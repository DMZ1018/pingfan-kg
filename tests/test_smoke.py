"""冒烟测试：不依赖 torch，验证语料、金标准、词典与流水线骨架的一致性。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common import TYPES, load_sentences  # noqa: E402


def test_sentences():
    data = json.loads((ROOT / "data" / "sentences.json").read_text(encoding="utf-8"))
    assert len(data) == 21
    assert len({d["sid"] for d in data}) == 21
    assert sum(len(d["text"]) for d in data) == 1103


def test_gold_offsets():
    sents = load_sentences()
    assert sum(len(s.spans) for s in sents) == 124
    assert sum(len(s.triples) for s in sents) == 75
    for s in sents:
        for sp in s.spans:
            assert s.text[sp.start : sp.end] == sp.text, f"{s.sid} 跨度越界"
            assert sp.type in TYPES


def test_gold_triples_grounded():
    """三元组的头尾必须能在该句实体里找到（允许别名归一后的规范名）。"""
    from common import build_name_index, canon, load_dict

    alias = build_name_index(load_dict())
    sents = load_sentences()
    for s in sents:
        names = {canon(sp.text) for sp in s.spans}
        for h, r, t, _ in s.triples:
            assert canon(alias.get(h, h)) in names or h in names, f"{s.sid} 头实体 {h} 不在句内"
            assert canon(alias.get(t, t)) in names or t in names, f"{s.sid} 尾实体 {t} 不在句内"


def test_dict_shape():
    d = json.loads((ROOT / "data" / "dict" / "entity_dict.json").read_text(encoding="utf-8"))
    assert len(d["entities"]) == 80
    names = [e["name"] for e in d["entities"]]
    assert len(names) == len(set(names)), "词典存在重名"
    for e in d["entities"]:
        assert e["type"] in TYPES
        assert e["eid"].startswith(e["type"])


def test_pipeline_list():
    proc = subprocess.run([sys.executable, str(ROOT / "pipeline.py"), "--list"],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0
    for name in ("segment", "dict", "ner_eval", "re_eval", "kg", "viz"):
        assert name in proc.stdout


@pytest.mark.skipif(not (ROOT / "out" / "metrics_ner.json").exists(), reason="尚未运行评测")
def test_metrics_files():
    m = json.loads((ROOT / "out" / "metrics_ner.json").read_text(encoding="utf-8"))
    assert "LLM(DeepSeek)" in m and "词典+规则" in m
    for v in m.values():
        assert 0 <= v["overall"]["f1"] <= 1
    r = json.loads((ROOT / "out" / "metrics_re.json").read_text(encoding="utf-8"))
    assert r["LLM(DeepSeek)"]["coarse"]["f1"] > 0.9
