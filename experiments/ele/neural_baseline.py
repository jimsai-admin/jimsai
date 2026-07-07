"""Equal-budget neural baselines (spec §4.1 — mandatory, permanent).

Row 3: a tiny neural LM vs a construction-ledger predictor on next-token
perplexity. The original finding was the transformer winning by ~6x; this
comparison exists so that result is never hidden or re-litigated. REPORT, not
assert — whichever way it lands.

Row 4: ledger ingestion vs neural retraining wall-clock on the same new data.

Row 7: a tiny neural renderer CAN hallucinate roles the input never contained;
the template renderer cannot (capacity starvation). Hallucination count is
REPORTED (existence claim from the original run; seed-dependent).

numpy only; parameter counts printed so "equal budget" is checkable.
"""

from __future__ import annotations

import time

import numpy as np

BOS = "<s>"


def _vocab(token_lists: list[list[str]]) -> dict[str, int]:
    words = sorted({t for toks in token_lists for t in toks} | {BOS})
    return {w: i for i, w in enumerate(words)}


def _trigram_examples(token_lists, vocab):
    X, y = [], []
    for toks in token_lists:
        padded = [BOS, BOS] + toks
        for i in range(2, len(padded)):
            X.append((vocab[padded[i - 2]], vocab[padded[i - 1]]))
            y.append(vocab[padded[i]])
    return np.array(X), np.array(y)


class TinyNeuralLM:
    """Trigram MLP: 2 x embed(16) -> tanh(32) -> softmax(V)."""

    def __init__(self, vocab_size: int, seed: int, dim: int = 16, hidden: int = 32):
        rng = np.random.default_rng(seed)
        self.E = rng.normal(0, 0.1, (vocab_size, dim))
        self.W1 = rng.normal(0, 0.1, (2 * dim, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = rng.normal(0, 0.1, (hidden, vocab_size))
        self.b2 = np.zeros(vocab_size)

    @property
    def n_params(self) -> int:
        return sum(a.size for a in (self.E, self.W1, self.b1, self.W2, self.b2))

    def _forward(self, X):
        emb = np.concatenate([self.E[X[:, 0]], self.E[X[:, 1]]], axis=1)
        h = np.tanh(emb @ self.W1 + self.b1)
        logits = h @ self.W2 + self.b2
        logits -= logits.max(axis=1, keepdims=True)
        p = np.exp(logits)
        return emb, h, p / p.sum(axis=1, keepdims=True)

    def train(self, X, y, epochs: int = 25, lr: float = 0.5, batch: int = 256,
              seed: int = 0) -> None:
        rng = np.random.default_rng(seed)
        for _ in range(epochs):
            order = rng.permutation(len(X))
            for s in range(0, len(X), batch):
                idx = order[s:s + batch]
                Xb, yb = X[idx], y[idx]
                emb, h, probs = self._forward(Xb)
                d_logits = probs
                d_logits[np.arange(len(yb)), yb] -= 1
                d_logits /= len(yb)
                dW2 = h.T @ d_logits
                dh = d_logits @ self.W2.T * (1 - h ** 2)
                dW1 = emb.T @ dh
                demb = dh @ self.W1.T
                self.W2 -= lr * dW2
                self.b2 -= lr * d_logits.sum(0)
                self.W1 -= lr * dW1
                self.b1 -= lr * dh.sum(0)
                half = self.E.shape[1]
                np.add.at(self.E, Xb[:, 0], -lr * demb[:, :half])
                np.add.at(self.E, Xb[:, 1], -lr * demb[:, half:])

    def perplexity(self, X, y) -> float:
        _, _, probs = self._forward(X)
        nll = -np.log(np.clip(probs[np.arange(len(y)), y], 1e-12, None))
        return float(np.exp(nll.mean()))


class LedgerLM:
    """Construction-ledger predictor: interpolated trigram/bigram/unigram counts
    (the ledger's n-gram frames as a next-token model). Updates are count
    increments — milliseconds, no retraining."""

    def __init__(self, vocab: dict[str, int], k: float = 0.1):
        self.vocab = vocab
        self.k = k
        self.tri: dict[tuple[int, int], np.ndarray] = {}
        self.bi: dict[int, np.ndarray] = {}
        self.uni = np.zeros(len(vocab))
        self.n_constructions = 0

    def update(self, token_lists: list[list[str]]) -> None:
        V = len(self.vocab)
        for toks in token_lists:
            padded = [BOS, BOS] + toks
            ids = [self.vocab[t] for t in padded]
            for i in range(2, len(ids)):
                c2 = (ids[i - 2], ids[i - 1])
                if c2 not in self.tri:
                    self.tri[c2] = np.zeros(V)
                    self.n_constructions += 1
                self.tri[c2][ids[i]] += 1
                if ids[i - 1] not in self.bi:
                    self.bi[ids[i - 1]] = np.zeros(V)
                self.bi[ids[i - 1]][ids[i]] += 1
                self.uni[ids[i]] += 1

    def _dist(self, c2: tuple[int, int]) -> np.ndarray:
        V = len(self.vocab)
        parts = []
        tri = self.tri.get(c2)
        parts.append((0.6, tri / tri.sum()) if tri is not None and tri.sum() else (0.0, None))
        bi = self.bi.get(c2[1])
        parts.append((0.3, bi / bi.sum()) if bi is not None and bi.sum() else (0.0, None))
        uni = (self.uni + self.k) / (self.uni + self.k).sum()
        used = sum(w for w, d in parts if d is not None)
        dist = (1 - used) * uni
        for w, d in parts:
            if d is not None:
                dist = dist + w * d
        return dist / dist.sum()

    def perplexity(self, token_lists: list[list[str]]) -> float:
        nll, n = 0.0, 0
        for toks in token_lists:
            padded = [BOS, BOS] + toks
            ids = [self.vocab[t] for t in padded]
            for i in range(2, len(ids)):
                p = self._dist((ids[i - 2], ids[i - 1]))[ids[i]]
                nll -= np.log(max(p, 1e-12))
                n += 1
        return float(np.exp(nll / n))


def lm_comparison(train_lists, test_lists, seed: int) -> dict:
    vocab = _vocab(train_lists + test_lists)
    Xtr, ytr = _trigram_examples(train_lists, vocab)
    Xte, yte = _trigram_examples(test_lists, vocab)

    neural = TinyNeuralLM(len(vocab), seed)
    t0 = time.perf_counter()
    neural.train(Xtr, ytr, seed=seed)
    neural_train_s = time.perf_counter() - t0

    ledger = LedgerLM(vocab)
    t0 = time.perf_counter()
    ledger.update(train_lists)
    ledger_build_s = time.perf_counter() - t0

    # Row 4: ingest the SAME 100 new sentences into each.
    new = test_lists[:100]
    t0 = time.perf_counter()
    ledger.update(new)
    ledger_update_s = time.perf_counter() - t0
    Xn, yn = _trigram_examples(train_lists + new, vocab)
    t0 = time.perf_counter()
    retrained = TinyNeuralLM(len(vocab), seed)
    retrained.train(Xn, yn, seed=seed)
    neural_retrain_s = time.perf_counter() - t0

    return {
        "neural_ppl": round(neural.perplexity(Xte, yte), 2),
        "ledger_ppl": round(ledger.perplexity(test_lists), 2),
        "neural_params": neural.n_params,
        "ledger_constructions": ledger.n_constructions,
        "neural_train_s": round(neural_train_s, 2),
        "ledger_build_s": round(ledger_build_s, 4),
        "ledger_update_ms": round(ledger_update_s * 1000, 2),
        "neural_retrain_s": round(neural_retrain_s, 2),
    }


# ── row 7: tiny neural renderer ──

ROLE_ORDER = ("agent", "verb", "recipient", "article", "object")


class TinyNeuralRenderer:
    """frame -> token sequence via MLP over role-value one-hots; greedy decode.
    Small enough to be honest about capacity, big enough to memorize — the
    point is whether it stays inside the frame. Templates cannot leave it."""

    def __init__(self, vocab: dict[str, int], seed: int, hidden: int = 48,
                 max_len: int = 6):
        V = len(vocab)
        self.vocab = vocab
        self.inv = {i: w for w, i in vocab.items()}
        self.max_len = max_len
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, 0.1, (len(ROLE_ORDER) * V, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = rng.normal(0, 0.1, (hidden, max_len * V))
        self.b2 = np.zeros(max_len * V)

    @property
    def n_params(self) -> int:
        return sum(a.size for a in (self.W1, self.b1, self.W2, self.b2))

    def _encode(self, frames: list[dict[str, str]]) -> np.ndarray:
        V = len(self.vocab)
        X = np.zeros((len(frames), len(ROLE_ORDER) * V))
        for i, frame in enumerate(frames):
            for r, role in enumerate(ROLE_ORDER):
                if role in frame:
                    X[i, r * V + self.vocab[frame[role]]] = 1.0
        return X

    def train(self, frames, token_lists, epochs: int = 200, lr: float = 0.5,
              seed: int = 0) -> None:
        V = len(self.vocab)
        X = self._encode(frames)
        Y = np.full((len(frames), self.max_len), self.vocab["."])
        for i, toks in enumerate(token_lists):
            for j, t in enumerate(toks[: self.max_len]):
                Y[i, j] = self.vocab[t]
        rng = np.random.default_rng(seed)
        for _ in range(epochs):
            idx = rng.permutation(len(X))
            Xb, Yb = X[idx], Y[idx]
            h = np.tanh(Xb @ self.W1 + self.b1)
            logits = (h @ self.W2 + self.b2).reshape(len(Xb), self.max_len, V)
            logits -= logits.max(axis=2, keepdims=True)
            p = np.exp(logits)
            p /= p.sum(axis=2, keepdims=True)
            d = p
            for pos in range(self.max_len):
                d[np.arange(len(Yb)), pos, Yb[:, pos]] -= 1
            d = d.reshape(len(Xb), -1) / len(Xb)
            dW2 = h.T @ d
            dh = d @ self.W2.T * (1 - h ** 2)
            self.W2 -= lr * dW2
            self.b2 -= lr * d.sum(0)
            self.W1 -= lr * (Xb.T @ dh)
            self.b1 -= lr * dh.sum(0)

    def render(self, frame: dict[str, str]) -> list[str]:
        V = len(self.vocab)
        X = self._encode([frame])
        h = np.tanh(X @ self.W1 + self.b1)
        logits = (h @ self.W2 + self.b2).reshape(self.max_len, V)
        out = []
        for pos in range(self.max_len):
            tok = self.inv[int(logits[pos].argmax())]
            out.append(tok)
            if tok == ".":
                break
        return out
