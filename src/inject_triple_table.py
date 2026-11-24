"""把 LLM 三元组渲染成 Markdown 表格并注入报告。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tr = json.loads((ROOT / "data" / "llm" / "triples.json").read_text(encoding="utf-8"))

import sys
sys.path.insert(0, str(ROOT / "src"))
from common import REL2COARSE  # noqa: E402

rows = ["| # | 句子 | 头实体 | 关系 | 尾实体 | 粗类 |", "|---|---|---|---|---|---|"]
n = 0
for item in tr:
    for h, r, t in item["triples"]:
        n += 1
        rows.append(f"| {n} | {item['sid']} | {h} | {r} | {t} | {REL2COARSE.get(r, r)} |")

p = ROOT / "reports" / "03_关系三元组.md"
txt = p.read_text(encoding="utf-8").replace("<!--TRIPLE_TABLE-->", "\n".join(rows))
p.write_text(txt, encoding="utf-8")
print("injected triples:", n)
