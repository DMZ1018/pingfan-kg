"""把词典全表与三元组全表注入总报告（幂等：只在占位符存在时替换）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from common import REL2COARSE  # noqa: E402

REPORT = ROOT / "reports" / "00_全流程总报告.md"
dict_data = json.loads((ROOT / "data" / "dict" / "entity_dict.json").read_text(encoding="utf-8"))

rows = ["| eid | 词条 | 类型 | 别名 | 频次 | 首现句 | 释义 |", "|---|---|---|---|---|---|---|"]
for e in dict_data["entities"]:
    aliases = "、".join(e["aliases"]) if e["aliases"] else "—"
    rows.append(f"| {e['eid']} | **{e['name']}** | {e['type_cn']} | {aliases} | {e['freq']} | {e['first_sid']} | {e['desc']} |")
dict_table = "\n".join(rows)

tri = json.loads((ROOT / "data" / "llm" / "triples.json").read_text(encoding="utf-8"))
rows = ["| # | 句子 | 头实体 | 关系 | 尾实体 | 粗类 |", "|---|---|---|---|---|---|"]
n = 0
for item in tri:
    for h, r, t in item["triples"]:
        n += 1
        rows.append(f"| {n} | {item['sid']} | {h} | {r} | {t} | {REL2COARSE.get(r, r)} |")
triple_table = "\n".join(rows)

txt = REPORT.read_text(encoding="utf-8")
if "<!--DICT_TABLE_ALL-->" in txt:
    txt = txt.replace("<!--DICT_TABLE_ALL-->", dict_table)
if "<!--TRIPLE_TABLE_ALL-->" in txt:
    txt = txt.replace("<!--TRIPLE_TABLE_ALL-->", triple_table)
REPORT.write_text(txt, encoding="utf-8")
print(f"dict rows={len(dict_data['entities'])}, triples={n}, size={len(txt)} chars")
