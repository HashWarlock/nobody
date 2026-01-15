"""Tests for speech-to-text module."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


def test_transcriber_handles_empty_audio():
    """Transcriber should return empty string for empty audio."""
    from stt import MoshiTranscriber

    # Create instance without loading model
    transcriber = MoshiTranscriber.__new__(MoshiTranscriber)
    transcriber.audio_tokenizer = None
    transcriber.model = None
    transcriber.text_tokenizer = None
    transcriber.stt_config = None
    transcriber.other_codebooks = 8
    transcriber.condition_tensor = None
    transcriber.SAMPLE_RATE = 24000
    transcriber.FRAME_SIZE = 1920

    result = transcriber.transcribe(np.array([], dtype=np.float32))
    assert result == ""
