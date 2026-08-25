from __future__ import annotations

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--result", choices=["clean", "warning", "rejected"], default="clean")
result = parser.parse_args().result
print(f"检查结果：{result}", flush=True)
raise SystemExit({"clean": 0, "warning": 2, "rejected": 3}[result])
