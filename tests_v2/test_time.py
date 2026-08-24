from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from localflow.storage import Store
from localflow.time_service import TimeService


@pytest.mark.asyncio
async def test_time_helper_is_fixed_and_audited(root: Path) -> None:
    root.mkdir()
    helper = root / "helper.py"
    helper.write_text(
        "import sys\nprint(sys.argv[1])\n",
        encoding="utf-8",
    )
    store = Store(root / "runtime" / "localflow.db")
    service = TimeService(store, [sys.executable, str(helper)])
    reference = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    result = await service.adjust(reference, "admin")
    assert result["returncode"] == 0
    event = store.events_after(0)[0]
    assert event.kind == "system.time_adjustment"
    assert event.data["requested"] == reference.isoformat()
    assert service.status()["last_adjustment"]["requested"] == reference.isoformat()
    store.close()


@pytest.mark.asyncio
async def test_time_adjustment_rejects_unconfigured_helper(root: Path) -> None:
    store = Store(root / "runtime" / "localflow.db")
    with pytest.raises(RuntimeError):
        await TimeService(store, []).adjust(datetime.now(UTC), "admin")
    store.close()
