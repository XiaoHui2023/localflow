from __future__ import annotations

import secrets
import time


def new_id() -> str:
    return f"{int(time.time() * 1000):013x}{secrets.token_hex(10)}"
