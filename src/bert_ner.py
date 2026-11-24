"""BERT 字符级实体抽取。

说明：本机处于离线白名单网络环境，HuggingFace 不可达，因此默认从随机初始化
训练一个 4 层 BERT（BertForTokenClassification）。若本地有预训练权重，传入
--bert-dir 即可切换到 bert-base-chinese 微调，其余流程不变。
"""
from __future__ import annotations

import argparse
import json
import random

import numpy as np
import torch
import torch.nn as nn
from transformers import BertConfig, BertForTokenClassification

from common import DATA, OUT, TYPES, Span, bio_to_spans, load_sentences, span_scores, to_bio
from bilstm_crf import TAGS, TAG2ID, ID2TAG, build_vocab, pad_batch, make_items


def build_model(vocab_size: int, bert_dir: str | None, device: str):
    if bert_dir:
        model = BertForTokenClassification.from_pretrained(bert_dir, num_labels=len(TAGS))
    else:
        cfg = BertConfig(
            vocab_size=vocab_size,
            hidden_size=192,
            num_hidden_layers=4,
            num_attention_heads=4,
            intermediate_size=384,
            max_position_embeddings=256,
            type_vocab_size=2,
            hidden_dropout_prob=0.2,
            attention_probs_dropout_prob=0.2,
            num_labels=len(TAGS),
        )
        model = BertForTokenClassification(cfg)
    return model.to(device)


def _batch(items, device):
    x, y, g, mask = pad_batch(items)
    return (
        x.to(device),
        torch.zeros_like(x).to(device),
        mask.long().to(device),
        y.to(device),
        mask.to(device),
    )


def train_model(train_items, vocab, bert_dir=None, n_epochs=40, seed=13, lr=8e-4, device="cpu"):
    random.seed(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = build_model(len(vocab), bert_dir, device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    items = list(train_items)
    model.train()
    for _ in range(n_epochs):
        random.shuffle(items)
        for i in range(0, len(items), 6):
            ids, ttype, attn, labels, mask = _batch(items[i : i + 6], device)
            out = model(input_ids=ids, token_type_ids=ttype, attention_mask=attn, labels=labels)
            opt.zero_grad()
            out.loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
    return model


@torch.no_grad()
def predict(model, items, device="cpu"):
    model.eval()
    out = []
    for i in range(0, len(items), 8):
        batch = items[i : i + 8]
        ids, ttype, attn, _, mask = _batch(batch, device)
        logits = model(input_ids=ids, token_type_ids=ttype, attention_mask=attn).logits
        paths = logits.argmax(-1).cpu()
        for (xi, yi, gi, s), path in zip(batch, paths):
            tags = [ID2TAG[int(t)] for t in path[: len(xi)]]
            out.append(bio_to_spans(s.text, tags))
    return out


def run_cv(folds=5, seeds=(13, 42, 2024), n_epochs=40, bert_dir=None, device="cpu"):
    sents = load_sentences()
    vocab = build_vocab(sents)
    d = json.loads((DATA / "dict" / "entity_dict.json").read_text(encoding="utf-8"))
    surfaces = sorted({e["name"] for e in d["entities"]} | {a for e in d["entities"] for a in e["aliases"]}, key=len, reverse=True)

    idx = list(range(len(sents)))
    rng = random.Random(7)
    rng.shuffle(idx)
    fold_of = {i: k % folds for k, i in enumerate(idx)}

    all_pred = {s.sid: [] for s in sents}
    for seed in seeds:
        for k in range(folds):
            train = [sents[i] for i in idx if fold_of[i] != k]
            test = [sents[i] for i in idx if fold_of[i] == k]
            model = train_model(make_items(train, vocab, surfaces), vocab, bert_dir, n_epochs, seed, device=device)
            for s, p in zip(test, predict(model, make_items(test, vocab, surfaces), device)):
                all_pred[s.sid].append(p)

    final = []
    for s in sents:
        votes = {}
        for p in all_pred[s.sid]:
            for sp in p:
                votes[sp.key()] = votes.get(sp.key(), 0) + 1
        final.append([Span(st, en, s.text[st:en], ty) for (st, en, ty), v in votes.items() if v * 2 >= len(all_pred[s.sid])])
    return span_scores([(s.sid, x) for s in sents for x in s.spans], [(s.sid, x) for s, ps in zip(sents, final) for x in ps]), final, sents


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bert-dir", default=None)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    sc, final, sents = run_cv(bert_dir=a.bert_dir, device=a.device)
    print("bert", json.dumps(sc, ensure_ascii=False))
    OUT.mkdir(exist_ok=True)
    name = "bert_pretrained" if a.bert_dir else "bert_scratch"
    (OUT / f"pred_{name}.json").write_text(
        json.dumps([{"sid": s.sid, "spans": [[p.start, p.end, p.text, p.type] for p in ps]} for s, ps in zip(sents, final)],
                   ensure_ascii=False, indent=1), encoding="utf-8")

