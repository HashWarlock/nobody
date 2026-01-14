"""Integration tests for voice pipeline."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


def test_full_pipeline_flow():
    """Test flow: capture -> transcribe -> LLM -> synthesize -> play."""
    with patch("audio_capture.sd") as mock_capture_sd, \
         patch("audio_playback.sd") as mock_play_sd:

        # Configure mock stream
        mock_stream = MagicMock()
        mock_capture_sd.InputStream.return_value = mock_stream

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
