"""端到端流水线：分句 → 词典 → 实体抽取 → 关系抽取 → 知识图谱 → 可视化。

每一步都是一个独立 CLI（src/*.py），本脚本负责编排、缓存、计时与产物清单。

用法:
    python pipeline.py --list
    python pipeline.py --all
    python pipeline.py --steps ner_eval,re_eval
    python pipeline.py --all --force
    python pipeline.py --all --device cuda --keep-going
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
LOGS = OUT / "logs"
PY = sys.executable


@dataclass
class Step:
    name: str
    desc: str
    cmds: list[list[str]]
    outputs: list[str]
    deps: list[str] = field(default_factory=list)
    optional: bool = False


# 步骤顺序即依赖顺序；outputs 用于缓存判断与产物清单
STEPS: list[Step] = [
    Step("segment", "语料分句", [[PY, "src/segment.py"]], ["data/sentences.json"]),
    Step("dict", "构建实体词典", [[PY, "src/build_entity_dict.py"]],
         ["data/dict/entity_dict.json", "data/dict/entity_dict.csv"], ["segment"]),
    Step("ner_dict", "词典+规则实体抽取", [[PY, "src/baseline_dict.py"]],
         ["out/pred_dict_rule.json"], ["dict"]),
    Step("ner_bilstm", "BiLSTM-CRF 实体抽取（两种设置）", [[PY, "src/bilstm_crf.py", "--device", "{device}"]],
         ["out/pred_bilstm_crf.json", "out/pred_bilstm_crf+dict.json"], ["dict"]),
    Step("ner_bert", "BERT 实体抽取（无预训练权重则从头训练）", [[PY, "src/bert_ner.py", "--device", "{device}"]],
         ["out/pred_bert_scratch.json"], ["dict"]),
    Step("ner_eval", "实体抽取统一评测", [[PY, "src/eval_ner.py"]],
         ["out/metrics_ner.json"], ["ner_dict", "ner_bilstm", "ner_bert"]),
    Step("re_rules", "规则/spaCy 关系抽取", [[PY, "src/re_spacy.py"]],
         ["out/pred_re_spacy.json"], ["dict"]),
    Step("re_bert", "BERT 关系分类", [[PY, "src/re_bert.py"]],
         ["out/pred_re_bert.json"], ["dict"]),
    Step("re_eval", "关系抽取统一评测", [[PY, "src/eval_re.py"]],
         ["out/metrics_re.json"], ["re_rules", "re_bert"]),
    Step("kg", "构建三张知识图谱", [
        [PY, "src/build_kg.py", "--src", "data/llm/triples.json", "--name", "llm"],
        [PY, "src/build_kg.py", "--src", "data/gold/triples.json", "--name", "gold"],
        [PY, "src/build_kg.py", "--src", "out/pred_re_spacy.json", "--name", "pipeline"],
    ], ["out/kg_llm.json", "out/kg_gold.json", "out/kg_pipeline.json"], ["re_eval"]),
    Step("viz", "图谱可视化", [[PY, "src/viz.py"]],
         ["figures/kg_llm.png", "figures/kg_gold.png", "figures/kg_pipeline.png"], ["kg"]),
    Step("bench", "Cypher 装载/查询基准（Kùzu 可用时）", [[PY, "src/kg_cypher.py"]],
         ["out/kg_bench.json"], ["kg"], optional=True),
    Step("report", "重生成报告中的大表格", [
        [PY, "src/inject_dict_table.py"],
        [PY, "src/inject_triple_table.py"],
    ], [], ["dict", "re_eval"], optional=True),
]

BY_NAME = {s.name: s for s in STEPS}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def up_to_date(step: Step) -> bool:
    outs = [ROOT / o for o in step.outputs]
    if not outs or not all(p.exists() for p in outs):
        return False
    newest_out = min(p.stat().st_mtime for p in outs)
    for dep in step.deps:
        for o in BY_NAME[dep].outputs:
            p = ROOT / o
            if p.exists() and p.stat().st_mtime > newest_out:
                return False
    return True


def run_step(step: Step, device: str, force: bool) -> dict:
    started = time.perf_counter()
    if not force and up_to_date(step):
        return {"step": step.name, "status": "cached", "seconds": 0.0}

    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"{step.name}.log"
    lines = [f"$ {' '.join(cmd)}" for cmd in step.cmds]
    for cmd in step.cmds:
        cmd = [c.replace("{device}", device) for c in cmd]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines.append(f"$ {' '.join(cmd)}")
        lines.append(proc.stdout or "")
        if proc.returncode != 0:
            lines.append(proc.stderr or "")
            log_path.write_text("\n".join(lines), encoding="utf-8")
            return {"step": step.name, "status": "failed", "seconds": round(time.perf_counter() - started, 2),
                    "error": (proc.stderr or "").strip().splitlines()[-1:] or ["unknown"]}
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return {"step": step.name, "status": "ok", "seconds": round(time.perf_counter() - started, 2)}


def main():
    ap = argparse.ArgumentParser(description="《平凡的世界》知识抽取流水线")
    ap.add_argument("--all", action="store_true", help="跑全部步骤")
    ap.add_argument("--steps", default="", help="逗号分隔的步骤名")
    ap.add_argument("--list", action="store_true", help="列出步骤")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="忽略缓存")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    ap.add_argument("--keep-going", action="store_true", help="某步失败后继续")
    a = ap.parse_args()

    if a.list:
        print(f"{'步骤':<12}{'说明':<34}{'依赖'}")
        for s in STEPS:
            print(f"{s.name:<12}{s.desc:<34}{','.join(s.deps) or '-'}")
        return 0

    names = [s.name for s in STEPS] if a.all or not a.steps else [x.strip() for x in a.steps.split(",") if x.strip()]
    unknown = [n for n in names if n not in BY_NAME]
    if unknown:
        print(f"未知步骤: {unknown}\n可用: {list(BY_NAME)}", file=sys.stderr)
        return 2
    # 自动补齐依赖
    chosen, stack = [], list(names)
    while stack:
        n = stack.pop(0)
        if n in chosen:
            continue
        chosen.append(n)
        stack = BY_NAME[n].deps + stack
    chosen = [s.name for s in STEPS if s.name in chosen]

    if a.dry_run:
        print("将执行:", " → ".join(chosen))
        return 0

    print(f"pipeline start  steps={len(chosen)} device={a.device} force={a.force}")
    results, failed = [], 0
    for name in chosen:
        step = BY_NAME[name]
        r = run_step(step, a.device, a.force)
        results.append(r)
        flag = {"ok": "OK  ", "cached": "SKIP", "failed": "FAIL"}[r["status"]]
        print(f"  [{flag}] {name:<12} {r['seconds']:>6.2f}s  {step.desc}")
        if r["status"] == "failed":
            if step.optional:
                r["status"] = "skipped"
                print(f"         （可选步骤，跳过）{r.get('error', '')}")
                continue
            failed += 1
            print(f"         {r.get('error')}", file=sys.stderr)
            if not a.keep_going:
                break

    manifest = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "device": a.device,
        "force": a.force,
        "steps": results,
        "artifacts": {o: sha256(ROOT / o) for s in STEPS for o in s.outputs if (ROOT / o).exists()},
        "failed": failed,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(r["seconds"] for r in results)
    print(f"pipeline done  ok={sum(r['status']!='failed' for r in results)}  failed={failed}  {total:.1f}s")
    print(f"manifest: out/run_manifest.json")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
