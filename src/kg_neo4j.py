"""Neo4j 装载与查询（需要本地 Neo4j 5.x 服务 + neo4j 驱动）。

用法:
    set NEO4J_URI=bolt://localhost:7687
    set NEO4J_USER=neo4j
    set NEO4J_PASSWORD=******
    python src/kg_neo4j.py --cypher out/kg_llm.cypher

本机没有安装 Neo4j（无 Java、无 Docker，安装包下载被网络白名单阻断），
所以脚本会先探测驱动与服务，探测失败时打印安装指引并退出，
不会伪造"已连通"的结果。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def split_statements(text: str):
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    body = "\n".join(lines)
    return [s.strip() for s in body.split(";") if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cypher", default=str(ROOT / "out" / "kg_llm.cypher"))
    ap.add_argument("--query", default="MATCH (n:Entity) RETURN count(n) AS nodes")
    a = ap.parse_args()

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[跳过] 未安装 neo4j 驱动：python -m pip install neo4j")
        print("       （本机 PyPI 下载受限，安装步骤见 README 的“环境说明”）")
        return 1

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        driver.verify_connectivity()
    except Exception as e:
        print(f"[跳过] 无法连接 {uri}：{type(e).__name__}: {e}")
        return 1

    stmts = split_statements(Path(a.cypher).read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    with driver.session() as s:
        for st in stmts:
            s.run(st)
    load_s = time.perf_counter() - t0
    with driver.session() as s:
        rec = s.run(a.query).single()
    print(f"装载 {len(stmts)} 条语句，用时 {load_s:.2f}s；查询结果 {dict(rec) if rec else None}")
    driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
