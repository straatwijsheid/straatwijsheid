"""Label repairs: a label must name the namesake, never repeat the street's road word.

Legacy vocabulary rules built saint labels by prefixing "Saint " to the word after "Sint", which kept the road word
("Saint Janstraat"). `repair_saint_labels` recomputes them ("Saint John")."""
from __future__ import annotations

import re

from .base import Context, Override
from .vocabulary import _saint_word, vocab

RULE = "label_cleanup"
ROAD_END = re.compile(r"(straat|laan|plein|weg|hof|pad|singel|dreef|steeg|kade|park)$", re.I)


def saint_label(label: str) -> str:
    word = _saint_word(label[len("Saint "):])
    return vocab()["SAINT"].get(word.lower()) or "Saint " + word


def repair_saint_labels(ctx: Context) -> list[Override]:
    out = []
    for r in ctx.final:
        lab = r.get("entity_label") or ""
        if r["category"] == "person" and r.get("subcategory") == "religious" and lab.startswith("Saint ") and ROAD_END.search(lab) \
                and r["source"] in ("claude_knowledge", "title_heuristic"):
            new = saint_label(lab)
            if new != lab:
                out.append(Override(r["gemeente_code"], r["street"], r["category"], r["subcategory"], new, r.get("entity_description"),
                                    r["confidence"], notes=r.get("notes"), rule=RULE))
    return out
