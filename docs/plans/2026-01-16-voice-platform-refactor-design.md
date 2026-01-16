# Voice Platform Refactor Design

**Date:** 2026-01-16
**Status:** Draft
**Author:** Brainstorming session with Claude

## Executive Summary

This document outlines a comprehensive refactor of the "nobody" voice application into a modular voice platform. The refactor transitions from a Python-only implementation to a **Rust core with Python ML workers**, using **uv** for Python package management and adopting **hexagonal architecture** principles.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Core language | Rust | Real-time audio reliability, type safety, Tauri integration |
| ML workers | Python (via gRPC) | Moshi/Pocket TTS are Python-native |
| Architecture | Hexagonal (Ports & Adapters) | Swappable engines, testable core |
| Package management | uv (Python), Cargo (Rust) | Modern, fast, lockfile support |
| Communication | REST + WebSocket | REST for CRUD, WebSocket for real-time streaming |
| TTS engine | Pocket TTS | Voice cloning from audio samples |
| STT engine | Moshi MLX | Apple Silicon optimized, low latency |
| Dashboard | Web-based (+ optional Tauri) | Svelte/React served locally, can wrap as desktop app |

---

## 1. Goals & Requirements

### Primary Goals

1. **Extensibility** — Connect voice capabilities into any application via local service
2. **Maintainability** — Clear boundaries between components, compile-time guarantees
3. **Real-time reliability** — Zero audio glitches, predictable latencies
4. **Voice cloning** — Train custom voices from user-uploaded audio samples

### Functional Requirements

- Push-to-talk voice interaction with AI personas
- Multiple LLM provider support (Ollama, RedPill, OpenAI)
- Voice cloning with flexible quality levels (10s to 10+ minutes of samples)
- Web dashboard for managing voices, personas, and training jobs
- Real-time feedback during recording, processing, and playback

### Non-Functional Requirements

- Local-first: runs entirely on user's machine
- macOS primary (Apple Silicon optimized), Linux stretch goal
- Sub-200ms latency for audio pipeline
- Graceful degradation under load (time slip, not catch up)

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                        │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌────────────┐  │
│   │  Dashboard  │    │   Tauri     │    │ Hammerspoon │    │  HTTP/WS   │  │
│   │  (Web UI)   │    │  Desktop    │    │  Hotkeys    │    │  Clients   │  │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └─────┬──────┘  │
└──────────┼──────────────────┼──────────────────┼───────────────────┼────────┘
           │                  │                  │                   │
           └──────────────────┴────────┬─────────┴───────────────────┘
                                       │
                              HTTP / WebSocket
                                       │
┌──────────────────────────────────────┴──────────────────────────────────────┐
│                           RUST CORE SERVICE                                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         API Layer (axum)                             │   │
│  │   REST: /voices, /personas, /training, /sessions                    │   │
│  │   WebSocket: /ws/session/{id} (real-time audio + events)            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────┴───────────────────────────────────┐   │
│  │                      Application Layer                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │   │
│  │  │   Session    │  │    Voice     │  │     Conversation         │   │   │
│  │  │   Manager    │  │   Manager    │  │     Orchestrator         │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────┴───────────────────────────────────┐   │
│  │                        Domain Layer                                  │   │
│  │  Voice, VoiceSample, VoiceSession, Persona, ConversationHistory     │   │
│  │  SessionState: Idle → Recording → Processing → Synthesizing → Playing│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────┴───────────────────────────────────┐   │
│  │                     Port Traits (Interfaces)                         │   │
│  │  SttEngine, TtsEngine, LlmProvider, VoiceRepository,                │   │
│  │  AudioCapture, AudioPlayback, JobQueue                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────┴───────────────────────────────────┐   │
│  │                         Audio Engine                                 │   │
│  │  cpal (capture/playback) + ringbuf (lock-free SPSC buffers)         │   │
│  │  RateController (time-based streaming, slip mode)                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                               gRPC (tonic)                                  │
│                                    │                                        │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼────────────────────────────────────────┐
│                        PYTHON ML WORKERS                                    │
│                                    │                                        │
│   ┌────────────────┐    ┌──────────┴───────┐    ┌────────────────────┐     │
│   │   STT Worker   │    │   TTS Worker     │    │  Trainer Worker    │     │
│   │   (Moshi MLX)  │    │  (Pocket TTS)    │    │ (Voice Embedding)  │     │
│   │   Port 50051   │    │   Port 50052     │    │    Port 50053      │     │
│   └────────────────┘    └──────────────────┘    └────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Project Structure

```
nobody/
├── Cargo.toml                     # Workspace root
├── pyproject.toml                 # Python workspace (uv)
├── uv.lock                        # Python lockfile
│
├── crates/                        # Rust workspace members
│   ├── nobody-core/               # Domain + Application layer
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── domain/
│   │       │   ├── mod.rs
│   │       │   ├── voice.rs       # Voice, VoiceSample, VoiceProfile
│   │       │   ├── session.rs     # SessionState, VoiceSession
│   │       │   ├── persona.rs     # Persona, ConversationHistory
│   │       │   └── events.rs      # Domain events
│   │       ├── ports/             # Trait definitions
│   │       │   ├── mod.rs
│   │       │   ├── stt.rs         # trait SttEngine
│   │       │   ├── tts.rs         # trait TtsEngine
│   │       │   ├── llm.rs         # trait LlmProvider
│   │       │   ├── voice_repo.rs  # trait VoiceRepository
│   │       │   └── audio.rs       # trait AudioCapture, AudioPlayback
│   │       └── services/          # Use case implementations
│   │           ├── mod.rs
│   │           ├── transcription.rs
│   │           ├── synthesis.rs
│   │           ├── conversation.rs
│   │           └── training.rs
│   │
│   ├── nobody-audio/              # Real-time audio engine
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── capture.rs         # cpal input stream
│   │       ├── playback.rs        # cpal output stream
│   │       ├── buffer.rs          # Lock-free ring buffers
│   │       ├── rate_controller.rs # Time-based streaming
│   │       └── resampler.rs       # Sample rate conversion
│   │
│   ├── nobody-server/             # HTTP + WebSocket server
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── main.rs            # Entry point, composition root
│   │       ├── config.rs          # Configuration loading
│   │       ├── rest/              # axum REST handlers
│   │       │   ├── mod.rs
│   │       │   ├── voices.rs      # /voices CRUD
│   │       │   ├── personas.rs    # /personas CRUD
│   │       │   └── training.rs    # /training jobs
│   │       ├── ws/                # WebSocket handlers
│   │       │   ├── mod.rs
│   │       │   └── session.rs     # Real-time voice session
│   │       ├── grpc_clients/      # Python worker clients
│   │       │   ├── mod.rs
│   │       │   ├── stt_client.rs
│   │       │   └── tts_client.rs
│   │       └── workers/
│   │           └── manager.rs     # Worker process management
│   │
│   └── nobody-desktop/            # Tauri app (optional)
│       ├── Cargo.toml
│       ├── tauri.conf.json
│       └── src/
│           └── main.rs
│
├── workers/                       # Python ML workers
│   ├── stt-worker/
│   │   ├── pyproject.toml
│   │   └── src/stt_worker/
│   │       ├── __init__.py
│   │       ├── server.py          # gRPC server
│   │       └── moshi_engine.py    # Moshi STT wrapper
│   │
│   ├── tts-worker/
│   │   ├── pyproject.toml
│   │   └── src/tts_worker/
│   │       ├── __init__.py
│   │       ├── server.py          # gRPC server
│   │       └── pocket_engine.py   # Pocket TTS wrapper
│   │
│   └── trainer-worker/
│       ├── pyproject.toml
│       └── src/trainer_worker/
│           ├── __init__.py
│           ├── server.py          # gRPC server
│           └── voice_trainer.py   # Voice embedding computation
│
├── proto/                         # Shared protobuf definitions
│   ├── stt.proto
│   ├── tts.proto
│   └── training.proto
│
├── dashboard/                     # Web UI
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│
└── docs/
    └── plans/
```

---

## 4. Domain Model

### Voice Entity

```rust
pub struct Voice {
    pub id: VoiceId,
    pub name: String,
    pub description: Option<String>,
    pub quality: VoiceQuality,
    pub embedding_path: PathBuf,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

pub enum VoiceQuality {
    Quick,        // 10-30 seconds of training audio
    Standard,     // 1-5 minutes
    Professional, // 10+ minutes
}

pub struct VoiceSample {
    pub id: Uuid,
    pub voice_id: VoiceId,
    pub audio_path: PathBuf,
    pub duration_secs: f32,
    pub sample_rate: u32,
    pub uploaded_at: DateTime<Utc>,
}
```

### Session State Machine

```rust
pub enum SessionState {
    Idle,
    Recording,
    Processing,   // STT + LLM
    Synthesizing,
    Playing,
}

// Valid transitions:
// Idle → Recording
// Recording → Processing | Idle (cancelled)
// Processing → Synthesizing
// Synthesizing → Playing
// Playing → Idle | Recording (interrupt)
```

### Domain Events

```rust
pub enum SessionEvent {
    RecordingStarted { session_id: SessionId },
    TranscriptionComplete { session_id: SessionId, text: String },
    LlmRequestStarted { session_id: SessionId },
    LlmResponseReceived { session_id: SessionId, text: String },
    SynthesisStarted { session_id: SessionId },
    PlaybackStarted { session_id: SessionId },
    PlaybackComplete { session_id: SessionId },
    SessionError { session_id: SessionId, error: String },
}

pub enum VoiceEvent {
    VoiceCreated { voice_id: VoiceId, name: String },
    TrainingStarted { voice_id: VoiceId, job_id: JobId },
    TrainingProgress { job_id: JobId, percent: u8 },
    TrainingComplete { voice_id: VoiceId, job_id: JobId },
    TrainingFailed { voice_id: VoiceId, job_id: JobId, error: String },
}
```

---

## 5. Port Traits (Interfaces)

### STT Engine

```rust
#[async_trait]
pub trait SttEngine: Send + Sync {
    async fn start_stream(&self) -> Result<SttStream, SttError>;
}

pub struct SttStream {
    pub audio_tx: mpsc::Sender<AudioChunk>,
    pub transcription_rx: mpsc::Receiver<Transcription>,
}
```

### TTS Engine

```rust
#[async_trait]
pub trait TtsEngine: Send + Sync {
    async fn synthesize(
        &self,
        text: &str,
        voice_id: VoiceId,
    ) -> Result<TtsStream, TtsError>;

    async fn is_voice_ready(&self, voice_id: VoiceId) -> bool;
}
```

### Audio Capture/Playback (Lock-Free)

```rust
// CRITICAL: Uses lock-free ring buffers, NOT mpsc channels
pub trait AudioCapture: Send + Sync {
    fn start(&self) -> Result<AudioConsumer, AudioError>;
    fn stop(&self) -> Result<(), AudioError>;
    fn sample_rate(&self) -> u32;
}

pub trait AudioPlayback: Send + Sync {
    fn start(&self) -> Result<AudioProducer, AudioError>;
    fn stop(&self) -> Result<(), AudioError>;
    fn sample_rate(&self) -> u32;
}
```

---

## 6. Audio Pipeline

### Critical Design Constraint

**Real-time audio threads must NEVER:**
- Acquire locks (mutex, rwlock)
- Allocate memory (Box, Vec::push)
- Perform I/O (file, network)
- Call async functions

**Solution:** Lock-free SPSC ring buffers (`ringbuf` crate) for communication between audio thread and application.

### Audio Flow

```
Recording:
  Mic (cpal) → [lock-free ringbuf] → Capture Thread → [gRPC] → STT Worker

Playback:
  TTS Worker → [gRPC] → RateController → [lock-free ringbuf] → Speaker (cpal)
```

### Rate Controller

TTS produces audio faster than real-time. The RateController:
1. Tracks wall-clock time vs samples written
2. Sleeps when ahead of real-time
3. "Slips" forward if too far behind (avoids catch-up spam)

```rust
impl RateController {
    const MAX_DRIFT: Duration = Duration::from_millis(500);

    pub async fn write(&mut self, samples: &[f32]) -> Result<(), PlaybackError> {
        // If too far behind, slip forward rather than catching up
        if self.samples_written + drift_threshold < expected_samples {
            self.samples_written = expected_samples;
            self.start_time = Some(Instant::now());
        }
        // ... rate-limited write to ring buffer
    }
}
```

---

## 7. Python Worker Integration

### Communication Protocol

- **gRPC** with bidirectional streaming
- Proto files as single source of truth
- Rust: `tonic` + `tonic-build`
- Python: `grpcio` + `grpcio-tools`

### Worker Lifecycle

1. Rust server starts
2. `WorkerManager` spawns Python processes
3. Workers load ML models (expensive, done once)
4. Rust connects gRPC clients
5. Health check confirms ready
6. On shutdown, Rust kills worker processes

### STT Worker (Port 50051)

- Wraps Moshi MLX
- Bidirectional streaming: audio chunks in, transcriptions out
- Maintains 0.5s audio overlap for context

### TTS Worker (Port 50052)

- Wraps Pocket TTS
- Server streaming: text in, audio chunks out
- Manages loaded voice embeddings

### Trainer Worker (Port 50053)

- Computes voice embeddings from samples
- Long-running jobs with progress reporting
- Supports cancellation

---

## 8. API Design

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /voices | List all voices |
| POST | /voices | Create voice (metadata only) |
| GET | /voices/{id} | Get voice details |
| DELETE | /voices/{id} | Delete voice |
| POST | /voices/{id}/samples | Upload audio sample |
| GET | /voices/{id}/samples | List samples |
| POST | /voices/{id}/train | Start training job |
| GET | /personas | List personas |
| POST | /personas | Create persona |
| GET | /training/{job_id} | Get job status |
| DELETE | /training/{job_id} | Cancel job |
| GET | /status | Service health |

### WebSocket Protocol

Connect: `ws://localhost:8080/ws/session/{session_id}`

**Client → Server:**
```json
{"type": "start_recording"}
{"type": "stop_recording"}
{"type": "cancel"}
{"type": "set_persona", "persona_id": "..."}
{"type": "set_voice", "voice_id": "..."}
```

**Server → Client:**
```json
{"type": "recording_started", "session_id": "..."}
{"type": "transcription", "text": "...", "is_final": false}
{"type": "llm_response", "text": "..."}
{"type": "playback_started"}
{"type": "playback_complete"}
{"type": "error", "message": "..."}
```

**Audio Streaming:**
- Client sends binary frames (PCM f32le) during recording
- Server sends binary frames (PCM f32le) during playback

---

## 9. Key Dependencies

### Rust (Cargo.toml)

```toml
# Core
tokio = { version = "1", features = ["full"] }
async-trait = "0.1"
thiserror = "1"
serde = { version = "1", features = ["derive"] }

# Web
axum = { version = "0.7", features = ["ws"] }
tower = "0.4"
tower-http = { version = "0.5", features = ["cors", "fs"] }

# Audio
cpal = "0.15"
ringbuf = "0.4"
rubato = "0.15"  # resampling

# gRPC
tonic = "0.11"
prost = "0.12"

# Storage
rusqlite = { version = "0.31", features = ["bundled"] }

# Config
config = "0.14"
dotenvy = "0.15"

# Tracing
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
```

### Python (uv workspace)

```toml
# workers/stt-worker
dependencies = [
    "grpcio>=1.60.0",
    "grpcio-tools>=1.60.0",
    "moshi-mlx>=0.3.0",
    "numpy>=1.26.0",
]

# workers/tts-worker
dependencies = [
    "grpcio>=1.60.0",
    "grpcio-tools>=1.60.0",
    "pocket-tts>=0.1.0",
    "numpy>=1.26.0",
]
```

---

## 10. Implementation Phases

### Phase 1: Foundation (Week 1-2)

- [ ] Set up Cargo workspace structure
- [ ] Set up uv workspace for Python workers
- [ ] Define proto files and generate code
- [ ] Implement domain entities
- [ ] Implement port traits
- [ ] Basic configuration loading

### Phase 2: Audio Engine (Week 3-4)

- [ ] Implement AudioCapture with cpal + ringbuf
- [ ] Implement AudioPlayback with cpal + ringbuf
- [ ] Implement RateController with slip mode
- [ ] Unit tests for audio pipeline

### Phase 3: ML Workers (Week 5-6)

- [ ] STT worker with Moshi MLX
- [ ] TTS worker with Pocket TTS
- [ ] Trainer worker for voice embeddings
- [ ] Worker process manager in Rust
- [ ] gRPC client adapters

### Phase 4: Core Services (Week 7-8)

- [ ] SessionManager state machine
- [ ] Event bus with broadcast channels
- [ ] VoiceRepository (SQLite)
- [ ] LLM provider adapters (Ollama, RedPill)

### Phase 5: API Layer (Week 9-10)

- [ ] REST endpoints with axum
- [ ] WebSocket session handler
- [ ] Audio streaming over WebSocket
- [ ] CORS and static file serving

### Phase 6: Dashboard (Week 11-12)

- [ ] Voice management UI
- [ ] Training job progress
- [ ] Real-time session visualization
- [ ] Persona configuration

### Phase 7: Polish (Week 13+)

- [ ] Tauri desktop wrapper
- [ ] Hammerspoon integration update
- [ ] Documentation
- [ ] Performance profiling
- [ ] Error handling edge cases

---

## 11. Migration Strategy

### From Current Codebase

1. **Keep current app working** — Don't break existing functionality during migration
2. **Extract domain logic first** — Identify pure business logic that can move to Rust
3. **Build new service in parallel** — New Rust service runs alongside old Python app
4. **Migrate piece by piece** — Move one capability at a time (STT, then TTS, then LLM)
5. **Cut over when ready** — Switch Hammerspoon to point at new service

### Data Migration

- Voice samples: Copy to new storage location
- Personas: Export from YAML, import to SQLite
- Conversation history: Start fresh (or export/import if critical)

---

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Moshi MLX API changes | High | Pin version, abstract behind port |
| Pocket TTS voice quality | Medium | Test early, have fallback TTS |
| gRPC latency | Low | Profile, tune buffer sizes |
| Rust learning curve | Medium | Start with simpler crates, good docs |
| Apple Silicon only | Medium | Design for cross-platform, test on Intel |

---

## 13. References

### Architecture

- [Hexagonal Architecture in Rust](https://www.howtocodeit.com/articles/master-hexagonal-architecture-rust)
- [Pretty State Machine Patterns in Rust](https://hoverbear.org/blog/rust-state-machine-pattern/)
- [Event-Driven Architecture in Rust](https://medium.com/@kanishks772/designing-an-event-driven-system-in-rust-a-step-by-step-architecture-guide-18c0e8013e86)

### Real-Time Audio

- [cpal - Cross-platform audio I/O](https://github.com/RustAudio/cpal)
- [ringbuf - Lock-free SPSC ring buffer](https://crates.io/crates/ringbuf)
- [Design Patterns for Real-Time Computer Music Systems (CMU)](https://www.cs.cmu.edu/~rbd/doc/icmc2005workshop/real-time-systems-concepts-design-patterns.pdf)

### Voice/Speech

- [Pocket TTS](https://github.com/kyutai-labs/pocket-tts)
- [Moshi MLX](https://github.com/kyutai-labs/moshi)
- [Kyutai TTS Voices](https://huggingface.co/kyutai/tts-voices)

### Python Tooling

- [uv - Fast Python Package Manager](https://github.com/astral-sh/uv)
- [uv Workspaces](https://docs.astral.sh/uv/guides/projects/)

### Rust Tooling

- [tonic - gRPC for Rust](https://github.com/hyperium/tonic)
- [axum - Web framework](https://github.com/tokio-rs/axum)
- [Tauri - Desktop apps](https://tauri.app/)

---

## Appendix A: Verified Design Decisions

The following design decisions were verified against industry best practices:

### A.1 Lock-Free Audio Buffers

**Issue Found:** Initial design used `tokio::sync::mpsc` for audio threads.
**Problem:** mpsc uses internal locks, unsuitable for real-time audio.
**Solution:** Use `ringbuf` SPSC lock-free buffers.
**Reference:** [Real-time audio best practices](https://dev.to/drsh4dow/the-joy-of-the-unknown-exploring-audio-streams-with-rust-and-circular-buffers-494d)

### A.2 Runtime vs Typestate State Machine

**Question:** Should session states be encoded in types (typestate pattern)?
**Decision:** Runtime enum is appropriate.
**Rationale:** Voice sessions receive external events (WebSocket), making runtime state the correct choice for event-driven systems.
**Reference:** [statig library documentation](https://github.com/mdeloof/statig)

### A.3 Broadcast Channel for Events

**Question:** How to distribute events to multiple subscribers?
**Decision:** `tokio::sync::broadcast` with documented drop behavior.
**Note:** Slow receivers may miss events (acceptable for dashboard updates).
**Reference:** [Tokio broadcast channels](https://app.studyraid.com/en/read/10838/332160/broadcast-and-watch-channels)

### A.4 Rate Controller with Slip Mode

**Question:** How to handle TTS producing audio faster than real-time?
**Decision:** Rate-controlled streaming with "slip forward" on overload.
**Rationale:** Better to skip ahead than spam audio trying to catch up.
**Reference:** [CMU Real-Time Music Systems](https://www.cs.cmu.edu/~rbd/doc/icmc2005workshop/real-time-systems-concepts-design-patterns.pdf)
