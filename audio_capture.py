"""Audio capture module using sounddevice."""

import threading
import numpy as np
import sounddevice as sd


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
