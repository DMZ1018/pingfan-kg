"""公共层：路径、语料加载、实体/关系标注结构、评价指标。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
FIG = ROOT / "figures"
REPORT = ROOT / "reports"

TYPES = ["PER", "LOC", "ORG", "TIME", "EVENT", "POLICY", "POS", "NUM", "DIS"]
TYPE_CN = {
    "PER": "人物",
    "LOC": "地点",
    "ORG": "机构",
    "TIME": "时间",
    "EVENT": "事件",
    "POLICY": "政策/运动",
    "POS": "身份/职务",
    "NUM": "数量",
    "DIS": "疾病",
}

# 细粒度谓词 -> 10 类粗粒度关系（供关系分类器与统一评测）
REL2COARSE = {
    "夫妻": "婚恋", "恋人": "婚恋", "恋爱": "婚恋", "爱慕": "婚恋",
    "青梅竹马": "婚恋", "相亲": "婚恋", "表白": "婚恋",
    "父亲": "亲属", "父女": "亲属", "兄弟": "亲属", "姐弟": "亲属",
    "兄妹": "亲属", "母子": "亲属", "父子": "亲属",
    "同学": "社交", "朋友": "社交", "遇见": "社交", "邂逅": "社交",
    "介绍": "社交", "相识": "社交",
    "任职于": "任职", "担任": "任职", "职务": "任职", "成为": "任职",
    "身份": "任职", "毕业": "任职", "就读于": "任职",
    "到": "空间", "回到": "空间", "发生于": "空间", "牺牲于": "空间",
    "受伤于": "空间", "居住于": "空间", "位于": "空间",
    "领导": "组织", "组织": "组织", "召开": "组织", "推行": "组织",
    "实行": "组织", "推广": "组织", "抵制": "组织", "反对": "组织",
    "抵触": "组织", "破坏": "组织", "抢水": "组织", "加入": "组织",
    "帮助": "支持", "救助": "支持", "救": "支持", "出资": "支持",
    "通知": "支持", "承认": "支持", "支持": "支持", "资助": "支持",
    "揭发": "冲突", "拒绝": "冲突", "告发": "冲突", "批判": "冲突",
    "建": "经营", "经营": "经营", "扩建": "经营", "生产": "经营",
    "贷款": "经营", "属于": "归属", "隶属": "归属",
    "确诊": "事件", "牺牲": "事件", "受伤": "事件", "致残": "事件",
    "结婚": "婚恋", "离婚": "婚恋", "去世": "事件",
}
COARSE_RELS = ["婚恋", "亲属", "社交", "任职", "空间", "组织", "支持", "冲突", "经营", "归属", "事件"]


@dataclass
class Span:
    start: int
    end: int
    text: str
    type: str
    eid: str = ""

    def key(self):
        return (self.start, self.end, self.type)


@dataclass
class Sentence:
    sid: str
    part: int
    text: str
    spans: list[Span] = field(default_factory=list)
    triples: list[tuple] = field(default_factory=list)  # (head, rel, tail, coref)


def load_dict(path: Path | None = None) -> dict:
    path = path or DATA / "dict" / "entity_dict.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_alias_index(d: dict) -> dict[str, str]:
    """别名/全名 -> 实体 id。"""
    idx = {}
    for ent in d["entities"]:
        idx[ent["name"]] = ent["eid"]
        for a in ent.get("aliases", []):
            idx.setdefault(a, ent["eid"])
    return idx


def build_name_index(d: dict) -> dict[str, str]:
    """别名 -> 规范名，用于把“少平/晓霞”归一到“孙少平/田晓霞”。"""
    idx = {}
    for ent in d["entities"]:
        idx[ent["name"]] = ent["name"]
        for a in ent.get("aliases", []):
            idx.setdefault(a, ent["name"])
    return idx


_NAME_IDX = None


def canon(name: str) -> str:
    global _NAME_IDX
    if _NAME_IDX is None:
        p = DATA / "dict" / "entity_dict.json"
        _NAME_IDX = build_name_index(load_dict(p)) if p.exists() else {}
    return _NAME_IDX.get(name, name)


def _find_span(text: str, surface: str, occ: int) -> tuple[int, int]:
    pos, seen = -1, 0
    for _ in range(occ):
        pos = text.find(surface, pos + 1)
        if pos < 0:
            raise ValueError(f"未找到第{occ}次出现的片段 {surface!r}")
    return pos, pos + len(surface)


def load_sentences(with_gold: bool = True) -> list[Sentence]:
    raw = json.loads((DATA / "sentences.json").read_text(encoding="utf-8"))
    gold_path = DATA / "gold" / "annotations.json"
    gold = {}
    if with_gold and gold_path.exists():
        for item in json.loads(gold_path.read_text(encoding="utf-8")):
            gold[item["sid"]] = item

    alias = {}
    dict_path = DATA / "dict" / "entity_dict.json"
    if dict_path.exists():
        alias = build_alias_index(load_dict(dict_path))

    out = []
    for r in raw:
        s = Sentence(sid=r["sid"], part=r["part"], text=r["text"])
        g = gold.get(r["sid"])
        if g:
            for item in g["entities"]:
                surface, typ = item[0], item[1]
                occ = item[2] if len(item) > 2 else 1
                st, en = _find_span(r["text"], surface, occ)
                s.spans.append(Span(st, en, surface, typ, alias.get(surface, "")))
            for t in g["triples"]:
                coref = bool(t[3]) if len(t) > 3 else False
                s.triples.append((t[0], t[1], t[2], coref))
        out.append(s)
    return out


def to_bio(text: str, spans: list[Span]) -> list[str]:
    tags = ["O"] * len(text)
    for sp in spans:
        tags[sp.start] = f"B-{sp.type}"
        for i in range(sp.start + 1, sp.end):
            tags[i] = f"I-{sp.type}"
    return tags


def bio_to_spans(text: str, tags: list[str]) -> list[Span]:
    spans, i = [], 0
    while i < len(tags):
        t = tags[i]
        if t.startswith("B-"):
            typ = t[2:]
            j = i + 1
            while j < len(tags) and tags[j] == f"I-{typ}":
                j += 1
            spans.append(Span(i, j, text[i:j], typ))
            i = j
        else:
            i += 1
    return spans


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "fp": fp, "fn": fn}


def span_scores(gold, pred) -> dict:
    """gold/pred: [(sid, Span)]；必须带句子 id，否则不同句的相同字符偏移会被误合并。"""
    g = {(sid, x.start, x.end, x.type) for sid, x in gold}
    p = {(sid, x.start, x.end, x.type) for sid, x in pred}
    return prf(len(g & p), len(p - g), len(g - p))


def triple_scores(gold, pred, coarse: bool = True):
    def norm(trs):
        out = set()
        for h, r, t in trs:
            rr = REL2COARSE.get(r, r) if coarse else r
            out.add((h, rr, t))
        return out

    g, p = norm(gold), norm(pred)
    return prf(len(g & p), len(p - g), len(g - p))


def dump_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
