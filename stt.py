"""Speech-to-text module using lightning-whisper-mlx.

Uses the lightning-fast Whisper implementation optimized for Apple Silicon.
"""

import tempfile
import numpy as np
import scipy.io.wavfile as wav

from lightning_whisper_mlx import LightningWhisperMLX


class WhisperTranscriber:
    """Transcribes audio to text using Lightning Whisper MLX."""

    # Available models: tiny, base, small, medium, large, large-v2, large-v3
    # distil variants: distil-small.en, distil-medium.en, distil-large-v2, distil-large-v3
    DEFAULT_MODEL = "distil-medium.en"  # Fast & accurate for English
    SAMPLE_RATE = 16000  # Whisper expects 16kHz

    def __init__(self, model: str | None = None, batch_size: int = 12):
        """Initialize transcriber.

        Args:
            model: Whisper model name (tiny, base, small, medium, large, etc.)
            batch_size: Batch size for processing.
        """
        self.model_name = model or self.DEFAULT_MODEL
        self.batch_size = batch_size
        self._model = None

    def _load_model(self):
        """Lazy load the model on first use."""
        if self._model is None:
            print(f"Loading Whisper model: {self.model_name}...")
            self._model = LightningWhisperMLX(
                model=self.model_name,
                batch_size=self.batch_size
            )
            print("Whisper model ready!")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 24000) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio data as numpy array.
            sample_rate: Sample rate of the input audio (will resample to 16kHz).

        Returns:
            Transcribed text.
        """
        if len(audio) == 0:
            return ""

        self._load_model()

        # Ensure audio is float32
        audio = audio.astype(np.float32)

        # Flatten if needed
        if audio.ndim > 1:
            audio = audio.flatten()

        # Resample to 16kHz if needed (Whisper expects 16kHz)
        if sample_rate != self.SAMPLE_RATE:
            from scipy import signal
            num_samples = int(len(audio) * self.SAMPLE_RATE / sample_rate)
            audio = signal.resample(audio, num_samples)

        # Normalize audio to [-1, 1] range
        max_val = np.abs(audio).max()
        if max_val > 0:
            audio = audio / max_val

        # Convert to int16 for WAV file
        audio_int16 = (audio * 32767).astype(np.int16)

        # Write to temp WAV file (lightning-whisper-mlx needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            wav.write(temp_path, self.SAMPLE_RATE, audio_int16)

        try:
            # Transcribe
            result = self._model.transcribe(temp_path)
            return result.get("text", "").strip()
        finally:
            # Clean up temp file
            import os
            try:
                os.unlink(temp_path)
            except OSError:
                pass


# Alias for backwards compatibility
MoshiTranscriber = WhisperTranscriber
