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
