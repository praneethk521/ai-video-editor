"""Download the public-domain NPS acceptance dataset without touching personal media."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / "media" / "Yellowstone"
ARCHIVE = "https://www.nps.gov/features/yell/slidefile/"
SOURCES = [
    ("01-round-prairie.jpg", "scenics/mvnortheast/Images/07190.jpg", "Round Prairie and Amphitheater Mountain", "NPS / J Schmidt, 1977"),
    ("02-lamar-valley.jpg", "scenics/mvnortheast/Images/07191.jpg", "Lamar Valley and River", "NPS / J Schmidt, 1977"),
    ("03-yellowstone-river.jpg", "scenics/mvnortheast/Images/07198.jpg", "Hellroaring Creek and Yellowstone River", "NPS / J Schmidt, 1977"),
    ("04-grand-prismatic.jpg", "thermalfeatures/hotspringsterraces/midwaylower/Images/06118.jpg", "Grand Prismatic Spring", "NPS / M Storey, 1966"),
    ("05-mammoth-terraces.jpg", "thermalfeatures/hotspringsterraces/mammoth/Images/04878.jpg", "Jupiter Terrace, Mammoth Hot Springs", "NPS / Bryan Harry, 1965"),
    ("06-riverside-geyser.jpg", "thermalfeatures/geysers/upper/Images/04828.jpg", "Riverside Geyser", "NPS / Rosalie LaRue, 1976"),
    ("07-lower-falls.mp4", "https://www.nps.gov/nps-audiovideo/legacy/yell/77B87078-1DD8-B71B-0BF726FF93C0CA13/yell-IMG01622_1280x720.mp4", "Lower Falls, spring 2017", "NPS / Jacob W. Frank, 2017"),
]


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    records = []
    for filename, location, title, credit in SOURCES:
        url = location if location.startswith("https://") else ARCHIVE + location
        target = ROOT / filename
        if not target.exists():
            temporary = target.with_suffix(target.suffix + ".part")
            request = Request(url, headers={"User-Agent": "AI-Video-Editor-local-demo/1.0"})
            try:
                with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        if output.tell() > 250 * 1024 * 1024:
                            raise ValueError("Sample exceeds the 250 MB download limit")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        checksum = hashlib.sha256(target.read_bytes()).hexdigest()
        records.append({"filename": filename, "title": title, "credit": credit,
                        "source_url": url, "license": "Public domain, NPS archive",
                        "sha256": checksum, "bytes": target.stat().st_size})
        print(f"Downloaded {filename}: {target.stat().st_size} bytes", flush=True)
    manifest = {"license_sources": [ARCHIVE + "index.htm", "https://www.nps.gov/yell/learn/photosmultimedia/videolibrary.htm"], "files": records}
    (ROOT / "SOURCES.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (ROOT / "CREDITS.md").write_text("# Yellowstone sample media\n\nPublic-domain National Park Service archive.\n\n" + "\n".join(f"- {row['filename']}: {row['title']}. {row['credit']}. {row['source_url']}" for row in records) + "\n")


if __name__ == "__main__":
    main()
