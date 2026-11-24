"""导出金标准三元组，并把各方法输出统一到规范名后评测。"""
from __future__ import annotations

import json

from common import DATA, OUT, REL2COARSE, build_name_index, load_dict, load_sentences, prf


def norm(name, alias):
    return alias.get(name, name)


def main():
    sents = load_sentences()
    alias = build_name_index(load_dict())

    gold = []
    for s in sents:
        for h, r, t, coref in s.triples:
            gold.append((s.sid, norm(h, alias), r, norm(t, alias), coref))

    (DATA / "gold" / "triples.json").write_text(
        json.dumps([{"sid": s.sid, "triples": [[norm(h, alias), r, norm(t, alias)] for h, r, t, _ in s.triples]}
                    for s in sents], ensure_ascii=False, indent=1), encoding="utf-8")

    def gold_set(coarse=True, skip_coref=False):
        return {(sid, h, REL2COARSE.get(r, r) if coarse else r, t)
                for sid, h, r, t, coref in gold if not (skip_coref and coref)}

    def load_method(path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("data", raw) if isinstance(raw, dict) else raw
        out = set()
        for r in rows:
            for t in r.get("triples", []):
                out.add((r["sid"], norm(t[0], alias), t[1], norm(t[2], alias)))
        return out

    methods = {
        "spaCy规则": OUT / "pred_re_spacy.json",
        "BERT关系分类": OUT / "pred_re_bert.json",
        "LLM(DeepSeek)": DATA / "llm" / "triples.json",
    }

    result = {}
    for name, path in methods.items():
        if not path.exists():
            print("skip", name)
            continue
        pred = load_method(path)
        result[name] = {
            "n_pred": len(pred),
            "fine": prf(*_cmp(gold_set(coarse=False), pred, coarse=False)),
            "coarse": prf(*_cmp(gold_set(coarse=True), pred, coarse=True)),
            "coarse_no_coref": prf(*_cmp(gold_set(coarse=True, skip_coref=True), pred, coarse=True)),
        }

    (OUT / "metrics_re.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'方法':<16}{'细F1':>8}{'粗F1':>8}{'粗P':>8}{'粗R':>8}{'去指代R':>9}{'预测数':>7}")
    for name, e in result.items():
        print(f"{name:<16}{e['fine']['f1']:>8.3f}{e['coarse']['f1']:>8.3f}{e['coarse']['precision']:>8.3f}"
              f"{e['coarse']['recall']:>8.3f}{e['coarse_no_coref']['recall']:>9.3f}{e['n_pred']:>7}")


def _cmp(gold, pred, coarse):
    def m(r):
        return REL2COARSE.get(r, r) if coarse else r

    g = {(h, m(r), t) for _, h, r, t in gold}
    p = {(h, m(r), t) for _, h, r, t in pred}
    return len(g & p), len(p - g), len(g - p)


if __name__ == "__main__":
    main()
