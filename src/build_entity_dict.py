"""构建实体词词典：合并人工种子、语料频次、首现句，导出 json/csv/md 三种形态。"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from common import DATA, ROOT, TYPES, TYPE_CN, load_sentences

SEED = DATA / "dict" / "seed_entities.csv"
OUTDIR = DATA / "dict"


def main():
    rows = list(csv.DictReader(SEED.read_text(encoding="utf-8").splitlines()))
    sents = load_sentences()
    corpus = "".join(s.text for s in sents)

    # 语料频次（含别名），用最长匹配避免“少平/孙少平”重复计数
    entities = []
    used_eids = set()
    seq = {t: 0 for t in TYPES}
    for r in rows:
        r = {k.strip(): (v or "").strip() for k, v in r.items()}
        typ = r["type"]
        aliases = [a for a in r["aliases"].split("|") if a]
        seq[typ] += 1
        eid = f"{typ}_{seq[typ]:03d}"
        while eid in used_eids:
            seq[typ] += 1
            eid = f"{typ}_{seq[typ]:03d}"
        used_eids.add(eid)

        surfaces = [r["name"]] + aliases
        freq, first_sid, first_pos = 0, "", 10**9
        for s in sents:
            hits = []
            for sf in surfaces:
                for m in re.finditer(re.escape(sf), s.text):
                    hits.append((m.start(), m.end(), sf))
            # 同一位置优先长匹配，避免“孙少平”与“少平”重复计数
            hits.sort(key=lambda x: (x[0], -(x[1] - x[0])))
            last_end = -1
            for st, en, sf in hits:
                if st < last_end:
                    continue
                last_end = en
                freq += 1
                if s.part * 10000 + st < first_pos:
                    first_pos = s.part * 10000 + st
                    first_sid = s.sid
        entities.append({
            "eid": eid,
            "name": r["name"],
            "type": typ,
            "type_cn": TYPE_CN[typ],
            "aliases": aliases,
            "desc": r["desc"],
            "freq": freq,
            "first_sid": first_sid,
        })

    entities.sort(key=lambda e: (TYPES.index(e["type"]), -e["freq"], e["name"]))
    # 重排 eid，让编号与最终顺序一致
    for i, e in enumerate(entities, 1):
        e["eid"] = f"{e['type']}_{i:03d}"

    payload = {
        "meta": {
            "source": "《平凡的世界》三部梗概（三幅图片转写）",
            "n_entities": len(entities),
            "n_mentions_in_gold": sum(len(s.spans) for s in sents),
            "types": {t: TYPE_CN[t] for t in TYPES},
        },
        "entities": entities,
    }
    (OUTDIR / "entity_dict.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    with open(OUTDIR / "entity_dict.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["eid", "name", "type", "type_cn", "aliases", "freq", "first_sid", "desc"])
        for e in entities:
            w.writerow([e["eid"], e["name"], e["type"], e["type_cn"], "|".join(e["aliases"]), e["freq"], e["first_sid"], e["desc"]])

    # 按类型统计
    stat = {}
    for e in entities:
        stat.setdefault(e["type"], {"n": 0, "mentions": 0})
        stat[e["type"]]["n"] += 1
        stat[e["type"]]["mentions"] += e["freq"]
    print(json.dumps({"n": len(entities), "by_type": stat}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
