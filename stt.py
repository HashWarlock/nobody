"""Speech-to-text module using moshi_mlx.

Based on moshi_mlx/local.py - uses the quantized Moshi model for STT.
"""

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
    FRAME_SIZE = 1920  # Samples per frame at 24kHz (80ms)

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
        print(f"Loading Moshi model from {self.hf_repo}...")

        # Download model weights
        if self.quantize == 8:
            model_file = hf_hub_download(self.hf_repo, "model.q8.safetensors")
        elif self.quantize == 4:
            model_file = hf_hub_download(self.hf_repo, "model.q4.safetensors")
        else:
            model_file = hf_hub_download(self.hf_repo, "model.safetensors")

        # Download tokenizers
        tokenizer_file = hf_hub_download(self.hf_repo, "tokenizer_spm_32k_3.model")
        mimi_file = hf_hub_download(self.hf_repo, "tokenizer-e351c8d8-checkpoint125.safetensors")

        # Load text tokenizer
        print("Loading text tokenizer...")
        self.text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_file)

        # Load Mimi audio tokenizer (non-streaming for batch processing)
        print("Loading Mimi audio codec...")
        lm_config = models.config_v0_1()
        self.audio_tokenizer = rustymimi.Tokenizer(mimi_file, num_codebooks=lm_config.audio_codebooks)

        # Build and load LM
        print("Loading language model...")
        mx.random.seed(299792458)
        self.model = models.Lm(lm_config)
        self.model.set_dtype(mx.bfloat16)

        if self.quantize is not None:
            group_size = 32 if self.quantize == 4 else 64
            nn.quantize(self.model, bits=self.quantize, group_size=group_size)

        self.model.load_weights(model_file, strict=True)

        # Warmup
        print("Warming up model...")
        self.model.warmup()
        print("STT model ready!")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio data as numpy array at 24kHz.

        Returns:
            Transcribed text.
        """
        if len(audio) == 0:
            return ""

        # Ensure audio is float32
        audio = audio.astype(np.float32)

        # Ensure audio is right shape [1, samples]
        if audio.ndim == 1:
            audio = audio.reshape(1, -1)

        # Calculate steps
        steps = audio.shape[-1] // self.FRAME_SIZE

        if steps == 0:
            return ""

        # Create generator
        gen = models.LmGen(
            model=self.model,
            max_steps=steps + 5,
            text_sampler=utils.Sampler(),
            audio_sampler=utils.Sampler(),
            check=False,
        )

        # Process audio frame by frame
        transcript_parts = []
        for idx in range(steps):
            frame = audio[:, idx * self.FRAME_SIZE:(idx + 1) * self.FRAME_SIZE]

            # Encode audio frame to tokens - expects (batch, channels, samples)
            audio_tokens = self.audio_tokenizer.encode_step(frame[None, 0:1])
            audio_tokens = mx.array(audio_tokens).transpose(0, 2, 1)[:, :, :8]

            # Get text token from model
            text_token = gen.step(audio_tokens[0])
            text_token = text_token[0].item()

            # Decode text token (skip padding tokens 0 and 3)
            if text_token not in (0, 3):
                text = self.text_tokenizer.id_to_piece(text_token)
                text = text.replace("▁", " ")
                transcript_parts.append(text)

        return "".join(transcript_parts).strip()
