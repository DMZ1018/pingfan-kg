"""基线：最长匹配的词典/规则实体识别。"""
from __future__ import annotations

import json

from common import DATA, Span, load_sentences


def load_surfaces():
    d = json.loads((DATA / "dict" / "entity_dict.json").read_text(encoding="utf-8"))
    surf = []
    for e in d["entities"]:
        surf.append((e["name"], e["type"]))
        for a in e["aliases"]:
            surf.append((a, e["type"]))
    # 同一表层取第一条（别名冲突时可在此人工裁决）
    seen, uniq = set(), []
    for s, t in surf:
        if s in seen:
            continue
        seen.add(s)
        uniq.append((s, t))
    uniq.sort(key=lambda x: len(x[0]), reverse=True)
    return uniq


def extract(text: str, surfaces) -> list[Span]:
    taken = [False] * len(text)
    spans = []
    for s, t in surfaces:
        start = 0
        while True:
            i = text.find(s, start)
            if i < 0:
                break
            j = i + len(s)
            if not any(taken[i:j]):
                spans.append(Span(i, j, s, t))
                for k in range(i, j):
                    taken[k] = True
            start = i + 1
    return sorted(spans, key=lambda x: x.start)


def main():
    sents = load_sentences()
    surfaces = load_surfaces()
    out = [{"sid": s.sid, "spans": [[p.start, p.end, p.text, p.type] for p in extract(s.text, surfaces)]} for s in sents]
    (DATA.parent / "out" / "pred_dict_rule.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("dict baseline done", sum(len(o["spans"]) for o in out))


if __name__ == "__main__":
    main()
