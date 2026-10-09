from __future__ import annotations

import array
import hashlib
import math
import wave

import pytest

from app.music import SAMPLE_RATE, generate_original_score


def _read_mono_windows(path, seconds=1):
    with wave.open(str(path), "rb") as stream:
        assert stream.getnchannels() == 2
        assert stream.getframerate() == SAMPLE_RATE
        samples = array.array("h", stream.readframes(stream.getnframes()))
    left = samples[::2]
    window_size = SAMPLE_RATE * seconds
    windows = []
    for start in range(0, len(left) - window_size + 1, window_size):
        chunk = left[start:start + window_size]
        rms = math.sqrt(sum(value * value for value in chunk) / len(chunk))
        zcr = sum((a < 0) != (b < 0) for a, b in zip(chunk, chunk[1:])) / len(chunk)
        windows.append((rms, zcr))
    return samples, windows


def test_score_has_sections_dynamics_and_timbre_changes(tmp_path):
    score = tmp_path / "score.wav"
    generate_original_score(score, "calm_cinematic", 16)

    samples, windows = _read_mono_windows(score)
    inner = windows[1:-1]
    rms_ratio = max(window[0] for window in inner) / min(window[0] for window in inner)
    zcr_spread = max(window[1] for window in inner) - min(window[1] for window in inner)

    assert len(samples) == 16 * SAMPLE_RATE * 2
    assert max(abs(sample) for sample in samples) < 32767
    assert rms_ratio > 1.25
    assert zcr_spread > 0.002


def test_score_is_original_deterministic_and_preset_specific(tmp_path):
    hashes = []
    for preset in ("calm_cinematic", "bright_journey", "warm_memories", "calm_cinematic"):
        path = tmp_path / f"{preset}-{len(hashes)}.wav"
        generate_original_score(path, preset, 3)
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())

    assert len(set(hashes[:3])) == 3
    assert hashes[0] == hashes[3]


@pytest.mark.parametrize("preset,duration", [("unknown", 2), ("calm_cinematic", 0), ("calm_cinematic", 901)])
def test_score_rejects_invalid_requests(tmp_path, preset, duration):
    with pytest.raises(ValueError, match="preset or duration"):
        generate_original_score(tmp_path / "invalid.wav", preset, duration)
