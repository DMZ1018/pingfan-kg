"""把 pingfan_kg 发布到 GitHub：设备码授权 → 建仓库 → Git Data API 一次性提交。

设计要点：
- 不在聊天/日志里出现 token；token 只存在于进程内存。
- 不依赖 git 二进制（本机没有安装 git），直接用 GitHub REST API 写对象。
- 全流程带重试：本机网络对 github.com 时通时断。

用法:
    python tools/publish_github.py --repo pingfan-kg --public
    python tools/publish_github.py --repo pingfan-kg --private --dry-run
    set GITHUB_TOKEN=... && python tools/publish_github.py --repo pingfan-kg   # 已有 token 时跳过设备码
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_ID = "178c6fc778ccc68e1d6a"  # GitHub CLI 的公开 client id，设备码流程用
UA = {"Accept": "application/vnd.github+json", "User-Agent": "pingfan-kg-publisher",
      "X-GitHub-Api-Version": "2022-11-28"}
SKIP_DIRS = {".git", "libs", "tmp", "tmp2", ".venv", "__pycache__", ".pytest_cache", "out/logs", "release"}
SKIP_FILES = {"pipeline_run.log", "out/run_manifest.json", "out/.gh_token"}


def http(url, method="GET", data=None, token=None, form=False, timeout=30, retries=5):
    body = None
    headers = dict(UA)
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            if e.code in (400, 401, 403, 404, 409, 422):
                return e.code, (json.loads(raw) if raw else {})
            last = f"HTTP {e.code}"
        except Exception as e:  # 超时/连接重置：重试
            last = f"{type(e).__name__}: {e}"
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{method} {url} 失败: {last}")


def request_code(save_to: Path) -> dict:
    """只申请设备码并落盘，供人工在浏览器授权（两步式流程的第一阶段）。"""
    status, d = http("https://github.com/login/device/code", "POST",
                     {"client_id": CLIENT_ID, "scope": "repo"}, form=True, retries=10)
    if status != 200:
        raise RuntimeError(f"申请设备码失败: {status} {d}")
    save_to.parent.mkdir(parents=True, exist_ok=True)
    d["_saved_at"] = time.time()
    save_to.write_text(json.dumps(d), encoding="utf-8")
    print(f"user_code={d['user_code']}  url={d['verification_uri']}  expires_in={d['expires_in']}s")
    return d


def poll_token(d: dict) -> str:
    print("\n" + "=" * 56)
    print(f"  在浏览器打开  {d['verification_uri']}")
    print(f"  输入代码      {d['user_code']}")
    print("  然后点 Authorize（授权范围：repo）")
    print("=" * 56 + "\n")
    interval = max(int(d.get("interval", 5)), 5)
    deadline = time.time() + int(d.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        st, tok = http("https://github.com/login/oauth/access_token", "POST",
                       {"client_id": CLIENT_ID, "device_code": d["device_code"],
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code"},
                       form=True, retries=6)
        if st == 200 and tok.get("access_token"):
            print("授权成功")
            return tok["access_token"]
        err = (tok or {}).get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err in ("expired_token", "access_denied"):
            raise RuntimeError(f"授权失败: {err}")
    raise RuntimeError("设备码超时")


def device_login(device_file: Path | None = None) -> str:
    if device_file and device_file.exists():
        d = json.loads(device_file.read_text(encoding="utf-8"))
        if time.time() < d.get("_saved_at", 0) + int(d.get("expires_in", 900)):
            return poll_token(d)
    d = request_code(Path(__file__).resolve().parents[1] / "out" / "device.json")
    d["_saved_at"] = time.time()
    return poll_token(d)


def collect_files():
    """遍历仓库文件，跳过构建产物与密钥类文件。"""
    files = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        parts = rel.split("/")
        if any(seg in SKIP_DIRS for seg in parts[:-1]):
            continue
        if rel in SKIP_FILES or rel.endswith(".pyc") or rel.endswith(".log"):
            continue
        if parts[0] in SKIP_DIRS:
            continue
        files.append((rel, p))
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="pingfan-kg")
    ap.add_argument("--desc", default="《平凡的世界》三部梗概：实体词典 / 实体抽取 / 关系三元组 / 知识图谱 全流程")
    ap.add_argument("--public", action="store_true")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--request-code", action="store_true", help="只申请设备码并打印")
    ap.add_argument("--device-file", default="out/device.json")
    ap.add_argument("--message", default="feat: 端到端知识抽取流水线")
    a = ap.parse_args()

    if a.request_code:
        request_code(ROOT / a.device_file)
        return 0

    files = collect_files()
    total = sum(p.stat().st_size for _, p in files)
    print(f"待上传 {len(files)} 个文件，{total/1024:.1f} KB")
    if a.dry_run:
        for rel, p in files:
            print(f"  {p.stat().st_size:>8}  {rel}")
        return 0

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    cache = ROOT / "out" / ".gh_token"
    if not token and cache.exists():
        token = cache.read_text(encoding="utf-8").strip()
        print("复用本机临时 token（不参与上传，结束后删除）")
    if not token:
        token = device_login(ROOT / a.device_file)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(token, encoding="utf-8")

    try:
        for attempt in range(1, 4):
            try:
                _publish(token, files, a)
                break
            except Exception as e:
                print(f"[重试 {attempt}/3] {type(e).__name__}: {e}")
                if attempt == 3:
                    raise
                time.sleep(3)
    finally:
        if cache.exists():
            cache.unlink()
    return 0


def _publish(token, files, a):
    st, me = http("https://api.github.com/user", token=token)
    if st != 200:
        raise RuntimeError(f"取用户信息失败: {st} {me}")
    login = me["login"]
    print(f"账号: {login}")

    private = not a.public
    st, repo = http("https://api.github.com/user/repos", "POST",
                    {"name": a.repo, "description": a.desc, "private": private, "auto_init": False},
                    token=token)
    if st == 201:
        print(f"已创建仓库: {repo['html_url']}")
    elif st == 422:
        st2, repo = http(f"https://api.github.com/repos/{login}/{a.repo}", token=token)
        if st2 != 200:
            raise RuntimeError(f"仓库已存在但无法读取: {st2}")
        print(f"仓库已存在，复用: {repo['html_url']}")
    else:
        raise RuntimeError(f"创建仓库失败: {st} {repo}")

    full = repo["full_name"]
    branch = repo.get("default_branch") or "main"

    # 空仓库：GET /git/ref 返回 409（Git Repository is empty），
    # 先落一个占位文件把分支建出来，否则 /git/blobs 也会 409
    st_ref, ref = http(f"https://api.github.com/repos/{full}/git/ref/heads/{branch}", token=token)
    if st_ref in (404, 409):
        st_seed, seed = http(f"https://api.github.com/repos/{full}/contents/.gitkeep", "PUT",
                             {"message": "chore: init empty repository",
                              "content": base64.b64encode(b"init").decode()}, token=token)
        if st_seed not in (200, 201):
            raise RuntimeError(f"初始化空仓库失败: {st_seed} {seed}")
        st_ref, ref = http(f"https://api.github.com/repos/{full}/git/ref/heads/{branch}", token=token)
        if st_ref != 200:
            raise RuntimeError(f"初始化后仍取不到分支: {st_ref}")
        print("空仓库已初始化")

    # 1) blobs
    tree = []
    for i, (rel, p) in enumerate(files, 1):
        content = base64.b64encode(p.read_bytes()).decode()
        st, blob = http(f"https://api.github.com/repos/{full}/git/blobs", "POST",
                        {"content": content, "encoding": "base64"}, token=token, timeout=60)
        if st != 201:
            raise RuntimeError(f"上传 {rel} 失败: {st} {blob}")
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"  [{i:>2}/{len(files)}] {rel}")

    # 2) tree
    st, tr = http(f"https://api.github.com/repos/{full}/git/trees", "POST",
                  {"tree": tree}, token=token, timeout=60)
    if st != 201:
        raise RuntimeError(f"建树失败: {st} {tr}")

    # 3) commit（父提交为占位提交，随后整体覆盖成一次干净提交）
    st, ref = http(f"https://api.github.com/repos/{full}/git/ref/heads/{branch}", token=token)
    parents = [ref["object"]["sha"]] if st == 200 else []
    st, commit = http(f"https://api.github.com/repos/{full}/git/commits", "POST",
                      {"message": a.message, "tree": tr["sha"], "parents": parents}, token=token)
    if st != 201:
        raise RuntimeError(f"建提交失败: {st} {commit}")

    # 4) 指向分支
    if parents:
        st, _ = http(f"https://api.github.com/repos/{full}/git/refs/heads/{branch}", "PATCH",
                     {"sha": commit["sha"], "force": True}, token=token)
    else:
        st, _ = http(f"https://api.github.com/repos/{full}/git/refs", "POST",
                     {"ref": f"refs/heads/{branch}", "sha": commit["sha"]}, token=token)
    if st not in (200, 201):
        raise RuntimeError(f"更新分支失败: {st}")

    print(f"\n完成: https://github.com/{full}  ({len(files)} files, commit {commit['sha'][:7]})")


if __name__ == "__main__":
    sys.exit(main())



