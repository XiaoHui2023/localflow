from __future__ import annotations

from automation.script.runner import on_script_finished

from run_history import record_from_script

on_script_finished(record_from_script)
