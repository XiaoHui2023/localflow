from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def control_socket_path(root: Path, task_id: str) -> Path:
    digest = hashlib.sha256(f"{root.resolve()}:{task_id}".encode()).hexdigest()[:32]
    user_id = os.getuid() if hasattr(os, "getuid") else os.getpid()
    user_runtime = Path("/run/user") / str(user_id)
    base = (
        user_runtime / "localflow"
        if user_runtime.is_dir()
        else Path(tempfile.gettempdir()) / f"localflow-{user_id}"
    )
    base.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(base, 0o700)
    return base / f"{digest}.sock"
