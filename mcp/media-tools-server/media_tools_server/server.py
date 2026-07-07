from __future__ import annotations

import asyncio
import json
import sys

from media_tools_server.tools import ApiClient

TOOLS = {
    "google_drive_media_ingestion": "Submit validated private media metadata for ingestion.",
    "metadata_lookup": "Lookup project render and media status.",
    "timeline_generation": "Run analysis and deterministic timeline generation.",
    "rendering_job_submission": "Queue rendering jobs for requested variants.",
    "job_status_lookup": "Lookup render job status.",
    "private_output_delivery": "Return private output metadata for manual upload.",
}


async def dispatch(request: dict) -> dict:
    client = ApiClient()
    name = request.get("tool")
    args = request.get("args", {})
    correlation_id = request.get("correlation_id")
    if name == "google_drive_media_ingestion":
        return await client.submit_ingestion(args["project_id"], args["assets"], correlation_id)
    if name == "timeline_generation":
        return await client.submit_analysis(args["project_id"], correlation_id)
    if name == "rendering_job_submission":
        return await client.submit_render(args["project_id"], args.get("variants", ["youtube_16x9", "shorts_9x16"]), correlation_id)
    if name in {"metadata_lookup", "job_status_lookup"}:
        return await client.lookup_status(args["project_id"], correlation_id)
    if name == "private_output_delivery":
        return await client.deliver_outputs(args["project_id"], correlation_id)
    if name == "tools/list":
        return {"tools": TOOLS}
    raise ValueError(f"unknown tool: {name}")


def main() -> None:
    for line in sys.stdin:
        try:
            response = asyncio.run(dispatch(json.loads(line)))
            print(json.dumps({"ok": True, "result": response}), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), flush=True)


if __name__ == "__main__":
    main()

