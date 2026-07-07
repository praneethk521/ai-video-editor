from __future__ import annotations

import re
from pathlib import PurePosixPath

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str) -> str:
    name = PurePosixPath(filename).name.strip()
    name = SAFE_NAME_RE.sub("_", name)
    name = name.strip("._")
    if not name:
        raise ValueError("filename is empty after sanitization")
    if name in {".", ".."} or ".." in PurePosixPath(filename).parts:
        raise ValueError("path traversal is not allowed")
    return name[:160]


def validate_private_locator(locator: str) -> str:
    lowered = locator.lower()
    if lowered.startswith(("http://", "https://")):
        raise ValueError("public media URLs are not allowed")
    allowed_prefixes = ("drive://", "s3://private/", "file://private/")
    if not lowered.startswith(allowed_prefixes):
        raise ValueError("media locator must use an approved private storage prefix")
    return locator

