"""知识图谱构建：把三元组落成属性图，导出 JSON/GraphML/Cypher，并统计规模与质量。

用法:
    python src/build_kg.py --src data/llm/triples.json --name llm
    python src/build_kg.py --src out/pred_re_spacy.json --name pipeline
    python src/build_kg.py --src data/gold/triples.json --name gold
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import networkx as nx

from common import DATA, OUT, REL2COARSE, canon, load_dict


def load_triples(path):
    raw = json.loads(open(path, encoding="utf-8").read())
    if isinstance(raw, dict) and "data" in raw:
        rows = raw["data"]
    else:
        rows = raw
    out = []
    for r in rows:
        for t in r.get("triples", []):
            out.append((r["sid"], t[0], t[1], t[2]))
    return out


def build(triples, edges_meta=None):
    d = load_dict()
    by_name = {e["name"]: e for e in d["entities"]}
    G = nx.MultiDiGraph()
    for e in d["entities"]:
        G.add_node(e["name"], type=e["type"], type_cn=e["type_cn"], desc=e["desc"], freq=e["freq"], eid=e["eid"])
    for sid, h, r, t in triples:
        h, t = canon(h), canon(t)
        for n in (h, t):
            if n not in G:
                G.add_node(n, type="UNK", type_cn="未登录", desc="", freq=0, eid="")
        G.add_edge(h, t, rel=r, coarse=REL2COARSE.get(r, "其他"), sid=sid)
    # 只保留出现在三元组中的节点（词典词条作为候选集，不全部上图）
    used = {canon(n) for _, h, _, t in triples for n in (h, t)}
    H = G.subgraph(used).copy()
    return H


def stats(G: nx.MultiDiGraph):
    rels = Counter(d["rel"] for _, _, d in G.edges(data=True))
    coarse = Counter(d["coarse"] for _, _, d in G.edges(data=True))
    types = Counter(nx.get_node_attributes(G, "type").values())
    iso = [n for n in G if G.degree(n) == 0]
    deg = dict(G.degree())
    top = sorted(deg.items(), key=lambda x: -x[1])[:10]
    und = nx.Graph(G)  # 无向简单图，用于密度/聚类系数
    comps = list(nx.connected_components(und)) if G.number_of_nodes() else []
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": round(nx.density(und), 4) if und.number_of_nodes() > 1 else 0,
        "avg_degree": round(sum(deg.values()) / len(deg), 2) if deg else 0,
        "max_degree": max(deg.values()) if deg else 0,
        "isolated": len(iso),
        "n_relation_types": len(rels),
        "n_coarse_types": len(coarse),
        "node_types": dict(types),
        "relation_types": dict(rels.most_common()),
        "coarse_types": dict(coarse.most_common()),
        "top_nodes": [{"name": n, "degree": k} for n, k in top],
        "components": len(comps),
        "largest_component": max((len(c) for c in comps), default=0),
        "avg_clustering": round(nx.average_clustering(und), 4) if und.number_of_nodes() > 1 else 0,
    }


def to_cypher(G: nx.MultiDiGraph, path):
    lines = [
        "// 自动生成：先建约束，再逐条 MERGE 节点与关系",
        "CREATE CONSTRAINT ent_name IF NOT EXISTS FOR (n:Entity) REQUIRE n.name IS UNIQUE;",
        "",
    ]
    for n, d in G.nodes(data=True):
        lines.append(
            f'MERGE (n:Entity {{name: "{n}"}}) SET n.type = "{d.get("type","UNK")}", n.type_cn = "{d.get("type_cn","")}", n.description = "{d.get("desc","").replace(chr(34), chr(39))}";'
        )
    lines.append("")
    for h, t, d in G.edges(data=True):
        rel = d["rel"].replace('"', "")
        lines.append(f'MATCH (a:Entity {{name: "{h}"}}), (b:Entity {{name: "{t}"}}) MERGE (a)-[:`{rel}`]->(b);')
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    triples = load_triples(a.src)
    G = build(triples)
    st = stats(G)
    st["source"] = a.src
    st["n_triples"] = len(triples)
    OUT.mkdir(exist_ok=True)
    (OUT / f"kg_{a.name}.json").write_text(
        json.dumps({"stats": st,
                    "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
                    "links": [{"source": h, "target": t, "rel": d["rel"], "coarse": d["coarse"]} for h, t, d in G.edges(data=True)]},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / f"kg_{a.name}.graphml").write_text("\n".join(nx.generate_graphml(G)), encoding="utf-8")
    (OUT / f"kg_{a.name}.cypher").write_text("", encoding="utf-8")
    to_cypher(G, OUT / f"kg_{a.name}.cypher")
    print(json.dumps(st, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

