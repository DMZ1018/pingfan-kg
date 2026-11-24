"""知识图谱可视化：按实体类型着色，节点大小按度数，输出 PNG。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib import font_manager

from common import FIG, OUT

FONT_CANDIDATES = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
FONT = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
FP = font_manager.FontProperties(fname=FONT) if FONT else None
plt.rcParams["axes.unicode_minus"] = False

COLORS = {
    "PER": "#e4572e", "LOC": "#3f88c5", "ORG": "#f5a623", "TIME": "#7b6d8d",
    "EVENT": "#2e933c", "POLICY": "#b23a48", "POS": "#8c8c8c", "NUM": "#5b8e7d",
    "DIS": "#c9ada7", "UNK": "#cccccc",
}
CN = {"PER": "人物", "LOC": "地点", "ORG": "机构", "TIME": "时间", "EVENT": "事件",
      "POLICY": "政策", "POS": "身份", "NUM": "数量", "DIS": "疾病", "UNK": "未登录"}


def load(name):
    d = json.loads((OUT / f"kg_{name}.json").read_text(encoding="utf-8"))
    G = nx.MultiDiGraph()
    for n in d["nodes"]:
        G.add_node(n["id"], type=n.get("type", "UNK"))
    for l in d["links"]:
        G.add_edge(l["source"], l["target"], rel=l["rel"])
    return G, d


def draw(G, title, path, seed=7, labels=True):
    simple = nx.Graph(G)
    pos = nx.kamada_kawai_layout(simple)
    # 轻微放大布局，缓解中心节点标签重叠
    pos = {n: (x * 1.15, y * 1.15) for n, (x, y) in pos.items()}
    deg = dict(G.degree())
    sizes = [220 + 55 * deg[n] for n in G.nodes()]
    colors = [COLORS.get(G.nodes[n].get("type", "UNK"), "#ccc") for n in G.nodes()]

    fig, ax = plt.subplots(figsize=(15, 10.5), dpi=200)
    ax.set_facecolor("#fbfbfb")
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color="#b9b9b9", width=0.9,
                           arrows=True, arrowsize=7, alpha=0.85, connectionstyle="arc3,rad=0.06")
    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=sizes, node_color=colors,
                           edgecolors="white", linewidths=1.2, alpha=0.95)
    if labels:
        for n, (x, y) in pos.items():
            t = G.nodes[n].get("type", "UNK")
            size = 220 + 55 * deg[n]
            off = 0.030 + size * 0.000022
            dy = off if t == "PER" else -off
            va = "bottom" if t == "PER" else "top"
            ax.text(x, y + dy, n, fontproperties=FP, fontsize=9, ha="center", va=va, color="#1a1a1a",
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.65))
    ax.set_title(title, fontproperties=FP, fontsize=16, pad=12)
    ax.axis("off")
    types = Counter(G.nodes[n].get("type", "UNK") for n in G.nodes())
    handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS.get(t, "#ccc"),
                          markersize=10, label=f"{CN.get(t, t)}({types[t]})") for t in types]
    ax.legend(handles=handles, loc="lower left", prop=FP, fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", path)


def ego(G, center, radius=2):
    nodes = nx.single_source_shortest_path_length(G.to_undirected(), center, cutoff=radius).keys()
    return G.subgraph(nodes).copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="llm")
    a = ap.parse_args()
    FIG.mkdir(exist_ok=True)
    for name, title in [("gold", "金标准知识图谱（人工标注 75 三元组）"),
                        ("llm", "LLM 抽取知识图谱（DeepSeek，77 三元组）"),
                        ("pipeline", "流水线知识图谱（词典 NER + 规则 RE，37 三元组）")]:
        p = OUT / f"kg_{name}.json"
        if not p.exists():
            continue
        G, d = load(name)
        draw(G, title, FIG / f"kg_{name}.png")
    G, _ = load("llm")
    if "孙少平" in G:
        sub = ego(G, "孙少平", 2)
        draw(sub, "孙少平的二跳关系网络（LLM 图谱）", FIG / "kg_ego_shaoping.png")


if __name__ == "__main__":
    main()
