"""Text-to-speech module using moshi_mlx.

Based on moshi_mlx/run_tts.py - uses TTSModel for speech synthesis.
"""

import json
import numpy as np

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
        voice: str = "alba-mackenna/casual.wav",
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

        # Handle CFG distillation (model was trained with it)
        self.cfg_coef_conditioning = None
        if self.tts_model.valid_cfg_conditionings:
            self.cfg_coef_conditioning = self.tts_model.cfg_coef
            self.tts_model.cfg_coef = 1.0
            self.cfg_is_no_text = False
            self.cfg_is_no_prefix = False
        else:
            self.cfg_is_no_text = True
            self.cfg_is_no_prefix = True

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

        attributes = self.tts_model.make_condition_attributes(voices, self.cfg_coef_conditioning)

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
            cfg_is_no_prefix=self.cfg_is_no_prefix,
            cfg_is_no_text=self.cfg_is_no_text,
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

    def synthesize_streaming(self, text: str, on_audio_chunk):
        """Synthesize text to audio with streaming output.

        Calls on_audio_chunk with decoded audio as frames are generated,
        allowing playback to start before synthesis completes.

        Args:
            text: Text to synthesize.
            on_audio_chunk: Callback function(np.ndarray) called with each audio chunk.
        """
        if not text.strip():
            return

        # Prepare input
        entries = self.tts_model.prepare_script([text], padding_between=1)

        # Get voice conditioning
        if self.tts_model.multi_speaker:
            voice_path = self.tts_model.get_voice_path(self.voice)
            voices = [voice_path]
        else:
            voices = []

        attributes = self.tts_model.make_condition_attributes(voices, self.cfg_coef_conditioning)

        # Get prefix for single-speaker models
        prefixes = None
        prefix_samples = 0
        if not self.tts_model.multi_speaker:
            prefix_path = hf_get(self.voice, self.voice_repo, check_local_file_exists=True)
            prefixes = [self.tts_model.get_prefix(prefix_path)]
            prefix_samples = int(self.mimi.sample_rate * prefixes[0].shape[-1] / self.mimi.frame_rate)

        # Track whether we've passed the prefix
        self._streaming_frame_idx = 0
        self._prefix_frames = prefixes[0].shape[-1] if prefixes else 0
        self._samples_sent = 0

        def on_frame(frame):
            """Callback for each generated frame - decode and send audio."""
            self._streaming_frame_idx += 1

            # Skip prefix frames (they contain the voice conditioning audio)
            if self._streaming_frame_idx <= self._prefix_frames:
                return

            # Copy frame and ensure correct shape for decode_step
            # on_frame receives shape (batch, codebooks), decode_step needs (batch, codebooks, 1)
            frame_copy = mx.array(frame)
            if frame_copy.ndim == 2:
                frame_copy = frame_copy[:, :, None]

            # Decode frame to PCM
            pcm = self.tts_model.mimi.decode_step(frame_copy)
            audio = np.array(mx.clip(pcm, -1, 1)).flatten()

            if len(audio) > 0:
                on_audio_chunk(audio)

        # Generate with streaming callback
        self.tts_model.generate(
            [entries],
            [attributes],
            prefixes=prefixes,
            cfg_is_no_prefix=self.cfg_is_no_prefix,
            cfg_is_no_text=self.cfg_is_no_text,
            on_frame=on_frame,
        )
