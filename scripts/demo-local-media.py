"""Run the real upload -> scan -> plan -> approve -> queue -> download workflow."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=Path("media/Yellowstone"))
    parser.add_argument("--api", default="http://localhost:8001")
    parser.add_argument("--name", default="Yellowstone")
    parser.add_argument("--output", type=Path, default=Path("outputs/Yellowstone"))
    args = parser.parse_args()
    files = sorted(path for path in args.folder.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"})
    if not 1 <= len(files) <= 12:
        raise ValueError("Provide 1-12 supported images/videos")
    token = os.environ.get("API_TOKEN", "dev-only-token")
    with httpx.Client(base_url=args.api, headers={"Authorization": f"Bearer {token}"}, timeout=180) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                raise RuntimeError(f"{method} {path}: {response.status_code} {response.text}")
            return response

        project = request("POST", "/projects", json={"name": args.name}).json()
        project_id = project["id"]
        base = f"/projects/{project_id}"
        output = args.output / project_id
        output.mkdir(parents=True, exist_ok=False)
        report = {"project_id": project_id, "api": args.api, "source_files": [path.name for path in files], "outputs": []}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Project: {project_id}", flush=True)
        for path in files:
            with path.open("rb") as stream:
                result = request("POST", base + "/upload", files={"file": (path.name, stream, mimetypes.guess_type(path.name)[0])})
            print(f"Uploaded and scanned: {path.name} {result.status_code}", flush=True)
        request("POST", base + "/analyze")
        plans = request("GET", base + "/plans").json()
        (output / "plans.json").write_text(json.dumps(plans, indent=2) + "\n")
        for plan in plans["plans"]:
            request("POST", base + f"/plans/{plan['id']}/approve", json={"notes": "Approved for local montage acceptance run"})
        request("POST", base + "/render", json={"variants": ["youtube_16x9", "shorts_9x16"]})
        deadline = time.monotonic() + 1800
        previous = None
        while time.monotonic() < deadline:
            state = request("GET", base + "/status").json()
            progress = [(job["variant"], job["status"]) for job in state["render_jobs"]]
            if progress != previous:
                print(f"Render progress: {progress}", flush=True)
                previous = progress
            if state["status"] == "failed":
                raise RuntimeError(json.dumps(state))
            if state["status"] == "ready":
                break
            time.sleep(2)
        else:
            raise TimeoutError("Rendering did not finish in 30 minutes")
        outputs = request("GET", base + "/outputs").json()["outputs"]
        for item in outputs:
            data = request("GET", base + f"/outputs/{item['id']}/download").content
            filename = output / f"{item['variant']}.mp4"
            filename.write_bytes(data)
            report["outputs"].append({"path": str(filename.resolve()), "metadata": item})
            print(f"Video: {filename}", flush=True)
        report["status"] = "ready"
        report["workflow"] = "real HTTP uploads, ClamAV, Redis/RQ worker, FFmpeg, private downloads"
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Dashboard: http://localhost:3001/?project={project_id}", flush=True)


if __name__ == "__main__":
    main()
