from __future__ import annotations

import asyncio
from typing import Any

import httpx


async def trino_query(host: str, port: int, sql: str, user: str = "trino") -> list[dict[str, Any]]:
    url = f"http://{host}:{port}/v1/statement"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, content=sql.encode("utf-8"), headers={"X-Trino-User": user})
        response.raise_for_status()
        payload = response.json()
        columns: list[str] = []
        rows: list[list] = []
        while True:
            if payload.get("columns") and not columns:
                columns = [c["name"] for c in payload["columns"]]
            rows.extend(payload.get("data") or [])
            nxt = payload.get("nextUri")
            if not nxt:
                if payload.get("error"):
                    raise RuntimeError(payload["error"].get("message") or payload["error"])
                break
            await asyncio.sleep(0.05)
            response = await client.get(nxt)
            response.raise_for_status()
            payload = response.json()
    return [dict(zip(columns, row)) for row in rows]
