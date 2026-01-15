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
