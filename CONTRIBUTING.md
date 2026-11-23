# Contributing

Straatwijsheid has two repositories, and where a change goes depends on what it is:

| You want to... | It goes in |
|---|---|
| fix or add what a street is named after, exclude a wrong rule proposal, add a gemeente's data | [knowledge](https://github.com/straatwijsheid/knowledge) (CC-BY 4.0) |
| change how the pipeline, rules or map work | this repository (MIT) |

Knowledge is data; code only holds logic. Improve a rule by editing its data first (`knowledge/global/`), and touch code only when the logic is wrong.
Open an issue before a large change. Questions and ideas are welcome as issues too.

## Set up

Python 3.14 (what CI uses) in a virtualenv, run from the repository root:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python src/pipeline.py bootstrap     # creates build/ and clones the knowledge repository into knowledge/
.venv/bin/python src/config.py                 # shows where everything lives
```

`knowledge/` is a checkout of the knowledge repository, git-ignored here: commit knowledge changes **inside `knowledge/`**, to the knowledge repository.
`build/` holds rebuildable data and is never committed. Personal settings (a contact address for Wikidata, a different build directory) go in
`config.local.toml` (git-ignored, copy `config.example.toml`) or in environment variables, never in a tracked file.

## Run the tests

Each test file is a script; there is no test runner to install. No network is needed.

```bash
for t in tests/test_*.py; do .venv/bin/python $t | tail -1; done
```

CI runs the same on every push and pull request, against the knowledge repository's `main` and a small golden fixture (`tests/fixture`).
If you change output on purpose, update the fixture's expected files in the same commit and say why.

## Add a gemeente

```bash
.venv/bin/python src/pipeline.py add Tilburg          # acquire -> Wikidata -> reconcile -> themes -> rules check -> outputs
.venv/bin/python src/pipeline.py status               # what is still missing at each stage
```

A gemeente is identified by its CBS code (`GM0855`), not its name, because two gemeenten can share a name (Bergen in Noord-Holland and in Limburg).
A name works when it is unique; otherwise pass the code. The first fetch adds the gemeente to the registry,
`knowledge/global/gemeenten_index.json` (code, name, province), and the rules and reviews write that gemeente's files into `knowledge/gemeenten/<province>/<gemeente>/`.
Where the default acquisition fails for a gemeente (merged or renamed gemeenten), the exception goes in `knowledge/global/gemeenten.json`.

Then run `pipeline.py rebuild`, look at the map (`build/output/streets_map.html`, serve it with `python3 -m http.server --directory build/output`), and open a pull
request **to the knowledge repository** with the registry entry and the new gemeente folder. The raw and enriched data are rebuildable and stay out.

## Add a correction

A correction is a reviewed street-level decision and is the strongest layer: it wins over every rule. It lives in
`knowledge/gemeenten/<province>/<gemeente>/corrections.json`:

```json
{"gemeente": "Eindhoven", "street": "Mecklenburgstraat", "category": "person", "subcategory": "monarch_statesman",
 "entity_label": null, "entity_description": null, "confidence": 0.85,
 "reason": "a princely house is filed as 'monarch_statesman'; OSM supplies the namesake", "from_osm": true}
```

`category` is `person`, `place` or `thing`. **Always give a `reason`**, and where you can, a source (a Wikidata or OpenStreetMap link, a street sign, a local history book).
Then:

```bash
.venv/bin/python src/rules/run.py --apply corrections
.venv/bin/python src/pipeline.py rebuild
```

Commit `corrections.json` and the regenerated `overrides/corrections.json` together. Review-sheet answers (`REVIEW.md`) are the easier route for people who know a neighbourhood but not the tooling; see the knowledge repository.

A maintainer (re)generates sheets with `.venv/bin/python src/review_sheet.py <gemeente> ...` (or `--all`; every gemeente has one); it writes `REVIEW.md` into the gemeente's directory in the knowledge repository. Contributors type free text in the "Your answer" column. Regenerating reads those answers back from the existing file and keeps them, and an answer for a street that is no longer asked about moves to a section at the end instead of being dropped; `--print` shows a sheet without writing it. A sheet is Dutch first with English beside it, and asks about: streets read as a person with no namesake, places Wikidata may have got wrong, surname-or-ordinary-word readings (the last two are proposals of rules that are switched off until reviewed), and streets whose kind rests on the buurt theme alone. Each street is asked about once. Turn answers into corrections as above, then regenerate.

### Handle a review-sheet pull request

Contributors follow [knowledge/REVIEWING.md](https://github.com/straatwijsheid/knowledge/blob/main/REVIEWING.md). Every pull request on the knowledge repository is checked by a workflow (`check`, running `ingest_answers.py --validate-changed`): a sheet may differ only in its answer cells (anything else, even a heading, is an error), an answer must name someone, a correction needs a reason. Then, as a maintainer:

```bash
.venv/bin/python src/ingest_answers.py Eindhoven            # dry run: what each answer in the merged sheet would become
.venv/bin/python src/ingest_answers.py Eindhoven --write    # append the accepted ones to corrections.json
.venv/bin/python src/rules/run.py --apply corrections && .venv/bin/python src/pipeline.py rebuild
.venv/bin/python src/review_sheet.py Eindhoven              # settled answers leave the sheet
```

What an answer becomes (rules in `src/ingest_answers.py`):

- `Jan Ban, organist` (optionally with a link): accepted for a street the sheet reads as a person. It becomes a correction with the answer and the link in `reason` and `source_url`, confidence 0.8 with a link and 0.7 without. **Corrections are tier 2 at most**: a contributor's link makes the entry checkable and shows as `[source]` on the map, but tier 1 only comes from Wikidata or an OpenStreetMap etymology tag. Add a `from_osm` correction, or a tag in OpenStreetMap, if the link points to one.
- `probably ...`, `waarschijnlijk ...` or a trailing `?`: a guess; reported, never applied. Ask for a second indication in the pull request.
- `wrong: ...` / `fout: ...`: our reading is wrong; the command lists it for you to decide what the street is instead (a correction by hand, or a `rule_exclusions.json` entry when a rule proposed it).
- An answer for a street that is not a person-with-no-namesake street (a place or a held proposal) is listed for you: what it names is a judgement.

### Regenerate the sheets after a release

Sheets are made from `streets_final`, which needs the full build. So publishing exports what a sheet needs (`review_sheet.py --export`, see [docs/publishing.md](docs/publishing.md)) as the release asset `review-inputs.json.gz`, and the knowledge repository's workflow `regenerate sheets` (run it from the Actions tab, optionally with the release tag) re-renders every sheet from it and opens a pull request with the changes (branch `regenerate-sheets/...`; answers are kept). It needs the setting *Allow GitHub Actions to create and approve pull requests*.

## Add an exclusion

When a rule proposes something wrong, do not hand-edit its layer (the next `--apply` would bring it back). Add the street to
`knowledge/global/rule_exclusions.json` under the rule's name, with the reason:

```json
"vocabulary": {"Valkhof": "probably a place name rather than a falcon"}
```

`--check RULE` shows what a rule proposes now; `--apply RULE` regenerates its layer and prints how the layer changed. Review a `--check` before an `--apply`.

## Add or change a rule

Rules live in `src/rules/` (see `src/rules/README.md`): a pure function that takes a `Context` and returns `Override` records.

1. Write the function in a module in `src/rules/` and register it in `RULES` in `src/rules/run.py`; give it a place in `PRECEDENCE` in `src/overrides.py` (later wins).
2. Put word lists and other knowledge in `knowledge/global/`, not in code.
3. Add unit tests to `tests/test_rules.py`.
4. `--check` it on real data, then `--apply` it. The change to each layer is printed; read it.
5. Rebuild and run all the tests. Evidence only moves toward tier 1: a rule never replaces a verified (tier 1) street.

The principle behind every rule: the buurt decides between readings of a name, but never alone.

## Change the knowledge layout

The knowledge repository carries a `schema_version` file and core (`src/schema.py`) refuses a checkout whose version it does not read, so an old checkout or old code fails
at start-up with a message saying which side to update. If you change the layout or a file format in a way old code cannot read, bump the number in both
places in step: `schema_version` in the knowledge repository and `SCHEMA_VERSION` in `src/schema.py` (and `tests/fixture/knowledge/schema_version`), and merge the knowledge change first.

## Commits and pull requests

- One logical change per commit. A short imperative subject that says what changed; add the issue number, e.g. `Key gemeenten by CBS code, not by name (#1)`. Put the why in the body.
- Reference the issue a pull request closes. Keep generated files (layers, outputs) in the same commit as the change that produced them.
- Never commit secrets, personal contact addresses, or rebuildable data from `build/`.
- Say where knowledge comes from. A plausible guess is welcome when marked as such.

## Licences

Code contributions are under the MIT licence of this repository; knowledge contributions are under CC-BY 4.0 of the knowledge repository.
Data sources and their terms are in [NOTICE.md](NOTICE.md); do not add material from a source that does not allow reuse (no copied text from websites or books, only facts with a reference).
