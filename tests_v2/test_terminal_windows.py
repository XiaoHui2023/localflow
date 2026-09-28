import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from localflow.api import create_app
from localflow.models import TaskCreate
from localflow.settings import ExecutionSettings, ServerSettings, Settings
from localflow.terminal_windows import terminal_window


@pytest.mark.parametrize("columns", [20, 80, 160])
@pytest.mark.parametrize("line", [b"x\n", b"ordinary output\n", "中文信息\t\n".encode(), b"x" * 1000 + b"\n"])
def test_adjacent_windows_cover_every_byte_with_bounded_rows(tmp_path: Path, columns, line) -> None:
    path = tmp_path / "output.log"
    data = line * 12000
    path.write_bytes(data)
    end = len(data)
    covered_start = end
    while end:
        bounds = terminal_window(path, max(0, end - 4 * 1024 * 1024), end, columns)
        window = data[bounds["start"]:bounds["end"]]
        rows = window.count(b"\n") + (len(window) + 7 * window.count(b"\t") + columns - 1) // columns
        assert rows <= 4000
        assert bounds["end"] >= covered_start
        assert bounds["start"] < covered_start
        covered_start = bounds["start"]
        end = bounds["start"]
    assert covered_start == 0


def test_search_hit_survives_dense_context(tmp_path: Path) -> None:
    path = tmp_path / "output.log"
    data = b"\n" * 9000 + "中文needle\n".encode() + b"\n" * 10000
    path.write_bytes(data)
    hit = data.index(b"needle")
    bounds = terminal_window(path, 0, len(data), 20, "hit", hit)
    assert bounds["start"] <= hit < bounds["end"]
    data[bounds["start"]:bounds["end"]].decode("utf-8", errors="strict")


def test_row_windows_and_download_use_state_root_and_enforce_read_access(tmp_path: Path) -> None:
    config_root, state_root = tmp_path / "config", tmp_path / "state"
    app = create_app(config_root, state_root=state_root, settings=Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(backend="subprocess")), start_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        task = app.state.tasks.submit(TaskCreate(name="archive", working_directory=str(config_root), command=["true"]))
        log = state_root / "logs" / task.id / "output.log"
        data = b"\xff\x00" + b"short\n" * 12000 + "中文末尾\n".encode()
        log.write_bytes(data)
        for endpoint in ("download", "window?start=0&end=999999"):
            assert client.get(f"/api/v1/tasks/{task.id}/logs/{endpoint}").status_code == 403
        key = (config_root / "secrets/web-admin-key").read_text(encoding="ascii").strip()
        assert client.post("/api/v1/auth/local-sessions", json={"key": key}).status_code == 200
        download = client.get(f"/api/v1/tasks/{task.id}/logs/download")
        assert download.content == data
        assert download.headers["x-localflow-output-complete"] == "true"
        bounds = client.get(f"/api/v1/tasks/{task.id}/logs/window", params={
            "start": 0, "end": len(data), "columns": 20}).json()
        assert 0 < bounds["start"] < bounds["end"] == len(data)
        assert client.get(f"/api/v1/tasks/{task.id}/logs/window", params={
            "start": 0, "end": len(data), "columns": 1}).status_code == 422
        with client.websocket_connect(
            f"ws://127.0.0.1/api/v1/tasks/{task.id}/terminal?offset=0&end={len(data)}&window=rows&columns=20",
            headers={"Origin": "http://127.0.0.1"},
        ) as websocket:
            assert websocket.receive_json() == {"type": "window", **bounds}
            received = b""
            while True:
                message = websocket.receive_json()
                if message["type"] == "caught_up":
                    assert message["log_updated_at"] is not None
                    break
                received += base64.b64decode(message["data"])
                websocket.send_json({"type": "ack", "offset": message["offset"]})
            assert received == data[bounds["start"]:bounds["end"]]


def test_forward_windows_cover_dense_archive(tmp_path: Path) -> None:
    path = tmp_path / "output.log"
    data = b"x\n" * 40000
    path.write_bytes(data)
    position = 0
    while position < len(data):
        bounds = terminal_window(path, position, len(data), 20, "later")
        assert bounds["start"] == position < bounds["end"]
        position = bounds["end"]


@pytest.mark.parametrize("direction", ["tail", "later"])
def test_malformed_continuation_bytes_cannot_create_an_empty_window(tmp_path: Path, direction) -> None:
    path = tmp_path / "output.log"
    path.write_bytes(b"\x80" * 200000)
    bounds = terminal_window(path, 0, 200000, 20, direction)
    assert 0 < bounds["end"] - bounds["start"] <= 80000
