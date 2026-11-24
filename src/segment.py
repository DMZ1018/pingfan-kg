"""语料分句：把三部梗概切成句级单元，供标注与建模使用。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus"
OUT = ROOT / "data" / "sentences.json"

SENT_END = "。！？"
CLOSERS = "”’」』）)"


def split_sents(text: str):
    text = text.strip()
    sents, buf = [], ""
    for ch in text:
        buf += ch
        if ch in SENT_END:
            sents.append(buf.strip())
            buf = ""
    if buf.strip():
        sents.append(buf.strip())
    # 去掉纯标点句
    return [s for s in sents if re.search(r"[\u4e00-\u9fff0-9]", s)]


def main():
    data = []
    for part in (1, 2, 3):
        raw = (CORPUS / f"part{part}.txt").read_text(encoding="utf-8")
        for i, s in enumerate(split_sents(raw), 1):
            data.append({"sid": f"P{part}-S{i:02d}", "part": part, "text": s})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"sentences={len(data)} chars={sum(len(d['text']) for d in data)}")
    for d in data:
        print(d["sid"], len(d["text"]), d["text"])


if __name__ == "__main__":
    main()
