"""实体抽取统一评测：词典基线 / BiLSTM-CRF / BERT / LLM，按整体、类型、篇章分组。"""
from __future__ import annotations

import json
from collections import defaultdict

from common import OUT, TYPES, Span, load_sentences, prf, span_scores


def load_pred(path, sents):
    if not path.exists():
        return None
    raw = {d["sid"]: d for d in json.loads(path.read_text(encoding="utf-8"))}
    preds = {}
    for s in sents:
        if s.sid in raw:
            preds[s.sid] = [Span(int(a), int(b), t, ty) for a, b, t, ty in raw[s.sid]["spans"]]
    return preds


def load_llm(path, sents):
    if not path.exists():
        return None
    raw = {d["sid"]: d["entities"] for d in json.loads(path.read_text(encoding="utf-8"))}
    preds = {}
    for s in sents:
        spans, pos = [], 0
        for item in raw.get(s.sid, []):
            surface, typ = item[0], item[1]
            occ = item[2] if len(item) > 2 else 1
            idx, seen = -1, 0
            for _ in range(occ):
                idx = s.text.find(surface, idx + 1)
            spans.append(Span(idx, idx + len(surface), surface, typ))
        preds[s.sid] = spans
    return preds


def evaluate(preds, sents):
    gold = [(s.sid, x) for s in sents for x in s.spans]
    pred = [(s.sid, x) for s in sents for x in preds.get(s.sid, [])]
    overall = span_scores(gold, pred)

    by_type = {}
    for t in TYPES:
        g = [(sid, x) for sid, x in gold if x.type == t]
        p = [(sid, x) for sid, x in pred if x.type == t]
        by_type[t] = span_scores(g, p)

    by_part = {}
    for part in (1, 2, 3):
        g = [(sid, x) for sid, x in gold if next(s for s in sents if s.sid == sid).part == part]
        p = [(sid, x) for sid, x in pred if next(s for s in sents if s.sid == sid).part == part]
        by_part[f"P{part}"] = span_scores(g, p)

    # 边界正确但类型错误的“近似命中”，衡量类型判定能力
    gmap = {(sid, x.start, x.end): x.type for sid, x in gold}
    pmap = {(sid, x.start, x.end): x.type for sid, x in pred}
    boundary_tp = len(set(gmap) & set(pmap))
    type_ok = sum(1 for k in set(gmap) & set(pmap) if gmap[k] == pmap[k])
    return {
        "overall": overall,
        "by_type": by_type,
        "by_part": by_part,
        "boundary_precision": round(boundary_tp / len(pmap), 4) if pmap else 0.0,
        "boundary_recall": round(boundary_tp / len(gmap), 4) if gmap else 0.0,
        "type_accuracy_on_boundary_tp": round(type_ok / boundary_tp, 4) if boundary_tp else 0.0,
    }


def main():
    sents = load_sentences()
    methods = {
        "词典+规则": OUT / "pred_dict_rule.json",
        "BiLSTM-CRF": OUT / "pred_bilstm_crf.json",
        "BiLSTM-CRF+词典": OUT / "pred_bilstm_crf+dict.json",
        "BERT(从头训练)": OUT / "pred_bert_scratch.json",
        "LLM(DeepSeek)": None,
    }
    results = {}
    for name, path in methods.items():
        if name.startswith("LLM"):
            preds = load_llm(OUT.parent / "data" / "llm" / "ner.json", sents)
        else:
            preds = load_pred(path, sents)
        if preds is None:
            print("skip", name)
            continue
        results[name] = evaluate(preds, sents)

    OUT.mkdir(exist_ok=True)
    (OUT / "metrics_ner.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{'方法':<18}{'P':>7}{'R':>7}{'F1':>7}   {'边界P':>7}{'边界R':>7}{'类型准确':>8}")
    for name, r in results.items():
        o = r["overall"]
        print(f"{name:<18}{o['precision']:>7.3f}{o['recall']:>7.3f}{o['f1']:>7.3f}   "
              f"{r['boundary_precision']:>7.3f}{r['boundary_recall']:>7.3f}{r['type_accuracy_on_boundary_tp']:>8.3f}")
    print("\n按类型 F1:")
    head = "".join(f"{t:>8}" for t in TYPES)
    print(f"{'方法':<18}{head}")
    for name, r in results.items():
        print(f"{name:<18}" + "".join(f"{r['by_type'][t]['f1']:>8.3f}" for t in TYPES))


if __name__ == "__main__":
    main()
