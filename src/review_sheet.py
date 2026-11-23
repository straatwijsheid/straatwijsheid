"""Local-knowledge review sheet, one per gemeente: the streets where a person who knows the place can tell us most.

  python src/review_sheet.py Eindhoven Breda     # (re)writes <knowledge>/gemeenten/<province>/<gemeente>/REVIEW.md for each
  python src/review_sheet.py --all               # every gemeente in the registry
  python src/review_sheet.py --print Eindhoven   # to the terminal instead, nothing written
  python src/review_sheet.py --export F.json.gz  # save what the sheets are made from (a release asset)
  python src/review_sheet.py --all --inputs F.json.gz   # regenerate from that file, without the build (what the knowledge repository's workflow does)

The sheet is Dutch first, English beside it (bilingual headers). Sections: streets read as a person with no namesake (per buurt), further
checks, place readings and surname readings that the switched-off rules would change (`wikidata_place_review`, `bare_surname`), and streets
whose kind rests on the buurt's theme alone. A street is asked about once, in the first section that claims it.

The sheet is the contributor's form: they type into the "Your answer" column (free text, easy in the GitHub editor), e.g.
`Jan Ban, organist` or `wrong: not a composer street`. Regenerating keeps every answer already in the file: it is read back from
the existing sheet and written into the new one. An answer for a street that is no longer on the list (it was identified since,
or its reading changed) moves to the last section rather than being dropped, so nothing typed is
lost. Answers are turned into corrections (`corrections.json`, tier 2 or 1) by a maintainer; see CONTRIBUTING.md."""
from __future__ import annotations

import collections
import json
import re
import sys

import config
import gemeenten as gem
import knowledge
from tiers import THEME_SOURCES

FILE = "REVIEW.md"
ORPHANS = "Antwoorden op straten die niet meer gevraagd worden (Answers for streets no longer listed)"
HEADER_CELLS = {"Street", "Straat (Street)"}
ANSWER = "Uw antwoord (Your answer)"
INTRO = (
    "Welkom! Dit blad vraagt om uw lokale kennis. Waar we een straatnaam niet kunnen thuisbrengen, staat de straat hieronder. "
    "Typ in de laatste kolom wat u weet, bijvoorbeeld `Jan Ban, organist` of `fout: dit is een plant`; sla over wat u niet weet. "
    "Gebruik het teken `|` niet in een antwoord. Uitleg en bronnen: [REVIEWING](https://github.com/straatwijsheid/knowledge/blob/main/REVIEWING.md).\n\n"
    "*Welcome! This sheet asks for your local knowledge. Where we cannot place a street name, the street is listed below. Type what you know in "
    "the last column, for example `Jan Ban, organist` or `wrong: this is a plant`; skip any you do not know. Do not use the `|` character in an answer. How to, and what counts as a source: see the link above.*\n")
S_PERSONS = ("Personen zonder bekende naamgever (Streets read as a person, namesake unknown)",
             "Deze straten lezen we als *een persoon van een bepaald soort*, maar wie het was weten we niet. Per buurt: het naamgevingsthema dat we zagen. "
             "*We read these as a kind of person but have not identified who; per buurt, the naming theme we detected.*\n")
S_EXTRA = ("Nog te controleren (Further checks: already labelled, but they look wrong)", "")
S_PLACES = ("Is dit wel een plaats? (Is this really a place?)",
            "Wikidata koppelde deze naam aan een plaats, maar dat lijkt onjuist of misleidend. Ons voorstel is nog niet toegepast. "
            "*Wikidata matched these names to a place that looks wrong or misleading; our proposal is not applied yet. Is the street named after a place, and which?*\n")
S_SURNAMES = ("Achternaam of gewoon woord? (Surname or ordinary word?)",
              "Deze naam staat in Wikidata als achternaam, maar is ook een gewoon woord. Ons voorstel is nog niet toegepast. "
              "*These names are in Wikidata as a family name but are also ordinary words; our proposal is not applied yet. Which is it, and who if a person?*\n")
S_THEME = ("Gelezen via het buurtthema (Read from the buurt's theme only)",
           "Het soort naamgever volgt hier alleen uit het thema van de buurt, niet uit de naam zelf. Klopt het? "
           "*The kind here follows from the buurt's theme alone, not from the name itself. Is it right?*\n")


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
        if len(cells) < 2 or cells[0] in HEADER_CELLS or cells[0] == "" or set(cells[0]) <= set("-: "):
            continue
        if cells[-1]:
            out[cells[0]] = cells[-1]
    return out


def candidates(rows: list[dict], code: str) -> dict[str, list[dict]]:
    """buurt -> the streets of the gemeente read as a person but with no namesake."""
    by = collections.defaultdict(list)
    for r in rows:
        if r["gemeente_code"] == code and r["category"] == "person" and not r.get("entity_label") and r["evidence_tier"] >= 3:
            by[r["buurt"] if isinstance(r["buurt"], str) and r["buurt"] else "(no buurt)"].append(r)
    return by


def theme_read(rows: list[dict], code: str) -> list[dict]:
    """Streets whose kind rests on the buurt's theme alone (tier 4, not a person without namesake, which `candidates` asks about)."""
    return sorted((r for r in rows if r["gemeente_code"] == code and r["evidence_tier"] == 4 and r["source"] in THEME_SOURCES
                   and not (r["category"] == "person" and not r.get("entity_label"))), key=lambda r: r["street"])


def anchor(heading: str, seen: dict | None = None) -> str:
    """The id GitHub gives a heading: lower case, punctuation removed, spaces to hyphens; a repeat gets -1, -2..."""
    a = re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
    if seen is not None:
        n = seen.get(a, 0)
        seen[a] = n + 1
        a = a if n == 0 else f"{a}-{n}"
    return a


def placements(text: str) -> dict[str, str]:
    """street -> the anchor of the heading it is asked about under, read from the sheet itself so a link can never point at a street that is
    not there. Streets listed only as an old answer (the last section) are not asked about and are left out."""
    out: dict[str, str] = {}
    seen: dict[str, int] = {}
    here = None
    for line in text.splitlines():
        m = re.match(r"#{2,3} (.+)", line)
        if m:
            a = anchor(m.group(1), seen)
            here = None if m.group(1).startswith(ORPHANS) else a
            continue
        if here and line.startswith("| "):
            street = line[2:].split(" | ", 1)[0].strip()
            if street not in HEADER_CELLS and not set(street) <= set("-: "):
                out.setdefault(street, here)
    return out


def sheet_path(code: str):
    return knowledge.gemeente_dir(code) / FILE


def kind(r) -> str:
    """'place: foreign town (Damme)' from a street record or a proposal (anything with category, subcategory, entity_label)."""
    get = r.get if isinstance(r, dict) else lambda k: getattr(r, k, None)
    sub = (get("subcategory") or "").replace("_", " ")
    label = get("entity_label")
    return f"{get('category')}: {sub}{f' ({label})' if label else ''}" if sub or label else str(get("category"))


def table(header: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + rows


def render(name: str, by: dict[str, list[dict]], notes: dict, extra: list[dict], answers: dict[str, str],
           held: dict[str, list[tuple]] | None = None, themed: list[dict] | None = None, settled: set[str] = frozenset()) -> str:
    """The sheet text. `notes`: street -> our note; `extra`: further checks ({street, buurt, question}); `answers`: street -> answer to keep;
    `held`: {"places": [...], "surnames": [...]} of (street, now, proposal, note); `themed`: streets read from the buurt theme only.
    A street appears once: in the first section that asks about it. `settled`: streets that already have a correction; an answer for one of those
    that is no longer asked about is dropped instead of being kept in the last section."""
    used: set[str] = set()      # streets whose answer has a place in this sheet
    asked = {r["street"] for items in by.values() for r in items}
    out = [f"# Review sheet / Controleblad: {name}\n", INTRO]

    def answer(street):
        used.add(street)
        return cell(answers.get(street, ""))

    def heading(section):
        out.append(f"## {section[0]}\n")
        if section[1]:
            out.append(section[1])

    if by:
        heading(S_PERSONS)
    for b, items in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        theme = items[0].get("buurt_theme") or "(none)"
        out.append(f"### {b} ({name})\n*{len(items)} {'straat' if len(items) == 1 else 'straten'} (streets). Buurtthema (Buurt theme):* {theme}\n")
        out.extend(table(["Straat (Street)", "Wij lezen het als (We read it as)", "Niveau (Tier)", "Onze notitie (Our note)", ANSWER], [
            f"| {cell(r['street'])} | {(r.get('subcategory') or 'person').replace('_', ' ')} | {r['evidence_tier']} | {cell(notes.get(r['street']))} |{tail(answer(r['street']))}"
            for r in sorted(items, key=lambda r: r["street"])]))
        out.append("")
    if extra:
        heading(S_EXTRA)
        out.append("")
        out.extend(table(["Straat (Street)", "Buurt", "Vraag (Question)", ANSWER], [
            f"| {cell(x['street'])} | {cell(x['buurt'])} | {cell(x['question'])} |{tail(answer(x['street']))}" for x in extra]))
        out.append("")
    for key, section in (("places", S_PLACES), ("surnames", S_SURNAMES)):
        items = [h for h in (held or {}).get(key, []) if h[0] not in asked]
        asked |= {h[0] for h in items}
        if items:
            heading(section)
            out.extend(table(["Straat (Street)", "Nu (Now)", "Voorstel (Proposal)", "Onze notitie (Our note)", ANSWER], [
                f"| {cell(s)} | {cell(now)} | {cell(prop)} | {cell(note)[:160]} |{tail(answer(s))}" for s, now, prop, note in sorted(items)]))
            out.append("")
    themed = [r for r in (themed or []) if r["street"] not in asked]
    if themed:
        heading(S_THEME)
        out.extend(table(["Straat (Street)", "Buurt", "Wij lezen het als (We read it as)", "Buurtthema (Buurt theme)", ANSWER], [
            f"| {cell(r['street'])} | {cell(r['buurt']) if isinstance(r['buurt'], str) else ''} | {kind(r)} | {cell(r.get('buurt_theme'))[:80]} |{tail(answer(r['street']))}" for r in themed]))
        out.append("")
    gone = {s: a for s, a in answers.items() if s not in used and s not in settled}
    if gone:
        out.append(f"## {ORPHANS}\n\nBeantwoord, maar de straat wordt niet meer gevraagd (inmiddels geïdentificeerd of anders gelezen); een beheerder vergelijkt ze met de correcties. "
                   "*Answered, but the street is no longer asked about; a maintainer checks them against the corrections.*\n")
        out.extend(table(["Straat (Street)", ANSWER], [f"| {cell(s)} | {cell(a)} |" for s, a in sorted(gone.items())]))
        out.append("")
    return "\n".join(out) + "\n"


def held_proposals(rows: list[dict]) -> dict[str, dict[str, list[tuple]]]:
    """The proposals of the rules that are switched off until reviewed (rules_status.json), as {gemeente_code: {"places"|"surnames": [(street, now, proposal, note)]}}."""
    import reconcile
    from rules import place_review, surnames
    from rules.base import Context
    ctx = Context.load(final=reconcile.compute_final())
    out: dict = collections.defaultdict(lambda: {"places": [], "surnames": []})
    for key, rule in (("places", place_review.review), ("surnames", surnames.resolve)):
        for o in rule(ctx):
            cur = ctx.rows.get(o.key)
            if cur is not None and kind(cur) != kind(o):
                out[o.gemeente_code][key].append((o.street, kind(cur), kind(o), o.notes or ""))
    return out


def build(code: str, rows: list[dict], existing: str = "", held: dict | None = None) -> str:
    """The sheet for one gemeente, carrying over the answers in `existing` (the current file's text)."""
    n = knowledge.read_json(knowledge.gemeente_dir(code) / "review_notes.json", {})
    corrected = {c["street"] for c in knowledge.read_json(knowledge.gemeente_dir(code) / "corrections.json", {}).get("corrections", [])}
    return render(gem.name_of(code), candidates(rows, code), n.get("notes", {}), n.get("extra", []), parse_answers(existing),
                  (held or {}).get(code), theme_read(rows, code), corrected)


ROW_FIELDS = ("gemeente_code", "street", "buurt", "category", "subcategory", "entity_label", "evidence_tier", "source", "buurt_theme")


def export_inputs(path: str) -> None:
    """Write what a sheet is made from (the street rows and the held proposals) to one small file, so sheets can be regenerated elsewhere without the build."""
    import gzip
    rows = json.loads((config.ENRICHED / "streets_final.json").read_text())
    slim = [{k: r.get(k) for k in ROW_FIELDS} for r in rows]
    data = {"rows": slim, "held": held_proposals(rows)}
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{path}: {len(slim)} streets, held proposals for {len(data['held'])} gemeenten")


def load_inputs(path: str):
    import gzip
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    return data["rows"], data["held"]


def main(args):
    if "--export" in args:
        return export_inputs(args[args.index("--export") + 1])
    inputs = args[args.index("--inputs") + 1] if "--inputs" in args else None
    show = "--print" in args
    names = [a for i, a in enumerate(args) if a not in ("--print", "--all", "--inputs") and (not inputs or a != inputs)]
    if not names and "--all" not in args:
        sys.exit(__doc__)
    names = sorted(gem.index()) if "--all" in args else [gem.code_of(a) for a in names]
    if inputs:
        rows, held = load_inputs(inputs)
    else:
        rows = json.loads((config.ENRICHED / "streets_final.json").read_text())
        held = held_proposals(rows)
    for code in names:
        path = sheet_path(code)
        text = build(code, rows, path.read_text() if path.exists() else "", held)
        if show:
            print(text)
            continue
        kept = len(parse_answers(path.read_text())) if path.exists() else 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"{path.relative_to(config.KNOWLEDGE)}: {sum(1 for l in text.splitlines() if l.startswith('| ') and 'Straat (Street)' not in l)} streets asked, {kept} answers kept")


if __name__ == "__main__":
    main(sys.argv[1:])
