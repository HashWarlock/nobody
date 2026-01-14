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

        if steps == 0:
            return ""

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
                text = text.replace("\u2581", " ")
                transcript_parts.append(text)

        return "".join(transcript_parts).strip()
