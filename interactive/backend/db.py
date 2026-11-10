from __future__ import annotations

from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from interactive.backend.config import settings

SCHEMA_CANDIDATES = [
    settings.schema_sql,
    Path(__file__).resolve().parents[2] / "trading-dbt" / "init-scripts" / "03-interactive.sql",
]


class Database:
    def __init__(self) -> None:
        self.pool: AsyncConnectionPool | None = None

    async def connect(self) -> None:
        self.pool = AsyncConnectionPool(conninfo=settings.dsn, min_size=1, max_size=8, open=False)
        await self.pool.open()
        await self.apply_schema()

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def _pool(self) -> AsyncConnectionPool:
        if self.pool is None:
            raise RuntimeError("database pool is not open")
        return self.pool

    async def apply_schema(self) -> None:
        sql_path = next((p for p in SCHEMA_CANDIDATES if p.exists()), None)
        if sql_path is None:
            raise FileNotFoundError("03-interactive.sql not found")
        sql = sql_path.read_text()
        async with self._pool().connection() as conn:
            await conn.execute(sql)
            await conn.commit()

    async def fetch(self, query: str, params: tuple | dict | None = None) -> list[dict]:
        async with self._pool().connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def fetchone(self, query: str, params: tuple | dict | None = None) -> dict | None:
        rows = await self.fetch(query, params)
        return rows[0] if rows else None

    async def execute(self, query: str, params: tuple | dict | None = None) -> None:
        async with self._pool().connection() as conn:
            await conn.execute(query, params)
            await conn.commit()

    async def executemany(self, query: str, params_seq: list[tuple]) -> None:
        if not params_seq:
            return
        async with self._pool().connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(query, params_seq)
            await conn.commit()


db = Database()
