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


def test_player_non_blocking():
    """Player should not wait when blocking=False."""
    from audio_playback import AudioPlayer

    with patch("audio_playback.sd") as mock_sd:
        player = AudioPlayer(sample_rate=24000)
        audio = np.zeros((24000,), dtype=np.float32)

        player.play(audio, blocking=False)

        mock_sd.play.assert_called_once()
        mock_sd.wait.assert_not_called()


def test_player_can_stop():
    """Player should be able to stop playback."""
    from audio_playback import AudioPlayer

    with patch("audio_playback.sd") as mock_sd:
        player = AudioPlayer()
        player.stop()

        mock_sd.stop.assert_called_once()
