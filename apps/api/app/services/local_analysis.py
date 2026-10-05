"""Local pixel inspection. No network, face identity, or claimed semantic AI."""
from __future__ import annotations

import hashlib
import statistics
import subprocess
from pathlib import Path

from app.core.config import settings
from app.models.entities import MediaAsset
from app.services.analysis_providers import ProjectAnalysis
from video_shared.media import source_path

SIDE = 128


def inspect_pixels(pixels: bytes) -> dict:
    if len(pixels) != SIDE * SIDE:
        raise ValueError("could not decode a complete preview frame")
    laplacian = [4 * pixels[y * SIDE + x] - pixels[y * SIDE + x - 1] - pixels[y * SIDE + x + 1]
                 - pixels[(y - 1) * SIDE + x] - pixels[(y + 1) * SIDE + x]
                 for y in range(1, SIDE - 1) for x in range(1, SIDE - 1)]
    sharpness = statistics.pvariance(laplacian)
    dark = sum(value < 10 for value in pixels) / len(pixels)
    bright = sum(value > 245 for value in pixels) / len(pixels)
    flags = []
    if sharpness < 12:
        flags.append("low_detail_or_blur")
    if dark > 0.95:
        flags.append("severe_underexposure")
    if bright > 0.95:
        flags.append("severe_overexposure")
    score = round(0.65 * min(1, sharpness / 300) + 0.35 * (1 - max(dark, bright)), 4)
    return {"score": score, "usable": not flags, "flags": flags,
            "laplacian_variance": round(sharpness, 2), "dark_fraction": round(dark, 4),
            "bright_fraction": round(bright, 4), "eye_state": "unknown", "landmark": "unknown"}


def read_frame(path: Path, timestamp: float) -> bytes:
    result = subprocess.run(
        [settings.ffmpeg_path, "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
         "-ss", str(timestamp), "-i", str(path), "-vf", f"scale={SIDE}:{SIDE},format=gray",
         "-frames:v", "1", "-threads", "1", "-f", "rawvideo", "pipe:1"],
        check=True, capture_output=True, timeout=30,
    )
    return result.stdout


def analyze_local_media(assets: list[MediaAsset]) -> ProjectAnalysis:
    if not 1 <= len(assets) <= 500:
        raise ValueError("local analysis requires 1-500 media files")
    features = []
    fingerprints = []
    checksums = {}
    for asset in assets:
        metadata = asset.metadata_json or {}
        path = source_path(Path(settings.media_source_root), asset.project_id, metadata.get("relative_path", ""))
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if checksum != metadata.get("sha256"):
            raise ValueError("media changed after malware scanning")
        still = asset.mime_type.startswith("image/")
        duration = asset.duration_seconds or 3
        times = [0.0] if still else [round(max(0, duration - 0.1) * fraction, 3) for fraction in (0, 0.25, 0.5, 0.75)]
        samples = []
        try:
            for timestamp in times:
                pixels = read_frame(path, timestamp)
                samples.append((inspect_pixels(pixels), timestamp, pixels))
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("local frame analysis failed; check media encoding") from exc
        quality, timestamp, pixels = max(samples, key=lambda sample: sample[0]["score"])
        # Conservative whole-image comparison; never groups face identities.
        fingerprint = bytes(pixels[y * SIDE + x] for y in range(0, SIDE, 8) for x in range(0, SIDE, 8))
        group = checksums.get(checksum, asset.id)
        if still and group == asset.id:
            for previous, previous_group in fingerprints:
                if sum(abs(a - b) for a, b in zip(fingerprint, previous)) / len(fingerprint) < 5:
                    group = previous_group
                    break
            fingerprints.append((fingerprint, group))
        checksums[checksum] = group
        features.append({"asset_id": asset.id, "mime_type": asset.mime_type,
                         "duration_seconds": duration, "orientation": asset.orientation,
                         "quality": quality, "highlight_score": quality["score"],
                         "duplicate_group": group, "recommended_start": 0 if still else round(max(0, min(timestamp - 1, duration - min(8, duration))), 2),
                         "sample_times": times, "subject": {"presence": "unknown"},
                         "audio": {"quality": "unknown"}, "tags": [], "scene_count": 1})
    return ProjectAnalysis(provider="local-pixel-quality-v1", result={
        "schema_version": 1, "provider": "local-pixel-quality-v1", "asset_features": features,
        "privacy": {"media_bytes_used": True, "processing": "local_only", "external_transfers": False},
        "summary": {"asset_count": len(features), "review_count": sum(not item["quality"]["usable"] for item in features)},
        "limitations": ["Technical preview-frame heuristics only", "Eye-state and landmark models not implemented"],
    })
