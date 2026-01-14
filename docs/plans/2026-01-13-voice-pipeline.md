# Voice Pipeline Implementation Plan (moshi_mlx)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add real audio capture, speech-to-text, and text-to-speech to voice-realtime using moshi_mlx.

**Architecture:** Push-to-talk triggers sounddevice to record microphone audio. On release, moshi_mlx transcribes to text (STT), existing LLM router generates response, moshi_mlx synthesizes speech (TTS), sounddevice plays audio.

**Tech Stack:** moshi_mlx (Moshi STT + TTS), sounddevice (mic/speaker), numpy (audio buffers), rustymimi (audio codec)

**Key insight:** moshi_mlx provides both STT (via run_inference.py pattern) and TTS (via TTSModel). Single model for both, optimized for Apple Silicon.

---

## Task 1: Update Dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Update requirements.txt**

Replace mlx-audio with moshi_mlx:

```txt
# Voice pipeline (Moshi MLX for Apple Silicon)
moshi_mlx>=0.3.0

# LLM clients
ollama>=0.4.0
httpx>=0.27.0

# Configuration
pyyaml>=6.0

# Audio
sounddevice>=0.5.0
numpy>=1.26.0
```

**Step 2: Install moshi_mlx**

Run: `source ~/voice-env/bin/activate && pip install moshi_mlx`
Expected: Successfully installed moshi_mlx

**Step 3: Verify imports**

Run: `python -c "from moshi_mlx import models; print('OK')"`
Expected: "OK"

**Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: use moshi_mlx for STT and TTS

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Audio Capture Module

**Files:**
- Create: `audio_capture.py`
- Create: `tests/test_audio_capture.py`

**Step 1: Write failing test**

```python
"""Tests for audio capture module."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


def test_audio_recorder_starts_and_stops():
    """AudioRecorder should start recording and return audio on stop."""
    from audio_capture import AudioRecorder

    with patch("audio_capture.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        recorder = AudioRecorder(sample_rate=24000)
        recorder.start()

        assert recorder.is_recording is True

        recorder._buffer.append(np.zeros((1920,), dtype=np.float32))
        audio = recorder.stop()

        assert recorder.is_recording is False
        assert isinstance(audio, np.ndarray)


def test_audio_recorder_returns_empty_on_no_recording():
    """AudioRecorder should return empty array if stopped without recording."""
    from audio_capture import AudioRecorder

    recorder = AudioRecorder(sample_rate=24000)
    audio = recorder.stop()

    assert len(audio) == 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_audio_capture.py -v`
Expected: FAIL with "No module named 'audio_capture'"

**Step 3: Write audio_capture.py**

```python
"""Audio capture module using sounddevice."""

import threading
import numpy as np
import sounddevice as sd

import config


class AudioRecorder:
    """Records audio from microphone into a buffer.

    Note: Moshi expects 24kHz audio, so we record at that rate.
    """

    def __init__(self, sample_rate: int | None = None, channels: int | None = None):
        """Initialize recorder.

        Args:
            sample_rate: Sample rate in Hz. Defaults to 24000 for Moshi.
            channels: Number of channels. Defaults to 1 (mono).
        """
        self.sample_rate = sample_rate or 24000  # Moshi expects 24kHz
        self.channels = channels or 1
        self._buffer: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self.is_recording = False

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Callback for audio stream."""
        if status:
            print(f"Audio status: {status}")
        with self._lock:
            self._buffer.append(indata.copy().flatten())

    def start(self) -> None:
        """Start recording audio."""
        if self.is_recording:
            return

        self._buffer = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.float32,
            callback=self._audio_callback
        )
        self._stream.start()
        self.is_recording = True

    def stop(self) -> np.ndarray:
        """Stop recording and return audio data.

        Returns:
            Audio data as numpy array at 24kHz, or empty array if not recording.
        """
        if not self.is_recording:
            return np.array([], dtype=np.float32)

        self.is_recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if self._buffer:
                return np.concatenate(self._buffer)
            return np.array([], dtype=np.float32)

    def get_duration(self) -> float:
        """Get current recording duration in seconds."""
        with self._lock:
            total_samples = sum(len(chunk) for chunk in self._buffer)
        return total_samples / self.sample_rate
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_audio_capture.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add audio_capture.py tests/test_audio_capture.py
git commit -m "feat: add audio capture module with sounddevice

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Speech-to-Text Module (moshi_mlx)

**Files:**
- Create: `stt.py`
- Create: `tests/test_stt.py`

**Step 1: Write failing test**

```python
"""Tests for speech-to-text module."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


def test_transcriber_initializes():
    """Transcriber should initialize with model loading."""
    with patch("stt.hf_hub_download") as mock_download, \
         patch("stt.models") as mock_models, \
         patch("stt.sentencepiece") as mock_sp, \
         patch("stt.rustymimi") as mock_mimi:

        mock_download.return_value = "/fake/path"
        mock_models.LmConfig.from_config_dict.return_value = MagicMock()
        mock_models.Lm.return_value = MagicMock()
        mock_models.LmGen.return_value = MagicMock()

        from stt import MoshiTranscriber
        transcriber = MoshiTranscriber()

        assert transcriber is not None


def test_transcriber_handles_empty_audio():
    """Transcriber should return empty string for empty audio."""
    with patch("stt.hf_hub_download"), \
         patch("stt.models"), \
         patch("stt.sentencepiece"), \
         patch("stt.rustymimi"):

        from stt import MoshiTranscriber
        transcriber = MoshiTranscriber.__new__(MoshiTranscriber)
        transcriber.audio_tokenizer = None
        transcriber.gen = None
        transcriber.text_tokenizer = None

        result = transcriber.transcribe(np.array([], dtype=np.float32))

        assert result == ""
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stt.py -v`
Expected: FAIL with "No module named 'stt'"

**Step 3: Write stt.py**

Based on moshi_mlx/run_inference.py pattern:

```python
"""Speech-to-text module using moshi_mlx.

Based on moshi_mlx/run_inference.py - extracts text tokens from Moshi.
"""

import json
import numpy as np

from huggingface_hub import hf_hub_download
import mlx.core as mx
import mlx.nn as nn
import rustymimi
import sentencepiece

from moshi_mlx import models, utils


class MoshiTranscriber:
    """Transcribes audio to text using Moshi's text token output."""

    DEFAULT_REPO = "kyutai/moshiko-mlx-q8"
    SAMPLE_RATE = 24000
    FRAME_SIZE = 1920  # Samples per frame at 24kHz

    def __init__(self, hf_repo: str | None = None, quantize: int = 8):
        """Initialize transcriber.

        Args:
            hf_repo: HuggingFace repo for model weights.
            quantize: Quantization bits (4 or 8).
        """
        self.hf_repo = hf_repo or self.DEFAULT_REPO
        self.quantize = quantize
        self._load_model()

    def _load_model(self):
        """Load Moshi model and tokenizers."""
        # Load config
        config_path = hf_hub_download(self.hf_repo, "config.json")
        with open(config_path, "r") as f:
            raw_config = json.load(f)

        self.stt_config = raw_config.get("stt_config", None)

        # Load Mimi audio tokenizer
        mimi_name = raw_config["mimi_name"]
        mimi_path = hf_hub_download(self.hf_repo, mimi_name)

        lm_config = models.LmConfig.from_config_dict(raw_config)
        self.other_codebooks = lm_config.other_codebooks
        mimi_codebooks = max(lm_config.generated_codebooks, self.other_codebooks)
        self.audio_tokenizer = rustymimi.Tokenizer(mimi_path, num_codebooks=mimi_codebooks)

        # Load text tokenizer
        tokenizer_path = hf_hub_download(self.hf_repo, raw_config["tokenizer_name"])
        self.text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_path)

        # Load LM model
        moshi_name = raw_config.get("moshi_name", "model.safetensors")
        moshi_path = hf_hub_download(self.hf_repo, moshi_name)

        self.model = models.Lm(lm_config)
        self.model.set_dtype(mx.bfloat16)

        if self.quantize == 4:
            nn.quantize(self.model, bits=4, group_size=32)
        elif self.quantize == 8:
            nn.quantize(self.model, bits=8, group_size=64)

        self.model.load_weights(moshi_path, strict=True)

        # Condition tensor
        if self.model.condition_provider is not None:
            self.condition_tensor = self.model.condition_provider.condition_tensor("description", "very_good")
        else:
            self.condition_tensor = None

        # Warmup
        self.model.warmup(self.condition_tensor)

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio data as numpy array at 24kHz.

        Returns:
            Transcribed text.
        """
        if len(audio) == 0:
            return ""

        # Ensure audio is right shape [1, samples]
        if audio.ndim == 1:
            audio = audio.reshape(1, -1)

        # Apply STT config padding if available
        if self.stt_config is not None:
            pad_right = self.stt_config.get("audio_delay_seconds", 0.0)
            pad_left = self.stt_config.get("audio_silence_prefix_seconds", 0.0)
            pad_left = int(pad_left * self.SAMPLE_RATE)
            pad_right = int((pad_right + 1.0) * self.SAMPLE_RATE)
            audio = np.pad(audio, pad_width=[(0, 0), (pad_left, pad_right)], mode="constant")

        # Calculate steps
        steps = audio.shape[-1] // self.FRAME_SIZE

        # Create generator
        gen = models.LmGen(
            model=self.model,
            max_steps=steps,
            text_sampler=utils.Sampler(top_k=25, temp=0.8),
            audio_sampler=utils.Sampler(top_k=250, temp=0.8),
            cfg_coef=1.0,
            check=False,
        )

        # Process audio frame by frame
        transcript_parts = []
        for idx in range(steps):
            frame = audio[:, idx * self.FRAME_SIZE:(idx + 1) * self.FRAME_SIZE]

            # Encode audio frame
            audio_tokens = self.audio_tokenizer.encode_step(frame[None, 0:1])
            audio_tokens = mx.array(audio_tokens).transpose(0, 2, 1)[:, :, :self.other_codebooks]

            # Get text token
            text_token = gen.step(audio_tokens[0], self.condition_tensor)
            text_token = text_token[0].item()

            # Decode text token (skip padding tokens 0 and 3)
            if text_token not in (0, 3):
                text = self.text_tokenizer.id_to_piece(text_token)
                text = text.replace("▁", " ")
                transcript_parts.append(text)

        return "".join(transcript_parts).strip()
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_stt.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add stt.py tests/test_stt.py
git commit -m "feat: add STT module using moshi_mlx

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Text-to-Speech Module (moshi_mlx)

**Files:**
- Create: `tts.py`
- Create: `tests/test_tts.py`

**Step 1: Write failing test**

```python
"""Tests for text-to-speech module."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


def test_synthesizer_initializes():
    """Synthesizer should initialize."""
    with patch("tts.hf_hub_download"), \
         patch("tts.models"), \
         patch("tts.sentencepiece"), \
         patch("tts.TTSModel"):

        from tts import MoshiSynthesizer
        synth = MoshiSynthesizer.__new__(MoshiSynthesizer)
        synth.tts_model = MagicMock()

        assert synth is not None


def test_synthesizer_handles_empty_text():
    """Synthesizer should return empty array for empty text."""
    with patch("tts.hf_hub_download"), \
         patch("tts.models"), \
         patch("tts.sentencepiece"), \
         patch("tts.TTSModel"):

        from tts import MoshiSynthesizer
        synth = MoshiSynthesizer.__new__(MoshiSynthesizer)
        synth.tts_model = None
        synth.sample_rate = 24000

        result = synth.synthesize("")

        assert len(result) == 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tts.py -v`
Expected: FAIL with "No module named 'tts'"

**Step 3: Write tts.py**

Based on moshi_mlx/run_tts.py pattern:

```python
"""Text-to-speech module using moshi_mlx.

Based on moshi_mlx/run_tts.py - uses TTSModel for speech synthesis.
"""

import json
import numpy as np

from huggingface_hub import hf_hub_download
import mlx.core as mx
import mlx.nn as nn
import sentencepiece

from moshi_mlx import models
from moshi_mlx.models.tts import TTSModel, DEFAULT_DSM_TTS_REPO, DEFAULT_DSM_TTS_VOICE_REPO
from moshi_mlx.utils.loaders import hf_get


class MoshiSynthesizer:
    """Synthesizes speech from text using Moshi TTS."""

    SAMPLE_RATE = 24000

    def __init__(
        self,
        hf_repo: str | None = None,
        voice_repo: str | None = None,
        voice: str = "af_heart",
        quantize: int | None = 8,
    ):
        """Initialize synthesizer.

        Args:
            hf_repo: HuggingFace repo for TTS model.
            voice_repo: HuggingFace repo for voice embeddings.
            voice: Voice preset name.
            quantize: Quantization bits (None, 4, or 8).
        """
        self.hf_repo = hf_repo or DEFAULT_DSM_TTS_REPO
        self.voice_repo = voice_repo or DEFAULT_DSM_TTS_VOICE_REPO
        self.voice = voice
        self.quantize = quantize
        self.sample_rate = self.SAMPLE_RATE
        self._load_model()

    def _load_model(self):
        """Load TTS model."""
        # Load config
        config_path = hf_get("config.json", self.hf_repo)
        with open(config_path, "r") as f:
            raw_config = json.load(f)

        # Load weights
        mimi_path = hf_get(raw_config["mimi_name"], self.hf_repo)
        moshi_name = raw_config.get("moshi_name", "model.safetensors")
        moshi_path = hf_get(moshi_name, self.hf_repo)
        tokenizer_path = hf_get(raw_config["tokenizer_name"], self.hf_repo)

        # Build LM
        lm_config = models.LmConfig.from_config_dict(raw_config)
        model = models.Lm(lm_config)
        model.set_dtype(mx.bfloat16)
        model.load_pytorch_weights(str(moshi_path), lm_config, strict=True)

        if self.quantize is not None:
            nn.quantize(model.depformer, bits=self.quantize)
            for layer in model.transformer.layers:
                nn.quantize(layer.self_attn, bits=self.quantize)
                nn.quantize(layer.gating, bits=self.quantize)

        # Load tokenizers
        text_tokenizer = sentencepiece.SentencePieceProcessor(str(tokenizer_path))

        generated_codebooks = lm_config.generated_codebooks
        audio_tokenizer = models.mimi.Mimi(models.mimi_202407(generated_codebooks))
        audio_tokenizer.load_pytorch_weights(str(mimi_path), strict=True)

        # Build TTS model
        self.tts_model = TTSModel(
            model,
            audio_tokenizer,
            text_tokenizer,
            voice_repo=self.voice_repo,
            n_q=32,
            temp=0.6,
            cfg_coef=2.0,
            raw_config=raw_config,
        )
        self.mimi = self.tts_model.mimi

    def synthesize(self, text: str) -> np.ndarray:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.

        Returns:
            Audio data as numpy array at 24kHz.
        """
        if not text.strip():
            return np.array([], dtype=np.float32)

        # Prepare input
        entries = self.tts_model.prepare_script([text], padding_between=1)

        # Get voice conditioning
        if self.tts_model.multi_speaker:
            voice_path = self.tts_model.get_voice_path(self.voice)
            voices = [voice_path]
        else:
            voices = []

        attributes = self.tts_model.make_condition_attributes(voices, None)

        # Get prefix for single-speaker models
        prefixes = None
        if not self.tts_model.multi_speaker:
            prefix_path = hf_get(self.voice, self.voice_repo, check_local_file_exists=True)
            prefixes = [self.tts_model.get_prefix(prefix_path)]

        # Generate
        result = self.tts_model.generate(
            [entries],
            [attributes],
            prefixes=prefixes,
            cfg_is_no_prefix=True,
            cfg_is_no_text=True,
        )

        # Decode audio
        wav_frames = []
        for frame in result.frames:
            pcm = self.tts_model.mimi.decode_step(frame)
            wav_frames.append(pcm)

        wav = mx.concat(wav_frames, axis=-1)

        # Trim to actual content
        end_step = result.end_steps[0]
        if end_step is not None:
            wav_length = int(self.mimi.sample_rate * (end_step + self.tts_model.final_padding) / self.mimi.frame_rate)
            wav = wav[0, :, :wav_length]
        else:
            wav = wav[0]

        # Remove prefix if present
        if prefixes is not None:
            start_step = prefixes[0].shape[-1]
            start = int(self.mimi.sample_rate * start_step / self.mimi.frame_rate)
            wav = wav[:, start:]

        return np.array(mx.clip(wav, -1, 1)).flatten()
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_tts.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add tts.py tests/test_tts.py
git commit -m "feat: add TTS module using moshi_mlx

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Audio Playback Module

**Files:**
- Create: `audio_playback.py`
- Create: `tests/test_audio_playback.py`

**Step 1: Write failing test**

```python
"""Tests for audio playback module."""

import pytest
import numpy as np
from unittest.mock import patch


def test_player_plays_audio():
    """Player should play audio through sounddevice."""
    from audio_playback import AudioPlayer

    with patch("audio_playback.sd") as mock_sd:
        player = AudioPlayer(sample_rate=24000)
        audio = np.zeros((24000,), dtype=np.float32)

        player.play(audio)

        mock_sd.play.assert_called_once()
        mock_sd.wait.assert_called_once()


def test_player_handles_empty_audio():
    """Player should do nothing for empty audio."""
    from audio_playback import AudioPlayer

    with patch("audio_playback.sd") as mock_sd:
        player = AudioPlayer()
        player.play(np.array([], dtype=np.float32))

        mock_sd.play.assert_not_called()


def test_player_can_stop():
    """Player should be able to stop playback."""
    from audio_playback import AudioPlayer

    with patch("audio_playback.sd") as mock_sd:
        player = AudioPlayer()
        player.stop()

        mock_sd.stop.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_audio_playback.py -v`
Expected: FAIL with "No module named 'audio_playback'"

**Step 3: Write audio_playback.py**

```python
"""Audio playback module using sounddevice."""

import numpy as np
import sounddevice as sd


class AudioPlayer:
    """Plays audio through speakers."""

    DEFAULT_SAMPLE_RATE = 24000  # Match Moshi output

    def __init__(self, sample_rate: int | None = None):
        """Initialize player.

        Args:
            sample_rate: Sample rate in Hz. Defaults to 24000.
        """
        self.sample_rate = sample_rate or self.DEFAULT_SAMPLE_RATE

    def play(self, audio: np.ndarray, blocking: bool = True) -> None:
        """Play audio through speakers.

        Args:
            audio: Audio data as numpy array.
            blocking: If True, wait for playback to complete.
        """
        if len(audio) == 0:
            return

        sd.play(audio, self.sample_rate)
        if blocking:
            sd.wait()

    def stop(self) -> None:
        """Stop any current playback."""
        sd.stop()
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_audio_playback.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add audio_playback.py tests/test_audio_playback.py
git commit -m "feat: add audio playback module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Update Config

**Files:**
- Modify: `config.py`

**Step 1: Add Moshi model settings**

Add after the API configuration section:

```python
# Moshi model configuration
MOSHI_STT_REPO = "kyutai/moshiko-mlx-q8"  # STT model
MOSHI_TTS_REPO = "kyutai/moshika-mlx-q4"  # TTS model (if available, else same as STT)
MOSHI_VOICE_REPO = "kyutai/moshi-voices"  # Voice embeddings
MOSHI_VOICE = "af_heart"  # Default voice
MOSHI_QUANTIZE = 8  # Quantization bits (4 or 8)
MOSHI_SAMPLE_RATE = 24000  # Audio sample rate
```

**Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add Moshi model configuration

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Integrate Voice Pipeline into Main

**Files:**
- Modify: `main.py`

**Step 1: Add imports**

Add after existing imports:

```python
from audio_capture import AudioRecorder
from stt import MoshiTranscriber
from tts import MoshiSynthesizer
from audio_playback import AudioPlayer

# Global voice pipeline instances (lazy loaded)
recorder: AudioRecorder | None = None
transcriber: MoshiTranscriber | None = None
synthesizer: MoshiSynthesizer | None = None
player: AudioPlayer | None = None
```

**Step 2: Add initialization function**

```python
def get_voice_pipeline() -> tuple[AudioRecorder, MoshiTranscriber, MoshiSynthesizer, AudioPlayer]:
    """Get or create voice pipeline instances."""
    global recorder, transcriber, synthesizer, player

    if recorder is None:
        print("Loading voice pipeline (first run downloads ~2GB)...", file=sys.stderr)
        recorder = AudioRecorder()
        transcriber = MoshiTranscriber(hf_repo=config.MOSHI_STT_REPO, quantize=config.MOSHI_QUANTIZE)
        synthesizer = MoshiSynthesizer(voice=config.MOSHI_VOICE, quantize=config.MOSHI_QUANTIZE)
        player = AudioPlayer(config.MOSHI_SAMPLE_RATE)
        print("Voice pipeline ready", file=sys.stderr)

    return recorder, transcriber, synthesizer, player
```

**Step 3: Update handle_start**

```python
def handle_start():
    """Handle start command - begin listening (push-to-talk press)."""
    conv = get_or_create_conversation()
    rec, _, _, _ = get_voice_pipeline()

    conv.state = State.LISTENING
    conv.current_transcript = ""

    rec.start()
    print("State: LISTENING", file=sys.stderr)
```

**Step 4: Update handle_stop_and_process**

```python
def handle_stop_and_process():
    """Handle stop_and_process command - stop listening and get response."""
    conv = get_or_create_conversation()
    rec, trans, synth, play = get_voice_pipeline()

    if conv.state != State.LISTENING:
        print("Not listening, nothing to process", file=sys.stderr)
        return

    # Stop recording
    audio = rec.stop()

    if len(audio) == 0:
        print("No audio captured", file=sys.stderr)
        conv.state = State.IDLE
        return

    duration = len(audio) / 24000
    print(f"Captured {duration:.1f}s of audio", file=sys.stderr)

    # Transcribe
    conv.state = State.THINKING
    print("State: THINKING - Transcribing...", file=sys.stderr)

    transcript = trans.transcribe(audio)

    if not transcript:
        print("No speech detected", file=sys.stderr)
        conv.state = State.IDLE
        return

    print(f"You said: {transcript}", file=sys.stderr)
    conv.current_transcript = transcript

    # Get LLM response
    print("Getting response...", file=sys.stderr)
    conv.add_user_message(transcript)
    response = conv.get_response()
    conv.add_assistant_message(response)
    print(f"AI: {response}", file=sys.stderr)

    # Synthesize and play
    conv.state = State.SPEAKING
    print("State: SPEAKING", file=sys.stderr)

    speech = synth.synthesize(response)
    play.play(speech)

    conv.state = State.IDLE
    print("State: IDLE", file=sys.stderr)
```

**Step 5: Update handle_stop**

```python
def handle_stop():
    """Handle stop command - cancel and return to idle."""
    global recorder, player
    conv = get_or_create_conversation()

    if recorder and recorder.is_recording:
        recorder.stop()

    if player:
        player.stop()

    conv.stop()
    print("Stopped", file=sys.stderr)
```

**Step 6: Commit**

```bash
git add main.py
git commit -m "feat: integrate moshi_mlx voice pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Integration Test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

```python
"""Integration tests for voice pipeline."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


def test_full_pipeline_flow():
    """Test flow: capture -> transcribe -> LLM -> synthesize -> play."""
    with patch("audio_capture.sd"), \
         patch("stt.hf_hub_download"), \
         patch("stt.models"), \
         patch("stt.sentencepiece"), \
         patch("stt.rustymimi"), \
         patch("tts.hf_hub_download"), \
         patch("tts.models"), \
         patch("tts.sentencepiece"), \
         patch("tts.TTSModel"), \
         patch("audio_playback.sd") as mock_play_sd:

        from audio_capture import AudioRecorder
        from audio_playback import AudioPlayer

        # Test recording
        recorder = AudioRecorder()
        recorder.start()
        recorder._buffer.append(np.zeros((24000,), dtype=np.float32))
        audio = recorder.stop()
        assert len(audio) > 0

        # Test playback
        player = AudioPlayer()
        player.play(np.zeros((24000,), dtype=np.float32))
        mock_play_sd.play.assert_called_once()
```

**Step 2: Run test**

Run: `python -m pytest tests/test_integration.py -v`
Expected: 1 passed

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add voice pipeline integration test

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update Documentation

**Files:**
- Modify: `README.md`

**Step 1: Update README**

Update Features and add Voice Pipeline section:

```markdown
## Features

- **Push-to-Talk**: Hold Cmd+Shift+T to speak, release to get AI response
- **Multiple Personas**: Switch between Assistant, Tutor, Creative, and Casual modes
- **Hybrid LLM**: Local Ollama for speed, RedPill cloud for complex tasks
- **Voice Pipeline**: Moshi MLX for low-latency STT + TTS on Apple Silicon
- **Continuous Conversation**: Maintains context across turns

## Voice Pipeline

Uses [moshi_mlx](https://github.com/kyutai-labs/moshi) for speech processing:

- **STT**: Moshi text token extraction from audio
- **TTS**: Moshi TTSModel for natural speech synthesis
- **Codec**: Mimi neural audio codec (80ms latency)
- **Optimized**: Quantized models (8-bit) for Apple Silicon

First run downloads models (~2GB). Models are cached for subsequent runs.
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with moshi_mlx voice pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Run Full Test Suite

**Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: Manual test**

1. Ensure Ollama is running: `ollama serve`
2. Hold Cmd+Shift+T, speak, release
3. Verify: audio captured, transcribed, LLM responds, TTS plays

---

## Summary

After completing all tasks:

1. **audio_capture.py** - Microphone recording (24kHz for Moshi)
2. **stt.py** - Moshi-based speech-to-text
3. **tts.py** - Moshi-based text-to-speech
4. **audio_playback.py** - Speaker output
5. **Updated main.py** - Full voice pipeline
6. **Updated config.py** - Moshi settings
7. **Updated requirements.txt** - moshi_mlx

**Architecture:**
```
Mic → AudioRecorder → MoshiTranscriber → text
                                          ↓
                                    LLM Router (Ollama/RedPill)
                                          ↓
                        text → MoshiSynthesizer → AudioPlayer → Speaker
```
