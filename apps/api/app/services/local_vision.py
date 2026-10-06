"""Strict loopback-only adapter for private local vision inference."""
from __future__ import annotations

import base64
import json
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings

Scene = Literal["portrait", "group", "landscape", "landmark", "wildlife", "activity", "food",
                "architecture", "indoor", "document", "other"]
EyeState = Literal["open", "closed", "mixed", "not_visible", "uncertain", "no_people"]
Tag = Literal["scenery", "people", "wildlife", "geothermal", "waterfall", "mountain", "lake_river",
              "architecture", "food", "activity", "sunset", "indoor", "text", "vehicle"]


class VisionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: Scene
    setting: Literal["outdoor", "indoor", "mixed", "unknown"]
    people_count: int = Field(ge=0, le=20)
    face_visibility: Literal["clear", "partial", "not_visible", "no_people", "uncertain"]
    eye_state: EyeState
    occlusion: Literal["none", "minor", "major", "uncertain"]
    point_of_interest: Literal["natural_landmark", "manmade_landmark", "scenic_background", "wildlife",
                               "activity", "none", "uncertain"]
    landmark_hint: str | None = Field(default=None, max_length=80)
    editorial_relevance: float = Field(ge=0, le=1)
    moment_quality: float = Field(ge=0, le=1)
    tags: list[Tag] = Field(max_length=3, json_schema_extra={"uniqueItems": True})
    confidence: float = Field(ge=0, le=1)
    needs_review: bool


class LocalVisionError(ValueError):
    pass


PROMPT = """Analyze this private travel-media preview for video editing. Use only visible evidence.
Never identify a person or infer sensitive traits. Count visible people, but use uncertain/not_visible for
eyes unless faces and eyes are genuinely clear. Choose the dominant scene: landmark means a distinctive
natural or built feature; landscape means general scenery; architecture requires a building or structure
to dominate. Include zero to three tags for dominant, clearly visible subjects only; an empty list is
better than a wrong tag and never fill the list merely because options exist. Geothermal requires a hot
spring, geyser, mineral pool or steam; waterfall requires visibly falling water. point_of_interest is a category, while
landmark_hint is an optional unverified location hint. Score editorial_relevance, moment_quality and
confidence from 0 to 1. Return only JSON matching the supplied schema."""


def endpoint() -> str:
    parts = urlsplit(settings.local_vision_url)
    if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"}
            or parts.port not in {None, 11434} or parts.username or parts.password or parts.query or parts.fragment
            or parts.path not in {"", "/"}):
        raise LocalVisionError("local vision URL must be the loopback Ollama endpoint on port 11434")
    return settings.local_vision_url.rstrip("/")


def analyze_preview(jpeg: bytes) -> VisionEvidence:
    if not jpeg.startswith(b"\xff\xd8") or len(jpeg) > 3 * 1024 * 1024:
        raise LocalVisionError("local vision preview must be a JPEG under 3 MB")
    payload = {
        "model": settings.local_vision_model,
        "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(jpeg).decode("ascii")]}],
        "format": VisionEvidence.model_json_schema(),
        "stream": False,
        "options": {"temperature": 0, "num_predict": 500},
        "keep_alive": "15m",
    }
    try:
        with httpx.Client(timeout=settings.local_vision_timeout_seconds, follow_redirects=False,
                          trust_env=False) as client:
            response = client.post(endpoint() + "/api/chat", json=payload)
        if not response.is_success:
            raise LocalVisionError("local vision model request failed; verify Ollama and the configured model")
        if len(response.content) > 256 * 1024:
            raise LocalVisionError("local vision model returned an oversized response")
        body = response.json()
        content = (body.get("message") or {}).get("content")
        if not isinstance(content, str) or not content:
            raise LocalVisionError("local vision model returned no structured result")
        raw = json.loads(content)
        for key in ("editorial_relevance", "moment_quality", "confidence"):
            value = raw.get(key) if isinstance(raw, dict) else None
            if isinstance(value, (int, float)) and 1 < value <= 10:
                raw[key] = value / 10
        evidence = VisionEvidence.model_validate(raw)
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as exc:
        raise LocalVisionError("local vision model returned an invalid structured result") from exc
    return conservative_evidence(evidence)


def conservative_evidence(evidence: VisionEvidence) -> VisionEvidence:
    update = {"tags": list(dict.fromkeys(evidence.tags)), "needs_review": False}
    if evidence.people_count == 0:
        update.update(face_visibility="no_people", eye_state="no_people", occlusion="none")
    elif evidence.confidence < 0.7 or evidence.face_visibility != "clear":
        update.update(eye_state="uncertain", needs_review=True)
    if evidence.confidence < 0.6:
        update.update(landmark_hint=None, point_of_interest="uncertain", needs_review=True)
    natural_tags = {"geothermal", "waterfall", "mountain", "lake_river", "wildlife"}
    if evidence.scene == "architecture" and "architecture" not in evidence.tags and natural_tags & set(evidence.tags):
        update["scene"] = "landmark"
    if evidence.point_of_interest == "wildlife" and "wildlife" not in evidence.tags:
        update["point_of_interest"] = "natural_landmark" if natural_tags & set(evidence.tags) else "uncertain"
    if evidence.point_of_interest == "activity" and "activity" not in evidence.tags:
        update["point_of_interest"] = "uncertain"
    if evidence.point_of_interest == "manmade_landmark" and "architecture" not in evidence.tags:
        update["point_of_interest"] = "uncertain"
    if evidence.eye_state in {"closed", "mixed"} or evidence.occlusion == "major":
        update["needs_review"] = True
    return evidence.model_copy(update=update)


def feature_fields(evidence: VisionEvidence) -> dict:
    score = round(0.6 * evidence.editorial_relevance + 0.4 * evidence.moment_quality, 4)
    primary = (evidence.tags[0] if evidence.tags else evidence.point_of_interest
               if evidence.point_of_interest not in {"none", "uncertain"} else "general")
    return {
        "semantic": evidence.model_dump(),
        "editorial_score": score,
        "story_group": f"{evidence.scene}:{primary}",
        "highlight_score": score,
        "subject": {"presence": "likely_human" if evidence.people_count else "none",
                    "confidence": evidence.confidence},
        "tags": list(evidence.tags),
    }
