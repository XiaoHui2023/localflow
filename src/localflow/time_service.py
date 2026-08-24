from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

from .storage import Store


class TimeService:
    def __init__(self, store: Store, helper: list[str]) -> None:
        self.store = store
        self.helper = helper

    def status(self) -> dict[str, object]:
        last = self.store.latest_event("system.time_adjustment")
        result: dict[str, object] = {
            "wall_clock": datetime.now(UTC).isoformat(),
            "monotonic_seconds": time.monotonic(),
        }
        if last:
            result["last_adjustment"] = {
                "at": last.at.isoformat(),
                "requested": last.data.get("requested"),
                "returncode": last.data.get("returncode"),
            }
        else:
            result["last_adjustment"] = None
        return result

    async def adjust(self, reference: datetime, actor: str) -> dict[str, object]:
        if reference.tzinfo is None:
            raise ValueError("reference time must include a timezone")
        if not self.helper or not Path(self.helper[0]).is_absolute():
            raise RuntimeError("time helper is not configured with an absolute executable")
        normalized = reference.astimezone(UTC).isoformat()
        requested = self.status()
        process = await asyncio.create_subprocess_exec(
            *self.helper,
            normalized,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        result = {
            "requested": normalized,
            "actor": actor,
            "returncode": process.returncode,
            "stdout": stdout.decode(errors="replace")[-2048:],
            "stderr": stderr.decode(errors="replace")[-2048:],
            "before": requested,
            "after": self.status(),
        }
        self.store.append_event(None, "system.time_adjustment", result)
        if process.returncode:
            raise RuntimeError(result["stderr"] or "time helper rejected the request")
        return result
