from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("--case", required=True)
parser.add_argument("--seed", required=True, type=int)
parser.add_argument("--compile-log")
parser.add_argument("--run-log")
args = parser.parse_args()
random.seed(args.seed)
score = random.randint(90, 100)
time.sleep(0.6)
compile_log = Path(args.compile_log) if args.compile_log else None
run_log = Path(args.run_log) if args.run_log else None
if run_log:
    run_log.unlink(missing_ok=True)
if compile_log:
    compile_log.parent.mkdir(parents=True, exist_ok=True)
    compile_log.write_text("Compiler version demo\nCompile completed\n", encoding="utf-8")
if score == 90:
    if compile_log:
        compile_log.write_text("Error-[DEMO] compile failed\n", encoding="utf-8")
    print(f"case={args.case} seed={args.seed} compile failed", flush=True)
    raise SystemExit(1)
fatal = 1 if score == 91 else 0
errors = 1 if score == 92 else 0
if run_log:
    run_log.parent.mkdir(parents=True, exist_ok=True)
    run_log.write_text(
        "--- UVM Report Summary ---\n"
        "UVM_INFO : 12\n"
        "UVM_WARNING : 0\n"
        f"UVM_ERROR : {errors}\n"
        f"UVM_FATAL : {fatal}\n",
        encoding="utf-8",
    )
print(f"case={args.case} seed={args.seed} score={score}", flush=True)
raise SystemExit(0 if not errors and not fatal else 2)
