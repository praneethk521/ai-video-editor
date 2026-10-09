from __future__ import annotations

import array
import math
import sys
import wave
from dataclasses import dataclass
from pathlib import Path


SAMPLE_RATE = 24_000
TAU = 2 * math.pi


@dataclass(frozen=True)
class ScorePreset:
    bpm: int
    progression: tuple[tuple[int, int, int], ...]
    melody: tuple[int, ...]
    pad_gain: float
    bass_gain: float
    melody_gain: float
    pulse_gain: float


PRESETS = {
    "calm_cinematic": ScorePreset(
        bpm=76,
        progression=((50, 54, 57), (47, 50, 54), (43, 47, 50), (45, 49, 52)),
        melody=(0, 1, 2, 1, 0, 2, 1, 2),
        pad_gain=0.15,
        bass_gain=0.07,
        melody_gain=0.085,
        pulse_gain=0.018,
    ),
    "bright_journey": ScorePreset(
        bpm=108,
        progression=((55, 59, 62), (50, 54, 57), (52, 55, 59), (48, 52, 55)),
        melody=(0, 2, 1, 2, 0, 1, 2, 1),
        pad_gain=0.12,
        bass_gain=0.095,
        melody_gain=0.12,
        pulse_gain=0.035,
    ),
    "warm_memories": ScorePreset(
        bpm=86,
        progression=((48, 52, 55), (43, 47, 50), (45, 48, 52), (41, 45, 48)),
        melody=(2, 1, 0, 1, 2, 0, 1, 0),
        pad_gain=0.14,
        bass_gain=0.075,
        melody_gain=0.095,
        pulse_gain=0.022,
    ),
}


def generate_original_score(path: Path, preset_name: str, duration_seconds: float) -> None:
    """Write a deterministic original score with musical sections and no sampled material."""
    preset = PRESETS.get(preset_name)
    if preset is None or not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 900:
        raise ValueError("generated soundtrack preset or duration is invalid")

    total_frames = max(1, round(duration_seconds * SAMPLE_RATE))
    beat_seconds = 60 / preset.bpm
    bar_seconds = beat_seconds * 4
    path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for frame_start in range(0, total_frames, 4096):
            frames = array.array("h")
            frame_end = min(total_frames, frame_start + 4096)
            for frame in range(frame_start, frame_end):
                t = frame / SAMPLE_RATE
                left, right = _sample(preset, t, duration_seconds, beat_seconds, bar_seconds)
                frames.extend((_pcm(left), _pcm(right)))
            if sys.byteorder != "little":
                frames.byteswap()
            output.writeframesraw(frames.tobytes())


def _sample(
    preset: ScorePreset,
    t: float,
    duration: float,
    beat_seconds: float,
    bar_seconds: float,
) -> tuple[float, float]:
    bar = int(t / bar_seconds)
    bar_time = t % bar_seconds
    beat = bar_time / beat_seconds
    beat_index = int(beat)
    beat_phase = beat - beat_index
    eighth = int(beat * 2) % 8
    eighth_phase = (beat * 2) % 1
    chord = preset.progression[bar % len(preset.progression)]

    cycle_bar = bar % 8
    if bar == 0:
        section_gain, bass_level, melody_level, pulse_level = 0.68, 0.0, 0.45, 0.0
    elif cycle_bar in {1, 2, 3}:
        section_gain, bass_level, melody_level, pulse_level = 0.82, 0.65, 0.75, 0.45
    elif cycle_bar in {4, 5, 6}:
        section_gain, bass_level, melody_level, pulse_level = 1.0, 1.0, 1.0, 1.0
    else:
        section_gain, bass_level, melody_level, pulse_level = 0.76, 0.55, 0.65, 0.3

    chord_envelope = _smoothstep(min(bar_time / (beat_seconds * 0.7), 1.0))
    chord_envelope *= _smoothstep(min((bar_seconds - bar_time) / (beat_seconds * 0.55), 1.0))
    pad = sum(_soft_tone(_midi_frequency(note), t) for note in chord) / 3
    pad *= preset.pad_gain * chord_envelope

    bass_note = chord[0] - 12
    bass_envelope = math.exp(-3.1 * beat_phase)
    bass = _soft_tone(_midi_frequency(bass_note), t) * preset.bass_gain * bass_level * bass_envelope

    melody_note = chord[preset.melody[eighth] % len(chord)] + 12
    if cycle_bar in {5, 6} and eighth in {3, 7}:
        melody_note += 12
    pluck_envelope = math.exp(-5.4 * eighth_phase) * min(eighth_phase * 18, 1.0)
    melody = _bell_tone(_midi_frequency(melody_note), t) * preset.melody_gain * melody_level * pluck_envelope

    pulse_phase = beat_phase * beat_seconds
    pulse_frequency = 72 - 24 * min(pulse_phase / 0.18, 1.0)
    pulse_envelope = math.exp(-18 * pulse_phase) if beat_index in {0, 2} else 0.0
    pulse = math.sin(TAU * pulse_frequency * pulse_phase) * preset.pulse_gain * pulse_level * pulse_envelope

    master = section_gain * _edge_fade(t, duration)
    pan = 0.5 + 0.22 * math.sin(TAU * t / (bar_seconds * 2))
    center = pad + bass + pulse
    left = (center + melody * (1 - pan) * 1.5) * master
    right = (center + melody * pan * 1.5) * master
    return left, right


def _soft_tone(frequency: float, t: float) -> float:
    return math.sin(TAU * frequency * t) + 0.18 * math.sin(TAU * frequency * 2 * t)


def _bell_tone(frequency: float, t: float) -> float:
    return (
        math.sin(TAU * frequency * t)
        + 0.28 * math.sin(TAU * frequency * 2 * t)
        + 0.09 * math.sin(TAU * frequency * 3 * t)
    )


def _midi_frequency(note: int) -> float:
    return 440 * (2 ** ((note - 69) / 12))


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def _edge_fade(t: float, duration: float) -> float:
    fade_in = _smoothstep(min(t / min(1.2, duration / 3), 1.0))
    fade_out = _smoothstep(min((duration - t) / min(2.0, duration / 3), 1.0))
    return fade_in * fade_out


def _pcm(value: float) -> int:
    softened = value / (1 + abs(value))
    return round(max(-0.98, min(0.98, softened)) * 32767)
