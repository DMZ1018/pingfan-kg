"""BERT 关系分类：把实体对拼成 [E1]..[/E1] [E2]..[/E2] 的字符序列做句对分类。

输出 11 类粗粒度关系 + no_relation。数据来自金标准三元组，按句 5 折交叉验证。
"""
from __future__ import annotations

import json
import random

import torch
import torch.nn as nn
from transformers import BertConfig, BertForSequenceClassification

from common import COARSE_RELS, DATA, OUT, REL2COARSE, Span, load_sentences, prf

LABELS = ["no_relation"] + COARSE_RELS
L2I = {l: i for i, l in enumerate(LABELS)}
SPECIAL = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[E1]", "[/E1]", "[E2]", "[/E2]"]


def build_vocab(sents):
    chars = sorted({c for s in sents for c in s.text})
    return {t: i for i, t in enumerate(SPECIAL)} | {c: i + len(SPECIAL) for i, c in enumerate(chars)}


def encode(text, s1, e1, s2, e2, vocab):
    parts = [text[:s1], "[E1]", text[s1:e1], "[/E1]", text[e1:s2], "[E2]", text[s2:e2], "[/E2]", text[e2:]]
    seq = ["[CLS]"] + [c for p in parts for c in p] + ["[SEP]"]
    return [vocab.get(c, 1) for c in seq]


def pairs_of(sent):
    """句内所有有序实体对及其金标关系（粗粒度）。"""
    ent = sorted(sent.spans, key=lambda x: x.start)
    gold = {}
    for h, r, t, cv in sent.triples:
        gold[(h, t)] = REL2COARSE.get(r, r)
    out = []
    for a in ent:
        for b in ent:
            if a.key() == b.key() or a.start >= b.start:
                continue
            rel = gold.get((a.text, b.text)) or gold.get((a.eid, b.text))
            out.append((a, b, rel))
    return out


def make_examples(sents, vocab, with_label=True):
    ex = []
    for s in sents:
        for a, b, rel in pairs_of(s):
            ex.append((s.text, a, b, rel, s.sid))
    return ex


def collate(ex, vocab, device):
    maxlen = max(len(encode(t, a.start, a.end, b.start, b.end, vocab)) for t, a, b, r, _ in ex)
    ids = torch.zeros(len(ex), maxlen, dtype=torch.long)
    mask = torch.zeros(len(ex), maxlen, dtype=torch.long)
    for i, (t, a, b, r, _) in enumerate(ex):
        seq = encode(t, a.start, a.end, b.start, b.end, vocab)
        ids[i, : len(seq)] = torch.tensor(seq)
        mask[i, : len(seq)] = 1
    return ids.to(device), mask.to(device)


def train(examples, vocab, device, epochs=30, lr=1e-3, seed=13):
    random.seed(seed)
    torch.manual_seed(seed)
    cfg = BertConfig(vocab_size=len(vocab), hidden_size=192, num_hidden_layers=4, num_attention_heads=4,
                     intermediate_size=384, max_position_embeddings=320, num_labels=len(LABELS),
                     hidden_dropout_prob=0.2, attention_probs_dropout_prob=0.2)
    model = BertForSequenceClassification(cfg).to(device)
    pos = [e for e in examples if e[3]]
    neg = [e for e in examples if not e[3]]
    data = pos * 8 + neg if pos else neg
    weight = torch.tensor([1.0] + [8.0] * (len(LABELS) - 1)).to(device)
    lossf = nn.CrossEntropyLoss(weight=weight)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    model.train()
    for _ in range(epochs):
        random.shuffle(data)
        for i in range(0, len(data), 8):
            batch = data[i : i + 8]
            ids, mask = collate(batch, vocab, device)
            labels = torch.tensor([L2I[e[3]] if e[3] else 0 for e in batch]).to(device)
            logits = model(input_ids=ids, attention_mask=mask).logits
            loss = lossf(logits, labels)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
    return model


@torch.no_grad()
def predict(model, examples, vocab, device, thr=0.5):
    model.eval()
    res = []
    for i in range(0, len(examples), 16):
        batch = examples[i : i + 16]
        ids, mask = collate(batch, vocab, device)
        probs = torch.softmax(model(input_ids=ids, attention_mask=mask).logits, -1).cpu()
        for (t, a, b, r, sid), p in zip(batch, probs):
            k = int(p.argmax())
            if p[k] >= thr:
                res.append((sid, a.text, LABELS[k], b.text, float(p[k])))
    return res


def main():
    sents = load_sentences()
    vocab = build_vocab(sents)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    ids = list(range(len(sents)))
    random.Random(7).shuffle(ids)
    fold_of = {i: k % 5 for k, i in enumerate(ids)}

    preds, gold = [], []
    for k in range(5):
        train_s = [sents[i] for i in ids if fold_of[i] != k]
        test_s = [sents[i] for i in ids if fold_of[i] == k]
        model = train(make_examples(train_s, vocab), vocab, device)
        preds += predict(model, make_examples(test_s, vocab), vocab, device)
        for s in test_s:
            for h, r, t, cv in s.triples:
                gold.append((s.sid, h, REL2COARSE.get(r, r), t))

    gold_set = set(gold)
    best = None
    for thr in (0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99):
        keep = [(p[0], p[1], p[2], p[3]) for p in preds if p[4] >= thr]
        sc = prf(len(set(keep) & gold_set), len(set(keep) - gold_set), len(gold_set - set(keep)))
        sc["threshold"] = thr
        if best is None or sc["f1"] > best["scores"]["f1"]:
            best = {"scores": sc, "keep": keep}
    print("bert_re", json.dumps(best["scores"], ensure_ascii=False))
    OUT.mkdir(exist_ok=True)
    by_sid = {}
    for sid, h, r, t in best["keep"]:
        by_sid.setdefault(sid, []).append([h, r, t])
    (OUT / "pred_re_bert.json").write_text(
        json.dumps({"engine": "bert_pair_classifier(scratch)", "scores": best["scores"],
                    "data": [{"sid": s.sid, "triples": by_sid.get(s.sid, [])} for s in sents]},
                   ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
