"""Audio playback module using sounddevice."""

import queue
import threading
import numpy as np
import sounddevice as sd


class StreamingAudioPlayer:
    """Plays audio chunks as they arrive with minimal latency."""

    DEFAULT_SAMPLE_RATE = 24000
    DEFAULT_BLOCKSIZE = 1024  # Small blocks for low latency

    def __init__(self, sample_rate: int | None = None, blocksize: int | None = None):
        """Initialize streaming player.

        Args:
            sample_rate: Sample rate in Hz. Defaults to 24000.
            blocksize: Audio block size. Smaller = lower latency.
        """
        self.sample_rate = sample_rate or self.DEFAULT_SAMPLE_RATE
        self.blocksize = blocksize or self.DEFAULT_BLOCKSIZE
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._stream: sd.OutputStream | None = None
        self._finished = threading.Event()
        self._buffer = np.array([], dtype=np.float32)

    def _audio_callback(self, outdata, frames, time, status):
        """Callback that feeds audio data to the output stream."""
        needed = frames
        filled = 0

        while filled < needed:
            # First use any buffered data
            if len(self._buffer) > 0:
                take = min(len(self._buffer), needed - filled)
                outdata[filled:filled + take, 0] = self._buffer[:take]
                self._buffer = self._buffer[take:]
                filled += take
                continue

            # Try to get more data from queue
            try:
                chunk = self._queue.get_nowait()
                if chunk is None:
                    # End signal - fill rest with silence and stop
                    outdata[filled:, 0] = 0
                    self._finished.set()
                    return
                self._buffer = chunk.flatten().astype(np.float32)
            except queue.Empty:
                # No data yet - fill with silence (this creates small gaps)
                outdata[filled:, 0] = 0
                return

    def start(self):
        """Start the audio stream."""
        self._finished.clear()
        self._queue = queue.Queue()
        self._buffer = np.array([], dtype=np.float32)
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            blocksize=self.blocksize,
            callback=self._audio_callback,
        )
        self._stream.start()

    def add_chunk(self, audio: np.ndarray):
        """Add an audio chunk to the playback queue.

        Args:
            audio: Audio data as numpy array.
        """
        if audio is not None and len(audio) > 0:
            self._queue.put(audio.flatten().astype(np.float32))

    def finish(self):
        """Signal that no more chunks will be added and wait for playback to complete."""
        self._queue.put(None)  # End signal
        self._finished.wait()  # Wait for playback to complete
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def stop(self):
        """Stop playback immediately."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._finished.set()


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
