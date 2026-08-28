#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT/runtime/localflow.pid"
[[ -r "$PID_FILE" ]] || { echo "LocalFlow is not running"; exit 0; }
PID="$(tr -d '[:space:]' < "$PID_FILE")"
[[ "$PID" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid LocalFlow PID file" >&2; exit 1; }
[[ -d "/proc/$PID" ]] || { rm -f "$PID_FILE"; echo "LocalFlow is not running"; exit 0; }
PROCESS_ROOT="$(readlink -f "/proc/$PID/cwd")"
[[ "$PROCESS_ROOT" == "$ROOT" ]] || { echo "PID does not belong to this LocalFlow directory" >&2; exit 1; }

kill -USR1 "$PID"
for _ in $(seq 1 900); do
  kill -0 "$PID" 2>/dev/null || { echo "LocalFlow stopped cleanly"; exit 0; }
  sleep 0.1
done
echo "LocalFlow is still cleaning task processes; the controller remains alive to prevent orphaning them" >&2
exit 1
