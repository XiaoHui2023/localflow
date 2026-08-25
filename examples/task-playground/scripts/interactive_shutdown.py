from __future__ import annotations

import signal
import sys
import threading
import time
from queue import Empty, Queue

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

stopping = False
commands: Queue[str | None] = Queue()


def request_stop(_signum: int, _frame: object) -> None:
    global stopping
    stopping = True
    print("已收到 Ctrl+C，请输入 status、resume 或 quit", flush=True)


signal.signal(signal.SIGINT, request_stop)
if hasattr(signal, "SIGBREAK"):
    signal.signal(signal.SIGBREAK, request_stop)


def read_commands() -> None:
    pending = bytearray()
    while True:
        value = sys.stdin.buffer.read(1)
        if value == b"":
            commands.put(None)
            return
        if value == b"\x03":
            commands.put("\x03")
        elif value == b"\n":
            command = pending.decode("utf-8", errors="replace").strip().lower()
            commands.put(command)
            pending.clear()
            if command == "quit":
                return
        elif value != b"\r":
            pending.extend(value)


threading.Thread(target=read_commands, name="terminal-input", daemon=True).start()
print("交互程序已启动；可输入 echo <内容>，Ctrl+C 进入控制模式，Ctrl+D 直接退出", flush=True)
while True:
    try:
        command = commands.get(timeout=0.5)
    except Empty:
        command = ""
    if command is None:
        print("已收到 Ctrl+D，立即退出", flush=True)
        raise SystemExit(0)
    if command == "\x03":
        request_stop(0, None)
        continue
    if command:
        if command == "quit":
            print("正在保存状态…", flush=True)
            time.sleep(1)
            print("保存完成，正常退出", flush=True)
            raise SystemExit(0)
        if command == "status":
            print("状态：等待交互决定" if stopping else "状态：工作中", flush=True)
            continue
        if command == "resume":
            stopping = False
            print("已继续运行", flush=True)
            continue
        if command.startswith("echo "):
            print(f"收到：{command[5:]}", flush=True)
            continue
        print("未识别，请输入 echo <内容>、status、resume 或 quit", flush=True)
    if not stopping:
        print("工作中…", flush=True)
