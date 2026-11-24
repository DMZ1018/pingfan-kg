"""Cypher 图谱装载与查询基准。

本机未安装 Neo4j 服务端（无 Java、无 Docker，安装包下载被网络白名单阻断），
这里用同为 Cypher 查询语言的嵌入式图库 Kùzu 0.11 执行**同一套 Cypher**，
以验证语句正确性并给出 Cypher 引擎侧的装载/查询耗时；同时用 networkx 做内存对照。
生成的 out/kg_llm.cypher 可直接在 Neo4j Browser 中执行。
"""
from __future__ import annotations

import json
import shutil
import time

import networkx as nx

from common import OUT

DB = OUT / "kg.kuzu"

SCHEMA = [
    "CREATE NODE TABLE Entity(name STRING, type STRING, type_cn STRING, description STRING, PRIMARY KEY(name))",
    "CREATE REL TABLE REL(FROM Entity TO Entity, rel STRING, coarse STRING)",
]

Q_ONE_HOP = "MATCH (a:Entity {name: $n})-[:REL]->(b:Entity) RETURN b.name AS name, b.type AS t"
Q_TWO_HOP = "MATCH (a:Entity {name: $n})-[:REL]->(m:Entity)-[:REL]->(b:Entity) RETURN DISTINCT b.name AS name LIMIT 50"
Q_DEGREE = "MATCH (a:Entity)-[r:REL]->() RETURN a.name AS name, count(r) AS deg ORDER BY deg DESC LIMIT 10"
Q_REL_DIST = "MATCH ()-[r:REL]->() RETURN r.rel AS rel, count(*) AS c ORDER BY c DESC"
Q_TYPE_DIST = "MATCH (a:Entity) RETURN a.type AS t, count(*) AS c ORDER BY c DESC"


def build_kuzu(kg):
    import kuzu

    # 中文路径会让 Kùzu 的 C++ 层按本地编码解析失败，这里用内存库；
    # 装载逻辑与落盘库完全一致，只是不计磁盘 I/O。
    db = kuzu.Database(":memory:")
    conn = kuzu.Connection(db)
    for s in SCHEMA:
        conn.execute(s)
    t0 = time.perf_counter()
    for n in kg["nodes"]:
        conn.execute("CREATE (:Entity {name: $n, type: $t, type_cn: $tc, description: $d})",
                     {"n": n["id"], "t": n.get("type", "UNK"), "tc": n.get("type_cn", ""), "d": (n.get("desc") or "")[:200]})
    for l in kg["links"]:
        conn.execute("MATCH (a:Entity {name: $h}), (b:Entity {name: $t}) "
                     "CREATE (a)-[:REL {rel: $r, coarse: $c}]->(b)",
                     {"h": l["source"], "t": l["target"], "r": l["rel"], "c": l["coarse"]})
    return conn, time.perf_counter() - t0


def timeit(fn, repeat=20):
    ts = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    return {"avg_ms": round(sum(ts) / len(ts), 3), "p50_ms": round(ts[len(ts) // 2], 3), "min_ms": round(ts[0], 3)}


def main():
    msg = json.loads((OUT / "kg_llm.json").read_text(encoding="utf-8"))
    G = nx.MultiDiGraph()
    for n in msg["nodes"]:
        G.add_node(n["id"], type=n.get("type"))
    for l in msg["links"]:
        G.add_edge(l["source"], l["target"], rel=l["rel"])

    out = {"engine": "kuzu 0.11.3 (Cypher)", "neo4j_server": "unavailable"}
    try:
        conn, load_s = build_kuzu(msg)
        out["load_seconds"] = round(load_s, 3)
        out["counts"] = {
            "nodes": conn.execute("MATCH (a:Entity) RETURN count(a)").get_next()[0],
            "edges": conn.execute("MATCH ()-[r:REL]->() RETURN count(r)").get_next()[0],
        }
        checks = {
            "one_hop_sort": (Q_ONE_HOP, {"n": "孙少平"}),
            "two_hop_sort": (Q_TWO_HOP, {"n": "孙少平"}),
            "degree_top": (Q_DEGREE, {}),
            "rel_dist": (Q_REL_DIST, {}),
            "type_dist": (Q_TYPE_DIST, {}),
        }
        out["queries"] = {}
        for name, (q, params) in checks.items():
            res = conn.execute(q, params)
            rows = []
            while res.has_next():
                rows.append(res.get_next())
            out["queries"][name] = {"rows": len(rows), "sample": rows[:5],
                                    "latency": timeit(lambda q=q, p=params: _drain(conn, q, p))}
    except Exception as e:  # 记录失败原因而不是伪造数据
        out["kuzu_error"] = f"{type(e).__name__}: {e}"

    # networkx 对照
    def nx_one():
        list(G.successors("孙少平"))

    def nx_two():
        nx.single_source_shortest_path_length(G, "孙少平", cutoff=2)

    def nx_deg():
        sorted(G.degree, key=lambda x: -x[1])[:10]

    def nx_rel():
        from collections import Counter
        Counter(d["rel"] for _, _, d in G.edges(data=True)).most_common()

    out["networkx"] = {
        "one_hop": timeit(nx_one), "two_hop": timeit(nx_two),
        "degree_top": timeit(nx_deg), "rel_dist": timeit(nx_rel),
    }
    (OUT / "kg_bench.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


def _drain(conn, q, p):
    res = conn.execute(q, p)
    n = 0
    while res.has_next():
        res.get_next()
        n += 1
    return n


if __name__ == "__main__":
    main()


