"""Calibration metrics of a probability-valued decision (spec v2 §5): AUROC, ECE, Brier."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

import numpy as np


def auroc(labels: Sequence[int], scores: Sequence[float]) -> float:
    """Rank-based AUROC with ties averaged; nan when only one class is present."""
    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    positives, negatives = int(y.sum()), int((1 - y).sum())
    if positives == 0 or negatives == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=float)
    sorted_scores = s[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float(
        (ranks[y == 1].sum() - positives * (positives + 1) / 2)
        / (positives * negatives)
    )


def ece(labels: Sequence[int], scores: Sequence[float], bins: int = 10) -> float:
    y = np.asarray(labels, dtype=float)
    s = np.asarray(scores, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for low, high in pairwise(edges):
        mask = (s >= low) & ((s < high) if high < 1.0 else (s <= high))
        if mask.any():
            total += mask.mean() * abs(y[mask].mean() - s[mask].mean())
    return float(total)


def brier(labels: Sequence[int], scores: Sequence[float]) -> float:
    y = np.asarray(labels, dtype=float)
    s = np.asarray(scores, dtype=float)
    return float(((s - y) ** 2).mean())


def accuracy_at(labels: Sequence[int], scores: Sequence[float], tau: float) -> float:
    y = np.asarray(labels, dtype=int)
    predicted = (np.asarray(scores, dtype=float) >= tau).astype(int)
    return float((predicted == y).mean())


def balanced_accuracy_at(
    labels: Sequence[int], scores: Sequence[float], tau: float
) -> float:
    y = np.asarray(labels, dtype=int)
    predicted = (np.asarray(scores, dtype=float) >= tau).astype(int)
    tpr = (predicted[y == 1] == 1).mean() if (y == 1).any() else 0.0
    tnr = (predicted[y == 0] == 0).mean() if (y == 0).any() else 0.0
    return float((tpr + tnr) / 2)


def best_threshold(labels: Sequence[int], scores: Sequence[float]) -> float:
    """The score that maximises balanced accuracy; ties go to the lower threshold."""
    candidates = sorted({float(s) for s in scores})
    return max(
        candidates, key=lambda tau: (balanced_accuracy_at(labels, scores, tau), -tau)
    )
