from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
import time
from typing import Protocol

import httpx

from app.core.config import settings
from app.models.entities import MediaAsset


@dataclass(frozen=True)
class ProjectAnalysis:
    provider: str
    result: dict


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    status: str
    details: dict


class AnalysisProviderError(ValueError):
    def __init__(self, message: str, details: dict):
        super().__init__(message)
        self.details = details


@dataclass
class ProviderCircuitState:
    failure_count: int = 0
    opened_at: datetime | None = None


_external_circuit = ProviderCircuitState()


class AnalysisProvider(Protocol):
    provider_name: str

    def analyze(self, assets: list[MediaAsset]) -> ProjectAnalysis:
        raise NotImplementedError

    def health(self) -> ProviderHealth:
        raise NotImplementedError


class DeterministicLocalAnalysisProvider:
    provider_name = "deterministic-local-metadata-v1"

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.provider_name,
            status="healthy",
            details={"mode": "local", "requires_network": False},
        )

    def analyze(self, assets: list[MediaAsset]) -> ProjectAnalysis:
        features = [self._asset_feature(asset) for asset in assets]
        orientations = Counter(feature["orientation"] for feature in features)
        checksums = [asset.content_checksum for asset in assets if asset.content_checksum]
        duplicate_checksum_count = len(checksums) - len(set(checksums))
        audio_scores = [feature["audio"]["score"] for feature in features if feature["audio"]["score"] is not None]
        highlight_scores = [feature["highlight_score"] for feature in features]
        subject_count = sum(1 for feature in features if feature["subject"]["presence"] != "unknown")

        return ProjectAnalysis(
            provider=self.provider_name,
            result={
                "schema_version": 1,
                "provider": self.provider_name,
                "privacy": {
                    "media_bytes_used": False,
                    "inputs": ["asset metadata", "filename", "duration", "orientation", "mime_type", "size", "checksum"],
                },
                "summary": {
                    "asset_count": len(assets),
                    "scene_count": sum(feature["scene_count"] for feature in features),
                    "primary_orientation": orientations.most_common(1)[0][0] if orientations else "unknown",
                    "average_highlight_score": round(mean(highlight_scores), 3) if highlight_scores else 0,
                    "subjects_detected": subject_count,
                    "audio_quality": self._audio_quality(mean(audio_scores)) if audio_scores else "unknown",
                    "duplicate_clip_detection": "duplicates_found" if duplicate_checksum_count else "no_duplicates_found",
                },
                "asset_features": features,
                "safety_note": "No private media bytes are included in this analysis record.",
            },
        )

    def _asset_feature(self, asset: MediaAsset) -> dict:
        duration = asset.duration_seconds or 0
        scene_count = self._scene_count(asset)
        tags = self._tags(asset)
        subject = self._subject(asset, tags)
        audio_score = self._audio_score(asset)
        visual = self._visual_quality(asset, duration)
        highlight_score = self._highlight_score(asset, scene_count, subject, audio_score, tags)

        return {
            "asset_id": asset.id,
            "mime_type": asset.mime_type,
            "duration_seconds": round(duration, 2),
            "orientation": asset.orientation,
            "scene_count": scene_count,
            "highlight_score": highlight_score,
            "tags": tags,
            "subject": subject,
            "audio": {
                "quality": self._audio_quality(audio_score),
                "score": audio_score,
                "recommended_lufs": -14 if asset.mime_type.startswith("video/") else -16,
            },
            "visual": visual,
        }

    @staticmethod
    def _scene_count(asset: MediaAsset) -> int:
        if asset.mime_type.startswith("image/"):
            return 1
        if asset.mime_type.startswith("audio/"):
            return 0
        duration = asset.duration_seconds or 3
        return max(1, min(60, round(duration / 6)))

    @staticmethod
    def _tags(asset: MediaAsset) -> list[str]:
        name = f"{asset.original_filename} {asset.sanitized_filename}".lower()
        keyword_tags = {
            "intro": ["intro", "hook"],
            "hero": ["hero", "highlight"],
            "interview": ["interview", "talking_head"],
            "demo": ["demo", "product"],
            "screen": ["screen_recording", "tutorial"],
            "broll": ["b_roll"],
            "voice": ["voiceover"],
            "music": ["music"],
        }
        tags: list[str] = []
        for keyword, mapped_tags in keyword_tags.items():
            if keyword in name:
                tags.extend(mapped_tags)
        if asset.mime_type.startswith("image/"):
            tags.append("still")
        if asset.orientation == "portrait":
            tags.append("vertical_ready")
        if not tags:
            tags.append("general")
        return sorted(set(tags))

    @staticmethod
    def _subject(asset: MediaAsset, tags: list[str]) -> dict:
        if "talking_head" in tags or "voiceover" in tags:
            return {"presence": "likely_human", "confidence": 0.72, "framing": "face_subject"}
        if asset.mime_type.startswith("image/"):
            return {"presence": "unknown", "confidence": 0.35, "framing": "center"}
        if asset.orientation == "portrait":
            return {"presence": "possible_human", "confidence": 0.52, "framing": "face_subject"}
        return {"presence": "unknown", "confidence": 0.4, "framing": "center"}

    @staticmethod
    def _audio_score(asset: MediaAsset) -> float | None:
        if asset.mime_type.startswith("image/"):
            return None
        duration = max(asset.duration_seconds or 1, 1)
        bytes_per_second = asset.size_bytes / duration
        if asset.mime_type.startswith("audio/"):
            score = min(0.95, max(0.45, bytes_per_second / 18000))
        else:
            score = min(0.95, max(0.4, bytes_per_second / 90000))
        return round(score, 3)

    @staticmethod
    def _audio_quality(score: float | None) -> str:
        if score is None:
            return "unknown"
        if score >= 0.78:
            return "good"
        if score >= 0.58:
            return "usable"
        return "needs_review"

    @staticmethod
    def _visual_quality(asset: MediaAsset, duration: float) -> dict:
        if asset.mime_type.startswith("audio/"):
            return {"quality": "not_applicable", "blur_risk": "not_applicable", "motion": "none"}
        if asset.size_bytes < 200_000 and duration > 8:
            return {"quality": "needs_review", "blur_risk": "medium", "motion": "unknown"}
        return {"quality": "usable", "blur_risk": "low", "motion": "unknown"}

    @staticmethod
    def _highlight_score(asset: MediaAsset, scene_count: int, subject: dict, audio_score: float | None, tags: list[str]) -> float:
        score = 0.5
        if asset.mime_type.startswith("video/"):
            score += 0.12
        if subject["presence"] != "unknown":
            score += 0.1
        if scene_count >= 3:
            score += 0.08
        if audio_score is not None and audio_score >= 0.58:
            score += 0.07
        if {"hero", "highlight", "hook"} & set(tags):
            score += 0.1
        if asset.orientation == "portrait":
            score += 0.03
        return round(min(score, 0.97), 3)


class ExternalHTTPAnalysisProvider:
    provider_name = "external-http-analysis-v1"

    def health(self) -> ProviderHealth:
        if not settings.analysis_provider_url:
            return ProviderHealth(
                provider=self.provider_name,
                status="unhealthy",
                details={"reason": "analysis provider URL is not configured"},
            )
        try:
            response = httpx.get(
                settings.analysis_provider_health_url or settings.analysis_provider_url,
                headers=self._headers(),
                timeout=settings.analysis_provider_timeout_seconds,
            )
            return ProviderHealth(
                provider=self.provider_name,
                status="healthy" if response.status_code < 500 and not self._circuit_is_open() else "unhealthy",
                details={"status_code": response.status_code, "circuit": self._circuit_details()},
            )
        except httpx.HTTPError as exc:
            return ProviderHealth(
                provider=self.provider_name,
                status="unhealthy",
                details={"error": exc.__class__.__name__, "circuit": self._circuit_details()},
            )

    def analyze(self, assets: list[MediaAsset]) -> ProjectAnalysis:
        if not settings.analysis_provider_url:
            raise AnalysisProviderError(
                "analysis provider is not configured",
                {"provider": self.provider_name, "missing": "ANALYSIS_PROVIDER_URL"},
            )

        fallback = DeterministicLocalAnalysisProvider().analyze(assets).result
        response = self._post_with_retries(
            {
                "schema_version": 1,
                "privacy": {
                    "media_bytes_included": False,
                    "private_locator_included": settings.analysis_provider_include_private_locator,
                },
                "assets": [self._asset_payload(asset) for asset in assets],
            }
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise AnalysisProviderError(
                "analysis provider returned an invalid response",
                {"provider": self.provider_name, "reason": "response was not a JSON object"},
            )

        result = {**fallback, **payload}
        result["provider"] = payload.get("provider") or self.provider_name
        result["privacy"] = {
            **fallback.get("privacy", {}),
            **payload.get("privacy", {}),
            "media_bytes_used": False,
            "private_locator_included": settings.analysis_provider_include_private_locator,
        }
        return ProjectAnalysis(provider=result["provider"], result=result)

    def _post_with_retries(self, payload: dict) -> httpx.Response:
        if self._circuit_is_open():
            raise AnalysisProviderError(
                "analysis provider circuit is open",
                {"provider": self.provider_name, "circuit": self._circuit_details()},
            )

        attempts = max(1, settings.analysis_provider_max_attempts)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = httpx.post(
                    settings.analysis_provider_url,
                    headers=self._headers(),
                    json=payload,
                    timeout=settings.analysis_provider_timeout_seconds,
                )
                response.raise_for_status()
                self._record_success()
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(settings.analysis_provider_retry_backoff_seconds)
        self._record_failure()
        raise AnalysisProviderError(
            "analysis provider unavailable",
            {
                "provider": self.provider_name,
                "attempts": attempts,
                "error": last_error.__class__.__name__ if last_error else "unknown",
            },
        )

    @staticmethod
    def _record_success() -> None:
        _external_circuit.failure_count = 0
        _external_circuit.opened_at = None

    @staticmethod
    def _record_failure() -> None:
        _external_circuit.failure_count += 1
        if _external_circuit.failure_count >= settings.analysis_provider_circuit_failure_threshold:
            _external_circuit.opened_at = datetime.now(timezone.utc)

    @staticmethod
    def _circuit_is_open() -> bool:
        if _external_circuit.opened_at is None:
            return False
        reset_at = _external_circuit.opened_at + timedelta(seconds=settings.analysis_provider_circuit_reset_seconds)
        if datetime.now(timezone.utc) >= reset_at:
            _external_circuit.failure_count = 0
            _external_circuit.opened_at = None
            return False
        return True

    @staticmethod
    def _circuit_details() -> dict:
        return {
            "failure_count": _external_circuit.failure_count,
            "open": _external_circuit.opened_at is not None,
            "opened_at": _external_circuit.opened_at.isoformat() if _external_circuit.opened_at else None,
        }

    @staticmethod
    def _headers() -> dict:
        headers = {"Content-Type": "application/json"}
        if settings.analysis_provider_token:
            headers["Authorization"] = f"Bearer {settings.analysis_provider_token}"
        return headers

    @staticmethod
    def _asset_payload(asset: MediaAsset) -> dict:
        payload = {
            "asset_id": asset.id,
            "sanitized_filename": asset.sanitized_filename,
            "mime_type": asset.mime_type,
            "size_bytes": asset.size_bytes,
            "duration_seconds": asset.duration_seconds,
            "orientation": asset.orientation,
            "content_checksum": asset.content_checksum,
            "metadata": asset.metadata_json,
        }
        if settings.analysis_provider_include_private_locator:
            payload["private_locator"] = asset.private_locator
        return payload


def get_analysis_provider() -> AnalysisProvider:
    if settings.analysis_provider in {"deterministic_local", "deterministic-local-metadata-v1"}:
        return DeterministicLocalAnalysisProvider()
    if settings.analysis_provider in {"external_http", "external-http-analysis-v1"}:
        return ExternalHTTPAnalysisProvider()
    raise ValueError(f"unsupported analysis provider: {settings.analysis_provider}")
