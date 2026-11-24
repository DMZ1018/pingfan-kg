"""快速申请设备码：短超时 + 连接复用，专治 github.com 时通时断。"""
import json
import sys
import time

import requests

URL = "https://github.com/login/device/code"
DATA = {"client_id": "178c6fc778ccc68e1d6a", "scope": "repo"}
HEAD = {"Accept": "application/json", "User-Agent": "pingfan-kg"}

s = requests.Session()
s.headers.update(HEAD)
for i in range(30):
    try:
        r = s.post(URL, data=DATA, timeout=8)
        if r.status_code == 200:
            d = r.json()
            d["_saved_at"] = time.time()
            open("out/device4.json", "w", encoding="utf-8").write(json.dumps(d))
            print(f"OK {d['user_code']} {d['verification_uri']} expires={d['expires_in']}")
            sys.exit(0)
        print(f"HTTP {r.status_code}", flush=True)
    except Exception as e:
        print(f"[{i+1}] {type(e).__name__}", flush=True)
    time.sleep(1)
print("FAILED")
sys.exit(1)
