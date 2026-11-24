"""BiLSTM-CRF 字符级实体抽取（含可选词典特征），从零实现，不依赖第三方序列标注库。

用法:
    python src/bilstm_crf.py --mode cv        # 5 折交叉验证
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from common import DATA, OUT, TYPES, Span, bio_to_spans, load_sentences, span_scores, to_bio

TAGS = ["O"] + [f"{p}-{t}" for t in TYPES for p in ("B", "I")]
TAG2ID = {t: i for i, t in enumerate(TAGS)}
ID2TAG = {i: t for t, i in TAG2ID.items()}
PAD, UNK = "<pad>", "<unk>"


# --------------------------------------------------------------------------- CRF
class CRF(nn.Module):
    def __init__(self, num_tags: int):
        super().__init__()
        self.num_tags = num_tags
        self.transitions = nn.Parameter(torch.empty(num_tags, num_tags))
        self.start_trans = nn.Parameter(torch.empty(num_tags))
        self.end_trans = nn.Parameter(torch.empty(num_tags))
        nn.init.uniform_(self.transitions, -0.1, 0.1)
        nn.init.uniform_(self.start_trans, -0.1, 0.1)
        nn.init.uniform_(self.end_trans, -0.1, 0.1)

    def _score(self, emissions, tags, mask):
        # emissions: (B,L,T) tags: (B,L)
        b, l, _ = emissions.shape
        score = self.start_trans[tags[:, 0]] + emissions[:, 0].gather(1, tags[:, :1]).squeeze(1)
        for i in range(1, l):
            m = mask[:, i]
            step = self.transitions[tags[:, i - 1], tags[:, i]] + emissions[:, i].gather(1, tags[:, i : i + 1]).squeeze(1)
            score = score + step * m
        last_idx = mask.long().sum(1) - 1
        score = score + self.end_trans[tags.gather(1, last_idx[:, None]).squeeze(1)]
        return score

    def _log_partition(self, emissions, mask):
        b, l, t = emissions.shape
        alpha = self.start_trans + emissions[:, 0]
        for i in range(1, l):
            m = mask[:, i].unsqueeze(1)
            emit = emissions[:, i].unsqueeze(1)  # (B,1,T)
            nxt = alpha.unsqueeze(2) + self.transitions.unsqueeze(0) + emit  # (B,T,T)
            new_alpha = torch.logsumexp(nxt, dim=1)
            alpha = torch.where(m.bool(), new_alpha, alpha)
        alpha = alpha + self.end_trans
        return torch.logsumexp(alpha, dim=1)

    def nll(self, emissions, tags, mask):
        return (self._log_partition(emissions, mask) - self._score(emissions, tags, mask)).mean()

    @torch.no_grad()
    def decode(self, emissions, mask):
        b, l, t = emissions.shape
        score = self.start_trans + emissions[:, 0]
        history = []
        for i in range(1, l):
            m = mask[:, i].unsqueeze(1).bool()
            nxt = score.unsqueeze(2) + self.transitions.unsqueeze(0) + emissions[:, i].unsqueeze(1)
            best, idx = nxt.max(dim=1)
            score = torch.where(m, best, score)
            history.append(idx)
        score = score + self.end_trans
        best_last = score.argmax(1)
        paths = []
        for bi in range(b):
            length = int(mask[bi].sum().item())
            path = [int(best_last[bi])]
            for i in range(length - 2, -1, -1):
                path.append(int(history[i][bi, path[-1]]))
            paths.append(path[::-1])
        return paths


# ----------------------------------------------------------------------- Encoder
class BiLSTMCRF(nn.Module):
    def __init__(self, vocab_size, n_tags, emb=128, hidden=128, gaz_vocab=3, gaz_dim=12, dropout=0.3):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, emb, padding_idx=0)
        self.gaz_emb = nn.Embedding(gaz_vocab, gaz_dim)
        self.lstm = nn.LSTM(emb + gaz_dim, hidden, num_layers=1, batch_first=True, bidirectional=True)
        self.drop = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden * 2, n_tags)
        self.crf = CRF(n_tags)

    def emissions(self, x, gaz):
        e = torch.cat([self.emb(x), self.gaz_emb(gaz)], dim=-1)
        out, _ = self.lstm(self.drop(e))
        return self.fc(self.drop(out))


# ------------------------------------------------------------------- data helper
def build_vocab(sents):
    chars = sorted({c for s in sents for c in s.text})
    return {PAD: 0, UNK: 1, **{c: i + 2 for i, c in enumerate(chars)}}


def gaz_features(text: str, surfaces) -> list[int]:
    """0=O, 1=B, 2=I：词典最长匹配的字符级标记。"""
    feats = [0] * len(text)
    for sf in surfaces:
        start = 0
        while True:
            i = text.find(sf, start)
            if i < 0:
                break
            feats[i] = 1
            for j in range(i + 1, i + len(sf)):
                feats[j] = 2
            start = i + 1
    return feats


def make_items(sents, vocab, surfaces):
    items = []
    for s in sents:
        x = [vocab.get(c, 1) for c in s.text]
        y = [TAG2ID[t] for t in to_bio(s.text, s.spans)]
        g = gaz_features(s.text, surfaces)
        items.append((x, y, g, s))
    return items


def pad_batch(batch):
    l = max(len(b[0]) for b in batch)
    x = torch.zeros(len(batch), l, dtype=torch.long)
    y = torch.zeros(len(batch), l, dtype=torch.long)
    g = torch.zeros(len(batch), l, dtype=torch.long)
    mask = torch.zeros(len(batch), l)
    for i, (xi, yi, gi, _) in enumerate(batch):
        n = len(xi)
        x[i, :n] = torch.tensor(xi)
        y[i, :n] = torch.tensor(yi)
        g[i, :n] = torch.tensor(gi)
        mask[i, :n] = 1
    return x, y, g, mask


def train_model(train_items, vocab, n_epochs=60, seed=13, lr=2e-3, use_gaz=True, device="cpu"):
    random.seed(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = BiLSTMCRF(len(vocab), len(TAGS), dropout=0.3 if use_gaz else 0.2).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    items = list(train_items)
    for ep in range(n_epochs):
        random.shuffle(items)
        model.train()
        for i in range(0, len(items), 6):
            batch = items[i : i + 6]
            x, y, g, mask = [t.to(device) for t in pad_batch(batch)]
            if not use_gaz:
                g = torch.zeros_like(g)
            em = model.emissions(x, g)
            loss = model.crf.nll(em, y, mask)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
    return model


@torch.no_grad()
def predict(model, items, vocab, device="cpu"):
    model.eval()
    out = []
    for i in range(0, len(items), 8):
        batch = items[i : i + 8]
        x, _, g, mask = [t.to(device) for t in pad_batch(batch)]
        em = model.emissions(x, g)
        paths = model.crf.decode(em, mask)
        for (xi, yi, gi, s), path in zip(batch, paths):
            tags = [ID2TAG[t] for t in path[: len(xi)]]
            out.append(bio_to_spans(s.text, tags))
    return out


def run_cv(use_gaz=True, folds=5, seeds=(13, 42, 2024), n_epochs=60, device="cpu"):
    sents = load_sentences()
    vocab = build_vocab(sents)
    d = json.loads((DATA / "dict" / "entity_dict.json").read_text(encoding="utf-8"))
    surfaces = []
    for e in d["entities"]:
        surfaces.append(e["name"])
        surfaces.extend(e["aliases"])
    surfaces = sorted(set(surfaces), key=len, reverse=True)

    idx = list(range(len(sents)))
    rng = random.Random(7)
    rng.shuffle(idx)
    fold_of = {i: k % folds for k, i in enumerate(idx)}

    all_pred = {s.sid: [] for s in sents}
    for seed in seeds:
        for k in range(folds):
            train = [sents[i] for i in idx if fold_of[i] != k]
            test = [sents[i] for i in idx if fold_of[i] == k]
            tr_items = make_items(train, vocab, surfaces)
            te_items = make_items(test, vocab, surfaces)
            model = train_model(tr_items, vocab, n_epochs=n_epochs, seed=seed, use_gaz=use_gaz, device=device)
            preds = predict(model, te_items, vocab, device=device)
            for s, p in zip(test, preds):
                all_pred[s.sid].append(p)

    # 多 seed 投票：按 (start,end,type) 出现次数过半保留
    final = []
    for s in sents:
        votes = {}
        for p in all_pred[s.sid]:
            for sp in p:
                votes[sp.key()] = votes.get(sp.key(), 0) + 1
        keep = [Span(st, en, s.text[st:en], ty) for (st, en, ty), v in votes.items() if v * 2 >= len(all_pred[s.sid])]
        final.append(keep)
    scores = span_scores([(s.sid, x) for s in sents for x in s.spans], [(s.sid, x) for s, ps in zip(sents, final) for x in ps])
    return scores, final, sents


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="cv")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    for gaz in (False, True):
        sc, final, sents = run_cv(use_gaz=gaz, device=a.device)
        tag = "bilstm_crf+dict" if gaz else "bilstm_crf"
        print(tag, json.dumps(sc, ensure_ascii=False))
        OUT.mkdir(exist_ok=True)
        (OUT / f"pred_{tag}.json").write_text(
            json.dumps([{"sid": s.sid, "spans": [[p.start, p.end, p.text, p.type] for p in ps]} for s, ps in zip(sents, final)],
                       ensure_ascii=False, indent=1),
            encoding="utf-8")

