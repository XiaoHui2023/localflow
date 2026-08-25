from __future__ import annotations

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--result", choices=["clean", "warning", "rejected"], default="clean")
args = parser.parse_args()
codes = {"clean": 0, "warning": 2, "rejected": 3}
print(f"result={args.result}", flush=True)
raise SystemExit(codes[args.result])
