"""Review-sheet answers -> corrections, and the checks a pull request on the knowledge repository must pass.

  python src/ingest_answers.py Eindhoven              dry run: what each answer in the sheet would become
  python src/ingest_answers.py Eindhoven --write      append the accepted ones to the gemeente's corrections.json
  python src/ingest_answers.py --validate-changed origin/main
                                                      check the sheets and corrections changed since that ref (what the knowledge repository's
                                                      pull-request workflow runs; needs only the knowledge checkout)

What an answer can be (typed in the "Your answer" column, free text):
  `Jan Ban, organist`                  a namesake: the name, then what we know about them. Accepted for a street the sheet reads as a person.
  `Jan Ban, organist https://...`      the same with a source link
  `probably Jan Ban` / `waarschijnlijk` a guess: reported, never applied
  `wrong: a plant` / `fout: ...`       our reading is wrong: reported for a maintainer, who decides what it is instead

An accepted answer becomes a correction (the strongest layer) with the answer and its source in `reason` and `source_url`. Corrections are tier 2
at most: a contributor's source makes the entry checkable, it does not make it tier 1 (tier 1 comes from Wikidata or an OpenStreetMap etymology tag).
Confidence is 0.8 with a source link and 0.7 without. Unsourced names are marked as local knowledge, unverified."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass

import config
import gemeenten as gem
import knowledge
import review_sheet as RS

WRONG = re.compile(r"^\s*(wrong|fout|onjuist|klopt niet|niet)\b\s*[:=,-]?\s*", re.I)
GUESS = re.compile(r"^\s*(probably|likely|maybe|perhaps|waarschijnlijk|misschien|mogelijk|denk(?: ik)?)\b\s*[:=,-]?\s*", re.I)
URL = re.compile(r"https?://[^\s<>)\]]+")
GENERIC = {"specific", "unspecified_individual", "other", "person", None, ""}
CATEGORIES = ("person", "place", "thing")


@dataclass
class Answer:
    raw: str
    kind: str                 # namesake | guess | wrong | unclear
    name: str = ""
    description: str = ""
    url: str = ""


def parse(text: str, street: str = "") -> Answer:
    """Read one free-text answer. A leading `Street =` (as in the sheet's example) is ignored."""
    raw = (text or "").strip()
    t = raw
    if street and t.lower().startswith(street.lower()):
        t = re.sub(r"^\s*[=:\-]\s*", "", t[len(street):])
    m = URL.search(t)
    url = m.group(0).rstrip(".,;") if m else ""
    t = URL.sub("", t).strip(" ,;()[]")
    if WRONG.match(t):
        return Answer(raw, "wrong", description=WRONG.sub("", t, count=1).strip())
    kind = "namesake"
    if GUESS.match(t) or t.endswith("?"):
        kind, t = "guess", GUESS.sub("", t, count=1).rstrip("?").strip()
    name, _, rest = t.partition(",")
    name, rest = name.strip(" ."), rest.strip()
    if not re.search(r"[^\W\d_]{2}", name):
        return Answer(raw, "unclear", url=url)
    return Answer(raw, kind, name, rest, url)


def person_rows(rows: list[dict], code: str) -> dict[str, dict]:
    """street -> record, for the streets the sheet reads as a person with no namesake (the ones a namesake answer applies to)."""
    return {r["street"]: r for items in RS.candidates(rows, code).values() for r in items}


def correction(code: str, street: str, row: dict, a: Answer) -> dict:
    sub = row.get("subcategory")
    return {"gemeente": gem.name_of(code), "street": street, "category": "person", "subcategory": sub if sub not in GENERIC else "other",
            "entity_label": a.name, "entity_description": a.description or None, "confidence": 0.8 if a.url else 0.7,
            "reason": f"review sheet answer: {a.raw} ({'source given' if a.url else 'local knowledge, unverified'})",
            **({"source_url": a.url} if a.url else {})}


def triage(code: str, rows: list[dict], text: str, corrected: set[str]) -> list[tuple]:
    """(street, answer, outcome, correction or None) for every answer in a sheet's text. outcome: `accept` or why not."""
    asked = RS.placements(text)
    people = person_rows(rows, code)
    out = []
    for street, raw in sorted(RS.parse_answers(text).items()):
        a = parse(raw, street)
        if street not in asked:
            out.append((street, a, "skip: not asked about on the sheet (an old answer)", None))
        elif street in corrected:
            out.append((street, a, "skip: already has a correction", None))
        elif a.kind == "unclear":
            out.append((street, a, "ask: could not read a name from the answer", None))
        elif a.kind == "wrong":
            out.append((street, a, "maintainer: the contributor says our reading is wrong", None))
        elif a.kind == "guess":
            out.append((street, a, "skip: a guess; needs a second indication", None))
        elif street not in people:
            out.append((street, a, "maintainer: not a person-with-no-namesake street, so what the answer names (person, place, thing) is a judgement", None))
        else:
            out.append((street, a, "accept", correction(code, street, people[street], a)))
    return out


def ingest(name: str, write: bool) -> int:
    code = gem.code_of(name)
    path = RS.sheet_path(code)
    if not path.exists():
        sys.exit(f"no review sheet for {gem.name_of(code)} at {path}")
    import json as _json
    rows = _json.loads((config.ENRICHED / "streets_final.json").read_text())
    cpath = knowledge.gemeente_dir(code) / "corrections.json"
    data = knowledge.read_json(cpath, {"corrections": []})
    results = triage(code, rows, path.read_text(), {c["street"] for c in data["corrections"]})
    new = [c for *_, c in results if c]
    for street, a, outcome, c in results:
        print(f"{street:32} {outcome}\n{'':32} answer: {a.raw[:100]}" + (f"\n{'':32} -> {c['entity_label']} ({c['subcategory']}), confidence {c['confidence']}" if c else ""))
    print(f"\n{len(new)} of {len(results)} answers accepted for {gem.name_of(code)}.")
    if write and new:
        data["corrections"].extend(new)
        knowledge.write_json(cpath, data)
        print(f"appended to {cpath.relative_to(config.KNOWLEDGE)}. Next: rules/run.py --apply corrections, pipeline.py rebuild, review_sheet.py {gem.name_of(code)}; "
              "commit corrections.json, the regenerated overrides and the sheet together.")
    elif new:
        print("dry run: add --write to append them to corrections.json")
    return 0


# --- checks for a pull request on the knowledge repository (no build needed) -------------------------------------------------------------------

def check_sheet(base: str, head: str) -> tuple[list[str], list[str]]:
    """(errors, notes) for a changed sheet. Everything except the answer cells must be as it was: headings (they are the links' anchors), tables,
    streets, order, prose. An answer must be readable."""
    import difflib
    errors, notes = [], []
    if not base.strip():
        return errors, ["a new sheet: not compared with a previous one"]
    nb, nh = RS.normalise(base).splitlines(), RS.normalise(head).splitlines()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, nb, nh, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        was, now = " / ".join(nb[i1:i2])[:100], " / ".join(nh[j1:j2])[:100]
        what = {"replace": "changed", "delete": "removed", "insert": "added"}[tag]
        errors.append(f"line {j1 + 1}: {what} outside the answer column (was: {was or '-'}; now: {now or '-'}). Sheets are generated; only the answers are yours to edit")
        if len(errors) >= 10:
            errors.append("... and more")
            break
    for n, street in RS.malformed(head):
        errors.append(f"line {n} ({street}): wrong number of columns (an answer cannot contain '|')")
    old, new = RS.parse_answers(base), RS.parse_answers(head)
    known = {c[0] for _, c, _ in RS.table_rows(base)}
    for street, raw in sorted(new.items()):
        if old.get(street) == raw or street not in known:
            continue
        a = parse(raw, street)
        if a.kind == "unclear":
            errors.append(f"{street}: could not read a name from the answer: {raw!r}")
        elif a.kind == "wrong":
            notes.append(f"{street}: marked as wrong ({a.description or 'no reason given'}); a maintainer decides what it is instead")
        elif a.kind == "guess":
            notes.append(f"{street}: a guess ({a.name}); it will not be applied without a second indication")
        elif not a.url:
            notes.append(f"{street}: no source link; it will be recorded as local knowledge, unverified (tier 2)")
    return errors, notes


def check_corrections(text: str) -> list[str]:
    errors = []
    try:
        entries = json.loads(text).get("corrections", [])
    except Exception as e:
        return [f"not valid JSON: {e}"]
    for i, e in enumerate(entries, 1):
        who = f"entry {i} ({e.get('street', '?')})"
        for field in ("gemeente", "street", "category", "reason"):
            if not e.get(field):
                errors.append(f"{who}: missing {field}")
        if e.get("category") and e["category"] not in CATEGORIES:
            errors.append(f"{who}: category must be one of {', '.join(CATEGORIES)}")
        c = e.get("confidence")
        if c is not None and not (isinstance(c, (int, float)) and 0 <= c <= 1):
            errors.append(f"{who}: confidence must be between 0 and 1")
        if not e.get("from_osm") and e.get("category") == "person" and not e.get("entity_label") and not e.get("subcategory"):
            errors.append(f"{who}: a person correction needs a subcategory or an entity_label")
    return errors


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(config.KNOWLEDGE), *args], capture_output=True, text=True, check=True).stdout


def validate_changed(ref: str) -> int:
    changed = git("diff", "--name-only", "--diff-filter=AM", f"{ref}...HEAD").split()
    failed = False
    for f in changed:
        if f.endswith("/REVIEW.md"):
            base = ""
            try:
                base = git("show", f"{ref}:{f}")
            except subprocess.CalledProcessError:
                pass
            errors, notes = check_sheet(base, (config.KNOWLEDGE / f).read_text())
        elif f.endswith("/corrections.json"):
            errors, notes = check_corrections((config.KNOWLEDGE / f).read_text()), []
        else:
            continue
        for n in notes:
            print(f"::notice file={f}::{n}")
        for e in errors:
            print(f"::error file={f}::{e}")
        print(f"{f}: {len(errors)} errors, {len(notes)} notes")
        failed |= bool(errors)
    return 1 if failed else 0


def main(args):
    if "--validate-changed" in args:
        return validate_changed(args[args.index("--validate-changed") + 1])
    names = [a for a in args if a != "--write"]
    if len(names) != 1:
        sys.exit(__doc__)
    return ingest(names[0], "--write" in args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
