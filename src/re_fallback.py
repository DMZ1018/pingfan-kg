"""无 spaCy 时的等价规则引擎：词典最长匹配 + re_rules 触发词。"""
from __future__ import annotations

import json

from common import DATA

_CACHE = {}


def _surfaces():
    if "s" not in _CACHE:
        d = json.loads((DATA / "dict" / "entity_dict.json").read_text(encoding="utf-8"))
        surf = []
        for e in d["entities"]:
            surf.append((e["name"], e["type"]))
            for a in e["aliases"]:
                surf.append((a, e["type"]))
        seen, uniq = set(), []
        for s, t in surf:
            if s not in seen:
                seen.add(s)
                uniq.append((s, t))
        uniq.sort(key=lambda x: len(x[0]), reverse=True)
        _CACHE["s"] = uniq
    return _CACHE["s"]


def match_entities(text: str):
    taken = [False] * len(text)
    ents = []
    for s, t in _surfaces():
        start = 0
        while True:
            i = text.find(s, start)
            if i < 0:
                break
            j = i + len(s)
            if not any(taken[i:j]):
                ents.append((i, j, s, t))
                for k in range(i, j):
                    taken[k] = True
            start = i + 1
    return sorted(ents, key=lambda x: x[0])


def fallback_extract(text: str):
    from re_rules import apply_rules

    return apply_rules(text, match_entities(text))
