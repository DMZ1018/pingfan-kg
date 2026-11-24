"""修正两处实体标注的出现序号：
P1-S03 的“晓霞”是第 2 次出现（第 1 次在“田晓霞”内部）；
P3-S02 的“少平”是第 3 次出现（前两次都在“孙少平”内部）。
"""
import json
import pathlib

FIXES = {
    "P1-S03": {"晓霞": ["晓霞", "PER", 2]},
    "P3-S02": {"少平": ["少平", "PER", 3]},
}

for path in ["data/gold/annotations.json", "data/llm/ner.json"]:
    p = pathlib.Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    for item in data:
        for surface, new in FIXES.get(item["sid"], {}).items():
            for i, e in enumerate(item["entities"]):
                if e[0] == surface and (len(e) == 2 or e[2] == 1):
                    item["entities"][i] = new
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("fixed", path)
