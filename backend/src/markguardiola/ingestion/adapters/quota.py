from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


class QuotaExceededError(RuntimeError):
    pass


class RequestQuota:
    def __init__(
        self, daily_limit: int, *, ledger_path: Path | None = None, account: str = "default"
    ) -> None:
        if daily_limit < 1:
            raise ValueError()
        self.daily_limit = daily_limit
        self.used = 0
        self._day = datetime.now(UTC).date().isoformat()
        self._ledger_path = ledger_path
        self._account = account

    async def reserve(self) -> None:
        await asyncio.to_thread(self._update, True, None)

    async def observe_remaining(self, remaining: int) -> None:
        await asyncio.to_thread(self._update, False, max(0, remaining))

    def _update(self, reserve: bool, remaining: int | None) -> None:
        day = datetime.now(UTC).date().isoformat()
        if day != self._day:
            self._day, self.used = day, 0
        if self._ledger_path is None:
            self.used = self._next_used(self.used, reserve, remaining)
            return
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(
            sqlite3.connect(self._ledger_path, timeout=10, isolation_level=None)
        ) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS daily_quota (account TEXT NOT NULL, "
                "day TEXT NOT NULL, used INTEGER NOT NULL, PRIMARY KEY (account, day))"
            )
            row = connection.execute(
                "SELECT used FROM daily_quota WHERE account=? AND day=?", (self._account, day)
            ).fetchone()
            self.used = self._next_used(int(row[0]) if row else 0, reserve, remaining)
            connection.execute(
                "INSERT INTO daily_quota VALUES (?,?,?) ON CONFLICT(account,day) "
                "DO UPDATE SET used=excluded.used",
                (self._account, day, self.used),
            )
            connection.commit()

    def _next_used(self, used: int, reserve: bool, remaining: int | None) -> int:
        if remaining is not None:
            used = max(used, self.daily_limit - remaining)
        if reserve:
            if used >= self.daily_limit:
                raise QuotaExceededError()
            used += 1
        return used
