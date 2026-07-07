from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass(frozen=True)
class ApiClient:
    base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    api_token: str = os.getenv("API_TOKEN", "dev-only-token")

    def headers(self, correlation_id: Optional[str] = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_token}"}
        if correlation_id:
            headers["x-correlation-id"] = correlation_id
        return headers

    async def submit_ingestion(self, project_id: str, assets: list[dict], correlation_id: Optional[str] = None) -> dict:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            response = await client.post(
                f"/projects/{project_id}/ingest",
                json={"assets": assets},
                headers=self.headers(correlation_id),
            )
            response.raise_for_status()
            return response.json()

    async def submit_analysis(self, project_id: str, correlation_id: Optional[str] = None) -> dict:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            response = await client.post(f"/projects/{project_id}/analyze", headers=self.headers(correlation_id))
            response.raise_for_status()
            return response.json()

    async def submit_render(self, project_id: str, variants: list[str], correlation_id: Optional[str] = None) -> dict:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            response = await client.post(
                f"/projects/{project_id}/render",
                json={"variants": variants},
                headers=self.headers(correlation_id),
            )
            response.raise_for_status()
            return response.json()

    async def lookup_status(self, project_id: str, correlation_id: Optional[str] = None) -> dict:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.get(f"/projects/{project_id}/status", headers=self.headers(correlation_id))
            response.raise_for_status()
            return response.json()

    async def deliver_outputs(self, project_id: str, correlation_id: Optional[str] = None) -> dict:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.get(f"/projects/{project_id}/outputs", headers=self.headers(correlation_id))
            response.raise_for_status()
            return response.json()
