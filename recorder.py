#!/usr/bin/env python3
"""Background audio recorder for push-to-talk.

This script runs as a separate process, recording audio until
a stop file is created, then saves the audio.
"""

import os
import sys
import time
import numpy as np
import sounddevice as sd

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# File paths
PID_FILE = config.TEMP_DIR / "recording.pid"
STOP_FILE = config.TEMP_DIR / "recording.stop"
AUDIO_FILE = config.TEMP_DIR / "recording.npy"

# Audio settings
SAMPLE_RATE = 24000
CHANNELS = 1

# Global state
chunks = []


def audio_callback(indata, frames, time_info, status):
    """Callback for audio stream."""
    chunks.append(indata.copy().flatten())


def main():
    global chunks

    # Clean up any stale files
    if STOP_FILE.exists():
        STOP_FILE.unlink()

    # Write PID file
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    try:
        # Start recording
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.float32,
            callback=audio_callback
        ):
            # Poll for stop signal
            while not STOP_FILE.exists():
                time.sleep(0.05)

    except Exception as e:
        print(f"Recording error: {e}", file=sys.stderr)

    finally:
        # Save audio
        if chunks:
            audio = np.concatenate(chunks)
            np.save(AUDIO_FILE, audio)

        # Clean up
        try:
            PID_FILE.unlink()
        except:
            pass
        try:
            STOP_FILE.unlink()
        except:
            pass


if __name__ == "__main__":
    main()
