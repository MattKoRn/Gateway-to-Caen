"""Extract packaged artwork and sounds into a versioned user cache."""
from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

from .persistence import user_data_dir

ASSET_VERSION = "0.6.0"


def ensure_assets() -> Path:
    destination = user_data_dir() / f"assets_{ASSET_VERSION.replace('.', '_')}"
    marker = destination / ".complete"
    if marker.exists():
        return destination
    destination.mkdir(parents=True, exist_ok=True)
    part_dir = Path(__file__).resolve().parent / "_assets"
    encoded = "".join(path.read_text(encoding="ascii") for path in sorted(part_dir.glob("assets_*.b64")))
    payload = base64.b64decode(encoded.encode("ascii"), validate=True)
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        archive.extractall(destination)
    marker.write_text(ASSET_VERSION, encoding="utf-8")
    return destination
