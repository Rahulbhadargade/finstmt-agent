"""Rank COA accounts for an unknown account code. Deterministic and explainable; an LLM can be added
later as one extra signal, but the output is always a *suggestion* that a human confirms."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

STOP = {"and", "the", "of", "for", "from", "to", "out", "old", "code", "reclass", "move", "into", "in"}
SYN = {"conf": "conference", "t&e": "travel entertainment", "dep": "depreciation", "amort": "amortization"}


def _tokens(text: str) -> set:
    text = text.lower()
    for k, v in SYN.items():
        text = text.replace(k, v)
    return {t for t in re.findall(r"[a-z]{3,}", text) if t not in STOP}


def suggest_accounts(code: int, texts: list, coa: dict, top: int = 3) -> list:
    words = _tokens(" ".join(texts))
    out = []
    for c, a in coa.items():
        if a["type"] == "Header":
            continue
        name_t = _tokens(a["name"])
        overlap = len(words & name_t) / len(name_t) if name_t else 0.0
        fuzzy = SequenceMatcher(None, " ".join(sorted(words)), " ".join(sorted(name_t))).ratio()
        text_score = max(overlap, 0.5 * fuzzy)
        prox = max(0.0, 1 - abs(c - code) / 100) if c // 100 == code // 100 else 0.0
        score = round(min(0.9, 0.5 * text_score + 0.5 * prox), 2)  # never claim >0.9 confidence
        out.append({"account": c, "name": a["name"], "confidence": score})
    return sorted(out, key=lambda x: -x["confidence"])[:top]
