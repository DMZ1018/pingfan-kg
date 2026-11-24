"""把实体词典渲染成 Markdown 表格并注入报告。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "data" / "dict" / "entity_dict.json").read_text(encoding="utf-8"))

lines = ["| eid | 词条 | 类型 | 别名 | 频次 | 首现句 | 释义 |", "|---|---|---|---|---|---|---|"]
for e in d["entities"]:
    aliases = "、".join(e["aliases"]) if e["aliases"] else "—"
    desc = e["desc"].replace("|", "\\|")
    lines.append(f"| {e['eid']} | **{e['name']}** | {e['type_cn']} | {aliases} | {e['freq']} | {e['first_sid']} | {desc} |")
table = "\n".join(lines)

p = ROOT / "reports" / "01_实体词典.md"
txt = p.read_text(encoding="utf-8")
txt = txt.replace("<!--DICT_TABLE-->", table)
p.write_text(txt, encoding="utf-8")
print("injected rows:", len(lines) - 2)
