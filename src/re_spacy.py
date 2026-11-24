"""spaCy 关系抽取管线：EntityRuler 识别实体 + 触发词/邻接模式抽三元组。

本机无中文预训练模型（zh_core_web_sm 需从 GitHub 下载，当前网络不可达），
因此使用 spacy.blank("zh") + EntityRuler + 自写触发词规则，不依赖依存句法。
若装入了中文模型，把 nlp 换成 spacy.load("zh_core_web_sm") 即可接入句法特征。
"""
from __future__ import annotations

import json

from common import DATA, OUT, load_sentences
from re_rules import apply_rules


def build_nlp():
    import spacy

    nlp = spacy.blank("zh")
    ruler = nlp.add_pipe("entity_ruler")
    d = json.loads((DATA / "dict" / "entity_dict.json").read_text(encoding="utf-8"))
    patterns = []
    for e in d["entities"]:
        for sf in [e["name"]] + e["aliases"]:
            patterns.append({"label": e["type"], "pattern": sf})
    ruler.add_patterns(patterns)
    return nlp


def main():
    sents = load_sentences()
    try:
        nlp = build_nlp()
        engine = "spacy(blank_zh+EntityRuler+trigger_rules)"
    except Exception as e:
        nlp, engine = None, f"fallback:{type(e).__name__}"

    out = []
    for s in sents:
        if nlp is not None:
            doc = nlp(s.text)
            ents = [(e.start_char, e.end_char, e.text, e.label_) for e in doc.ents]
            triples = apply_rules(s.text, ents)
        else:
            from re_fallback import fallback_extract
            triples = fallback_extract(s.text)
        out.append({"sid": s.sid, "triples": [list(t) for t in triples]})

    OUT.mkdir(exist_ok=True)
    (OUT / "pred_re_spacy.json").write_text(
        json.dumps({"engine": engine, "data": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("engine:", engine, "triples:", sum(len(o["triples"]) for o in out))


if __name__ == "__main__":
    main()
