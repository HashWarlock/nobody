"""Tests for text-to-speech module."""

import pytest
import numpy as np


def test_synthesizer_handles_empty_text():
    """Synthesizer should return empty array for empty text."""
    from tts import MoshiSynthesizer

    # Create instance without loading model
    synth = MoshiSynthesizer.__new__(MoshiSynthesizer)
    synth.tts_model = None
    synth.sample_rate = 24000

    result = synth.synthesize("")
    assert len(result) == 0

    result = synth.synthesize("   ")
    assert len(result) == 0
