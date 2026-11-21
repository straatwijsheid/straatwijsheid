# What are the streets named after?

A pipeline and an interactive map that work out what Dutch streets are named after: **a person, a place or a thing**,
with sub-kinds (composer, saint, tree, river, castle...), and test whether naming themes cluster by neighbourhood.

Current coverage: **all of Noord-Brabant, 59 gemeenten and 38,090 streets**, built up wave by wave from Eindhoven outwards.
The long-term goal is the whole of the Netherlands, and a steadily growing share of streets we can actually identify.
See [TODO.md](TODO.md) for what is next.

## What you get

| Output | Where |
|---|---|
| Interactive map (open it over http; gemeenten load on demand) | `output/streets_map.html` + `output/data/` |
| One row per street: category, sub-kind, namesake, evidence tier, source | `output/streets_classified.csv` |
| One row per buurt: its naming theme | `output/buurt_themes.csv` |
| Do naming themes cluster by wijk? (permutation tests) | `output/wijk_theme_clustering.json` |

Serve the map locally with `python3 -m http.server --directory output 8765` and open `http://localhost:8765/streets_map.html`.
Opened straight from disk it still works but loads the larger uncompressed files.

## How certain is each street? Evidence tiers

Every street carries an `evidence_tier` (defined in `src/tiers.py`, shown in the map tooltips and the CSV):

| Tier | Meaning | Share today |
|---|---|---|
| 1 | Identified, external evidence (Wikidata or a web source) | 7.7% |
| 2 | Identified from general knowledge, not verified | 33.7% |
| 3 | Kind known from the name (a title, a species word, a trade term...) but no individual | 16.1% |
| 4 | Kind inferred from the neighbourhood's naming theme, or a weak match | 4.4% |
| 5 | Not identified (generic or local names, anything unresolved) | 38.2% |

About 41% of streets name a specific namesake, but only about 8% have external evidence behind that. Refinement should only
ever move streets toward tier 1.

## How it works

1. **Acquire** street names (OpenStreetMap via Overpass) and buurt/wijk boundaries (CBS via PDOK) for a gemeente.
2. **Look up** each street's core name (the name without "straat", "laan"...) on Wikidata.
3. **Reconcile** the per-street Wikidata guesses with each buurt's naming theme. A confident individual match is trusted; a weak one
   gives way to a strongly themed buurt; surname-only matches without support are rejected.
4. **Rules and hand classification** (`src/rules/`, `data/knowledge/`, `data/enriched/manual_overrides.json`) add what Wikidata
   cannot: species, composers, saints, directional roads (`Eindhovensedijk`), titles, local names, and consistency audits.
5. **Analyse** whether themes cluster by wijk, **build the map**, **export CSVs**.

Guiding principles: the same name can mean different people in different places, so a namesake is only asserted where the street's
own buurt supports that kind of person; and a label resting on the buurt theme alone must also be backed by the name itself.

## Running it

Requirements: Python 3 in a virtualenv (`.venv/`); install with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. Run from the
repository root.

```bash
# any gemeente(s), end to end (acquire -> Wikidata -> reconcile -> themes -> rules check -> outputs)
export WIKIDATA_CONTACT="you@example.org"          # a contact for polite, fast Wikidata access; never stored in the repo
.venv/bin/python src/pipeline.py add Tilburg Breda
.venv/bin/python src/pipeline.py status             # what is missing at each stage
.venv/bin/python src/pipeline.py rebuild            # after rules/overrides/knowledge changed: reconcile, analyze, map, CSVs, tier statistics

# or stage by stage (each is also what pipeline.py runs)
.venv/bin/python src/acquire.py "Tilburg"           # street network from the CBS buurten outline + buurten; exceptions in data/knowledge/gemeenten.json
.venv/bin/python src/enrich_wikidata.py --missing   # every street name in streets.geojson not cached yet (resumable)
.venv/bin/python src/reconcile.py                   # Wikidata + themes + overrides -> data/enriched/streets_final.json
.venv/bin/python src/themes.py                      # buurt themes for buurten without one; then reconcile again
.venv/bin/python src/rules/run.py --check           # review what each rule proposes; --apply RULE to write it
.venv/bin/python src/analyze.py && .venv/bin/python src/build_map.py && .venv/bin/python src/export_csv.py

# tests
for t in tests/test_*.py; do .venv/bin/python $t | tail -1; done
```

Network notes: Overpass can refuse connections from busy IPs (a VPN endpoint change has fixed it), and Wikidata lookups run at
roughly 100 names a minute only when `WIKIDATA_CONTACT` is set.

## Repository layout

```
src/                 pipeline.py (orchestrator), acquire.py, enrich_wikidata.py, reconcile.py, themes.py, analyze.py, build_map.py, export_csv.py, tiers.py,
                     osm_etymology.py / osm_places.py (OpenStreetMap evidence), names/ (candidate table + resolver)
src/rules/           tested classification rules (see src/rules/README.md); run.py is the CLI
data/raw/            street networks and buurt boundaries per gemeente, plus the combined files
data/enriched/       Wikidata cache, buurt themes, manual_overrides.json, streets_final.json (the result)
data/knowledge/      curated knowledge the rules use: species, vocabularies, famous people, place corrections...
scripts/legacy/      the original wave-by-wave scripts, kept verbatim for provenance (not meant to be re-run)
output/              the map, its data files and the CSV/JSON exports
tests/               unit tests for the tiers and the rules
```

## Known limits

* Classification depth varies by gemeente (they were built in waves): the Kempen gemeenten are the weakest, with about half their streets unidentified.
* About a quarter of the labels that rest on a buurt's theme in the oldest gemeenten (~1.1k streets) look wrong on sampling.
* Many matches were made from general knowledge and have not been verified against Wikidata or the web (tier 2).
* The first classification passes were hand-written per gemeente; their results live in `manual_overrides.json`, and the scripts
  that produced them are archived, not re-runnable (`scripts/legacy/README.md`).

More detail on the method, data fields and findings is still to be written, see the Documentation section of [TODO.md](TODO.md).
