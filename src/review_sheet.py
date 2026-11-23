"""Local-knowledge review sheet: streets in a gemeente read as a kind of person but with no namesake, grouped by buurt.

  python src/review_sheet.py Eindhoven Breda     # (re)writes <knowledge>/gemeenten/<province>/<gemeente>/REVIEW.md for each
  python src/review_sheet.py --print Eindhoven   # to the terminal instead, nothing written

The sheet is the contributor's form: they type into the "Your answer" column (free text, easy in the GitHub editor), e.g.
`Jan Ban, organist` or `wrong: not a composer street`. Regenerating keeps every answer already in the file: it is read back from
the existing sheet and written into the new one. An answer for a street that is no longer on the list (it was identified since,
or its reading changed) moves to the section "Answers for streets no longer listed" rather than being dropped, so nothing typed is
lost. Answers are turned into corrections (`corrections.json`, tier 2 or 1) by a maintainer; see CONTRIBUTING.md."""
from __future__ import annotations

import collections
import json
import re
import sys

import config
import gemeenten as gem
import knowledge

FILE = "REVIEW.md"
ORPHANS = "Answers for streets no longer listed"
INTRO = ("Streets read as *a person of some kind* but with no namesake identified. Per buurt: the naming theme we detected, then each street "
         "with the kind we assigned. Type your answer in the last column, however is quickest, e.g. `Banstraat = Jan Ban, organist` or "
         "`Bertelmanstraat: wrong, a plant`. Skip any you do not know. Do not use the `|` character in an answer.\n")


def cell(text) -> str:
    """Text safe inside a table cell."""
    return str(text or "").replace("|", "/").replace("\n", " ").strip()


def tail(a: str) -> str:
    """An answer cell and the closing bar; an empty cell is `| |`."""
    return f" {a} |" if a else " |"


def parse_answers(text: str) -> dict[str, str]:
    """street -> answer, from every table row in a sheet whose last column ("Your answer", or the orphan table's) is filled in."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|") or not line.rstrip().endswith("|"):
            continue
        cells = [c.strip() for c in line.strip()[1:-1].split("|")]
        if len(cells) < 2 or cells[0] in ("Street", "") or set(cells[0]) <= set("-: "):
            continue
        if cells[-1]:
            out[cells[0]] = cells[-1]
    return out


def candidates(rows: list[dict], code: str) -> dict[str, list[dict]]:
    """buurt -> the streets of the gemeente to ask about."""
    by = collections.defaultdict(list)
    for r in rows:
        if r["gemeente_code"] == code and r["category"] == "person" and not r.get("entity_label") and r["evidence_tier"] >= 3:
            by[r["buurt"] or "(no buurt)"].append(r)
    return by


def render(name: str, by: dict[str, list[dict]], notes: dict, extra: list[dict], answers: dict[str, str]) -> str:
    """The sheet text. `notes`: street -> our note; `extra`: further checks ({street, buurt, question}); `answers`: street -> answer to keep."""
    used: set[str] = set()
    out = [f"# Review sheet: {name}\n", INTRO]

    def answer(street):
        used.add(street)
        return cell(answers.get(street, ""))

    for b, items in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        theme = items[0].get("buurt_theme") or "(none)"
        out.append(f"## {b} ({name}): {len(items)} {'street' if len(items) == 1 else 'streets'}\n*Buurt theme detected:* {theme}\n")
        out.append("| Street | We read it as | Tier | Our note | Your answer |\n|---|---|---|---|---|")
        for r in sorted(items, key=lambda r: r["street"]):
            kind = (r.get("subcategory") or "person").replace("_", " ")
            out.append(f"| {cell(r['street'])} | {kind} | {r['evidence_tier']} | {cell(notes.get(r['street']))} |{tail(answer(r['street']))}")
        out.append("")
    if extra:
        out.append("## Further checks: already labelled, but they look wrong\n\n| Street | Buurt | Question | Your answer |\n|---|---|---|---|")
        for x in extra:
            out.append(f"| {cell(x['street'])} | {cell(x['buurt'])} | {cell(x['question'])} |{tail(answer(x['street']))}")
        out.append("")
    gone = {s: a for s, a in answers.items() if s not in used}
    if gone:
        out.append(f"## {ORPHANS}\n\nThese were answered but the street is no longer asked about (identified since, or read differently now). "
                   "A maintainer checks them against the corrections.\n\n| Street | Your answer |\n|---|---|")
        out.extend(f"| {cell(s)} | {cell(a)} |" for s, a in sorted(gone.items()))
        out.append("")
    return "\n".join(out) + "\n"


def build(code: str, rows: list[dict], existing: str = "") -> str:
    """The sheet for one gemeente, carrying over the answers in `existing` (the current file's text)."""
    n = knowledge.read_json(knowledge.gemeente_dir(code) / "review_notes.json", {})
    return render(gem.name_of(code), candidates(rows, code), n.get("notes", {}), n.get("extra", []), parse_answers(existing))


def main(args):
    show = "--print" in args
    names = [a for a in args if a != "--print"] or ["Eindhoven"]
    rows = json.loads((config.ENRICHED / "streets_final.json").read_text())
    for a in names:
        code = gem.code_of(a)
        path = knowledge.gemeente_dir(code) / FILE
        text = build(code, rows, path.read_text() if path.exists() else "")
        if show:
            print(text)
            continue
        kept = len(parse_answers(path.read_text())) if path.exists() else 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"{path.relative_to(config.KNOWLEDGE)}: {len(candidates(rows, code))} buurten, {kept} answers kept")


if __name__ == "__main__":
    main(sys.argv[1:])
