"""探测 GitHub API 各端点可达性（只读，不创建任何资源）。"""
import json
import urllib.error
import urllib.request

H = {"Accept": "application/json", "User-Agent": "pingfan-kg-probe"}


def t(url, method="GET", data=None, timeout=12):
    try:
        req = urllib.request.Request(url, data=data, method=method, headers=H)
        r = urllib.request.urlopen(req, timeout=timeout)
        return f"{r.status} {r.read(60)[:60]!r}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} {e.read(80)[:80]!r}"
    except Exception as e:
        return f"FAIL {type(e).__name__}"


if __name__ == "__main__":
    cases = [
        ("GET", "https://api.github.com/zen", None),
        ("GET", "https://api.github.com/rate_limit", None),
        ("GET", "https://api.github.com/repos/octocat/Hello-World", None),
        ("POST", "https://api.github.com/zen", b"{}"),
        ("POST", "https://api.github.com/user/repos", json.dumps({"name": "probe-only"}).encode()),
        ("POST", "https://github.com/login/device/code", b"client_id=178c6fc778ccc68e1d6a&scope=repo"),
    ]
    for m, u, d in cases:
        print(f"{m:<5} {u:<50} {t(u, m, d)}")
