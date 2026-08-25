"""打印一个随机数，然后正常结束。"""

import secrets
import sys

sys.stdout.reconfigure(encoding="utf-8")


print(f"本次随机数：{secrets.randbelow(100) + 1}", flush=True)
