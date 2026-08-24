#!/usr/bin/python3
from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime


def main() -> int:
    if os.geteuid() != 0 or len(sys.argv) != 2:
        print("must run as root with one RFC 3339 timestamp", file=sys.stderr)
        return 2
    try:
        requested = datetime.fromisoformat(sys.argv[1]).astimezone(UTC)
    except ValueError as exc:
        print(f"invalid timestamp: {exc}", file=sys.stderr)
        return 2
    if requested < datetime(2020, 1, 1, tzinfo=UTC) or requested > datetime(2200, 1, 1, tzinfo=UTC):
        print("timestamp outside allowed safety range", file=sys.stderr)
        return 2
    time.clock_settime(time.CLOCK_REALTIME, requested.timestamp())
    print(requested.isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
