# Repository model

The project lives in three places, with three lifecycles. Knowing which is which tells you where a change goes and what can be thrown away.

| | Core repository | Build directory | Knowledge repository |
|---|---|---|---|
| What | the code, tests and docs | everything that can be rebuilt | human judgement that cannot be regenerated |
| Where | `straatwijsheid/straatwijsheid` | `build/` (git-ignored; set `build_dir` to put it elsewhere) | `straatwijsheid/knowledge`, checked out at `knowledge/` (git-ignored in core) |
| Licence | MIT | not distributed as such | CC-BY 4.0 |
| Lifecycle | normal code review | delete and rebuild any time | pull requests from people with local knowledge |

## Core repository

The pipeline (`src/`), the rules (`src/rules/`), tests (`tests/`) with a small **golden fixture** (a few gemeenten with a canned Wikidata cache, `tests/fixture/`) and an end-to-end test, CI (`.github/workflows`), and the docs. It holds no data
beyond the fixture and `config.example.toml`.

## Build directory

`raw/` (OpenStreetMap and PDOK downloads, with dated, checksummed snapshots in `snapshots.json`), `enriched/` (the Wikidata cache, `streets_final.json`, derived buurt themes, OSM etymology), `names/` (the candidate table), `cache/`, and `output/` (the map, the CSVs,
reports, `PROVENANCE.json`). Nothing here is committed; `pipeline.py rebuild` recreates the downstream parts. Two things are not reproducible even though they are rebuildable in principle: Wikidata and OpenStreetMap change over time, so the Wikidata cache and
the raw snapshots are what a given build was made from, and each carries its date.

## Knowledge repository

- `global/`: the curated lists the rules read (vocabulary, species, famous people, common words, place corrections, OSM entity kinds), the rule exclusions and rule status, theme labels, the acquisition exceptions (`gemeenten.json`) and the **gemeente registry** (`gemeenten_index.json`: CBS code to name and province).
- `gemeenten/<province>/<gemeente>/`: per gemeente, `corrections.json` (reviewed decisions with reasons), `review_notes.json`, the review sheet `REVIEW.md`, and `overrides/<layer>.json`, one file per override layer: the frozen first-wave classifications (`legacy_hand`) and the layer each rule writes
  (regenerable with `rules/run.py --apply`, but stored here so a change to a classification is a reviewable diff).
- `schema_version`, `LICENSE`, `ATTRIBUTION.md`, a README for contributors.

Rule reference data lives here rather than in core because it is judgement as much as logic: improving a rule is mostly editing data, and a reviewer reads it as a diff. Code only holds logic. See [src/rules/README.md](../src/rules/README.md).

A gemeente is identified by its **CBS gemeentecode** (`GM0772`), never by name: two gemeenten can share a name (Bergen in Noord-Holland and in Limburg). The folder is `<province-slug>/<name-slug>`, so a pull request about one gemeente touches one directory.

## How the versions are tied together

- **Where the knowledge is.** Core reads one configured directory (`knowledge_dir`, default `knowledge/`). `pipeline.py bootstrap` clones the knowledge repository there.
- **A schema version.** The knowledge repository carries a `schema_version`; core refuses a checkout whose version it does not read, with a message saying which side to update (`src/schema.py`). A change to the layout bumps it in both places.
- **Provenance.** Every build writes `output/PROVENANCE.json`: the code commit, the knowledge commit (each marked dirty if modified) and the dates of the OpenStreetMap snapshots; the map shows them in its footer. Any published number can be tied to exact inputs.
- **Tests.** Most tests need no knowledge repository: they use the golden fixture or build their own small knowledge directory. The rule tests read the real curated lists and stop with a clear message if the checkout is missing. CI checks out the knowledge repository's `main` next to core.

## Settings and personal details

Paths, the Overpass URL and the optional Wikidata contact come from, in order, an environment variable, `config.local.toml` (git-ignored) or a default (`src/config.py`). A personal contact address lives only in the local file or the environment, never in either repository or in an output.

## Visibility and releases

Both repositories are public. `main` cannot be force-pushed or deleted. In the core repository the `test` workflow is a required check for pull requests; in the knowledge repository it is the `check` workflow (job `answers`), which keeps a pull request from changing anything in a review sheet but the answers. Administrators can bypass both. Pull requests opened by the sheet-regeneration workflow do not trigger checks (a limit of GitHub's default token), so an administrator merges those. Release assets (the built map, a dated raw snapshot) belong to releases, not to git history.
