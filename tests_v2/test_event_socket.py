import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from localflow.api import create_app
from localflow.settings import ExecutionSettings, ServerSettings, Settings


def receive_event(socket):
    for _ in range(5):
        message = socket.receive_json()
        if message["type"] == "event":
            return message
    raise AssertionError("event missing")


def test_events_cursor_replay_and_current_identity(admin, root):
    store = admin.app.state.store
    first = store.append_event(None, "config.changed", {"path": "private.yaml"})
    with admin.websocket_connect("/api/v1/events") as socket:
        assert socket.receive_json() == {"type": "ready", "id": first}
        second = store.append_event(None, "config.changed", {"path": "second.yaml"})
        assert receive_event(socket)["data"]["path"] == "second.yaml"
        # Rotating the on-disk key invalidates the still-open signed cookie.
        (root / "secrets/web-admin-key").write_text("rotated-key", encoding="ascii")
        third = store.append_event(None, "config.changed", {"path": "secret.yaml"})
        event = receive_event(socket)
        assert event["id"] == third
        assert "path" not in event["data"]
    with admin.websocket_connect(f"/api/v1/events?after={first}") as socket:
        socket.receive_json()
        assert receive_event(socket)["id"] == second
        assert receive_event(socket)["id"] == third


def test_event_socket_rejects_origin_and_bad_cursor(client):
    for url, headers, code in [
        ("/api/v1/events", {"Origin": "http://evil.example"}, 4403),
        ("/api/v1/events?after=-1", {"Origin": "http://testserver"}, 4400),
        ("/api/v1/events?after=invalid", {"Origin": "http://testserver"}, 4400),
    ]:
        with (
            pytest.raises(WebSocketDisconnect) as error,
            client.websocket_connect(url, headers=headers),
        ):
            pass
        assert error.value.code == code


def test_event_socket_disallowed_anonymous(root):
    settings = Settings(
        server=ServerSettings(anonymous_access="disabled"),
        execution=ExecutionSettings(backend="subprocess"),
    )
    with TestClient(create_app(root, settings=settings, start_scheduler=False)) as client:
        with (
            pytest.raises(WebSocketDisconnect) as error,
            client.websocket_connect("/api/v1/events", headers={"Origin": "http://testserver"}),
        ):
            pass
        assert error.value.code == 4403


def test_event_socket_readonly_and_shutdown(client):
    with client.websocket_connect(
        "/api/v1/events", headers={"Origin": "http://testserver"}
    ) as socket:
        assert socket.receive_json()["type"] == "ready"
        client.app.state.shutdown_event.set()
        with pytest.raises(WebSocketDisconnect) as error:
            while True:
                socket.receive_json()
        assert error.value.code == 1001


def test_event_socket_full_readonly_projection(root):
    settings = Settings(
        server=ServerSettings(anonymous_access="readonly"),
        execution=ExecutionSettings(backend="subprocess"),
    )
    with TestClient(create_app(root, settings=settings, start_scheduler=False)) as client:
        event_id = client.app.state.store.append_event(
            None, "config.changed", {"path": "public.yaml"}
        )
        with client.websocket_connect(
            "/api/v1/events?after=0", headers={"Origin": "http://testserver"}
        ) as socket:
            socket.receive_json()
            event = receive_event(socket)
            assert event["id"] == event_id
            assert event["data"]["path"] == "public.yaml"
