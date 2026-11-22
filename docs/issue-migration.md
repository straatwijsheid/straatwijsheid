# TODO.md to GitHub issues: migration draft

Temporary working file. Delete it once the issues exist (step 2 of the plan). Nothing here has been created on GitHub yet.

## Rules used for this draft

- Only **open, actionable** work becomes an issue. Done items, measurements and one-off findings stay in git history, not in `docs/`.
- **Review work is not an issue.** Local-knowledge review (Eindhoven sheet, held `bare_surname` / `wikidata_place_review` proposals, declined place readings, 60-street spot-checks, the ~1,135 skimmed Wikidata place matches, the 9 OSM conflicts) becomes generated per-gemeente review sheets in the knowledge repo, driven by contributors through PRs. Only the *tooling* for the sheets is an issue (R1 to R6).
- **Personal OSM/Wikidata edits are not issues.** Applying `OSM_FIXES.md` and `WIKIDATA_FIXES.md` is the user's own editing work on external sites; the generated lists are the worklist.
- Granularity: one issue per actionable item; sub-bullets become a task list in the issue body.
- All issues go in `straatwijsheid/straatwijsheid` (core). The knowledge repo gets none.

## Labels and milestones to create

Labels (the GitHub defaults stay): `rules`, `osm`, `wikidata`, `scaling`, `review-sheets`, `tech-debt`, `pipeline`, `map`, `docs` (reuse the default `documentation` instead), `decision`, `proposed`.
Milestones: `M3 Public hygiene`, `M4 Documentation`, `M5 First public release`. Issues with no milestone are backlog.

---

## M3: Public hygiene

### H1. Identify gemeenten by CBS code (GM####), not by name
Labels: `pipeline`, `scaling`. Milestone: M3.
Override keys, snapshots and the street list are keyed `(gemeente name, street)`. That collides for same-named gemeenten (Bergen NH / Bergen L; check others when more provinces are added).
Task list:
- [ ] Add the CBS code to `global/gemeenten.json` and the street list.
- [ ] Key override layers, snapshots, corrections and review notes by code; keep the name for display.
- [ ] Migrate the existing layers; `streets_final.json` must be unchanged apart from the new key.
- [ ] Tests for a same-name pair.
Done when: two gemeenten with the same name can coexist in one build. Needed before any province beyond Noord-Brabant is added.

### H2. Data-source terms in NOTICE/README, plus a secret scan
Labels: `documentation`. Milestone: M3.
State: OpenStreetMap contributors (ODbL), CBS/PDOK (CC-BY 4.0), Wikidata (CC0), and how derived outputs may be reused. Run a secret scan over both repos and their history (none expected: `WIKIDATA_CONTACT` is never stored).
Done when: `NOTICE.md` covers every source and the scan result is recorded in the PR.

### H3. Contributing guide
Labels: `documentation`. Milestone: M3.
`CONTRIBUTING.md` in core and a matching section in the knowledge repo: how to add a gemeente, a rule, an exclusion, a correction; how to run the tests; commit conventions; how local knowledge reaches the knowledge repo.
Done when: a stranger can add a gemeente from the guide alone. Related: R5 (review-sheet answers).

### H4. Replace the personal contact address
Labels: `decision`. Milestone: M3.
Set up mail on straatwijsheid.nl, then replace the personal address on the GitHub org/account sign-up, org billing/contact and any contact line in README/CONTRIBUTING. The Wikidata contact stays in `config.local.toml` (never committed).
Done when: no personal address appears in either repo or the org profile.

### H5. Site copy: tagline and tier-5 label
Labels: `map`. Milestone: M3.
Tagline "Where the streets have a name"; tier-5 label "Where the streets have no (known) name", with a call to contribute through review-sheet PRs (link to R5 once it exists).

### H6. Knowledge repo `schema_version` check
Labels: `pipeline`. Milestone: M3.
The repository model calls for a `schema_version` file in the knowledge repo, checked by core at start-up (provenance already stamps the commit hash; nothing checks the schema). Add the file, the check, and a clear error on mismatch.
Done when: core refuses a knowledge checkout with an incompatible schema version.

## M4: Documentation

(Durable material only. No findings or measurements pages; see KPI1.)

### D1. Pipeline guide
Labels: `documentation`. Milestone: M4.
acquire (OSM/PDOK) -> Wikidata lookup -> reconcile -> rules -> analyze -> build map -> export CSV. Commands, inputs and outputs per step, ordering gotchas (reconcile -> buurt themes for new gemeenten -> reconcile), Overpass/Wikidata practicalities (`WIKIDATA_CONTACT`, rate limits), `pipeline.py bootstrap`.

### D2. Method and principles
Labels: `documentation`. Milestone: M4.
Person/place/thing taxonomy and sub-kinds; evidence tiers (`src/tiers.py`); the buurt decides between readings of a name but never alone; same-named streets are not assumed to share a namesake; kind-only labels (Willem, Hendrik...).

### D3. Data dictionary
Labels: `documentation`. Milestone: M4.
Every field in `streets_final.json`, `streets_classified.csv`, `buurt_themes*.json/csv`, the override layers and `knowledge/`; the meaning of `source`, `confidence`, `evidence_tier`, `notes`. Consider generating it from code so it cannot drift.

### D4. Rules and knowledge reference
Labels: `documentation`, `rules`. Milestone: M4.
Expand `src/rules/README.md`: each rule, its inputs, how to read a `--check`, how to add a rule or exclusion, the layer order (`PRECEDENCE`).

### D5. Map guide
Labels: `documentation`, `map`. Milestone: M4.
Panel, lazy per-gemeente loading, gzipped data, tooltips, tiers, legend, path/planned toggles.

### D6. Repository model and known limitations
Labels: `documentation`. Milestone: M4.
`docs/repository-model.md`: the three places (core, build, knowledge), what lives where, how versions are tied together (the agreed decisions only, trimmed to what is true today). `docs/limitations.md`: structural limits only (OSM coverage and the way-class caveat, theme-forced labels, legacy wave depth, Baarle-Hertog shared names), no measurements.

### D7. README refresh after M3
Labels: `documentation`. Milestone: M4.
Replace "See TODO.md for what is next" with the issue tracker, refresh the coverage claims, link the new docs.

## M5: First public release

### P1. Publish the map on GitHub Pages
Labels: `map`, `pipeline`. Milestone: M5.

### P2. Release assets and tag v0.1
Labels: `pipeline`. Milestone: M5.
Dated raw OSM snapshot and the Wikidata cache as release assets. `all_streets_wikidata.jsonl` (8 MB, hours to rebuild) published under CC0: it holds only QIDs, labels and descriptions (CC0) plus our derived category/confidence fields; no Wikipedia text (that would be CC-BY-SA). NOTICE states "Contains data from Wikidata (CC0 1.0)". Tag v0.1.

### P3. Make the repositories public
Labels: `decision`. Milestone: M5.
Blocked by H1 to H4 and D7. Check: both repos still private, secret scan clean, `KNOWLEDGE_READ_TOKEN` fallback (`github.token`) works once the knowledge repo is public, branch protection on `main`.

---

## Review-sheet tooling (core issues; the sheets themselves live in the knowledge repo)

### R1. Sheet generator writes to the knowledge repo and merges answers
Labels: `review-sheets`, `pipeline`. Backlog (start after M3).
Today `src/review_sheet.py` writes `REVIEW_EINDHOVEN.md` to the build output and overwrites it. Move to `knowledge/reviews/<gemeente>.md`. Answers live in the sheet's "Your answer" column, so regeneration must keep them: store answers machine-readably (for example `reviews/answers/<gemeente>.json`) and render them into the sheet.
Decide in this issue: free text (friendly to the GitHub UI) or a small structured form (safer to parse).

### R2. Ingest command: merged answers become corrections
Labels: `review-sheets`, `pipeline`. Blocked by R1.
Parse merged answers, validate (street exists, source given, confidence stated), and turn accepted ones into `corrections.json` entries carrying the contributor's source as `source_url`/`reason`. Unsourced person names never reach tier 1; "local knowledge" is tier 2 at most.

### R3. Knowledge-repo PR template and validation Action
Labels: `review-sheets`. Blocked by R2.
PR template, plus a GitHub Actions workflow on the knowledge repo that runs the R2 validation on every PR.

### R4. Generate a review sheet for every gemeente
Labels: `review-sheets`. Blocked by R1.
One Markdown file per gemeente, Dutch-primary with bilingual table headers `Nederlands (English)`. Which streets appear (person streets with no namesake, held rule proposals, declined place readings, low-confidence theme-forced labels) is decided here; the held `bare_surname` and `wikidata_place_review` proposals are a section type, not separate work. Include the Philipsdorp carry-overs (Henriëttestraat, Hubertastraat) and the Generalenbuurt theme check in the Eindhoven sheet.

### R5. Contributor guide for review sheets
Labels: `review-sheets`, `documentation`. Blocked by R1.
What counts as a source (a link, a document; "local knowledge" flagged as tier 2 at most), how to edit a sheet, how a PR becomes a correction. Linked from the map's tier-5 call to contribute (H5).

### R6. Automate sheet regeneration with GitHub Actions
Labels: `review-sheets`, `pipeline`. Blocked by R1, R3.
Open question: the sheets are generated from `streets_final.json`, which needs the full build (OSM, Wikidata, hours of lookups). Options: a scheduled or self-hosted runner running `pipeline.py rebuild` and opening a PR against the knowledge repo, or an Action in the knowledge repo that re-renders from a published `streets_final` release asset (no network) on a merged PR.

---

## Rules and resolver

### Q1. Improve `bare_surname` (common nouns are not surnames)
Labels: `rules`. Backlog.
Ankerstraat and Koggestraat were proposed as monarchs; about half of a 50-proposal sample was wrong. Exclude common nouns (use `common_words.txt` and `species.txt`), re-run `--check`, then remove it from `rules_status.json` once the sample is mostly right. Likewise for `wikidata_place_review` (turns Linden/Heide into foreign towns).

### Q2. Layer audit
Labels: `rules`, `tech-debt`. Backlog.
Per rule layer, review what a clean regeneration would change (`rules/run.py --check --cascade vocabulary` prints the diff), decide per rule whether the regenerated layer is better, and commit one at a time. Includes the drift in `species` (9 -> 0 entries) and `person_consensus` (3 -> 4) when re-applied alone. Do not regenerate wholesale.

### Q3. Review the remaining `--check` proposals
Labels: `rules`. Backlog.
`same_name_harmonise` (16), `person_consensus` (2), `theme_forced_name_fit` (2) and leftovers. Small enough to be a rule-owner task, not a review sheet; fold into Q2 if the layer audit goes first.

### Q4. Theme-forced labels
Labels: `rules`. Backlog.
About 1.1k non-local labels rest on the buurt theme plus a weak name fit (~25% of a sample wrong). Decide: re-check against Wikidata by surname, or flag low-confidence in the CSV and tooltips.

### Q5. Buurt-theme feedback loop
Labels: `rules`, `tech-debt`. Backlog.
394 hand-written themes plus 1,670 derived from street classifications that were themselves shaped by those themes. Decide whether derived themes are recomputed after rules change (`themes.py --rebuild`) and whether reconcile needs damping.

### Q6. Resolver: merge near-synonym subcategories
Labels: `rules`. Backlog.
Merge `local_landmark` / `local_landscape_feature` and thing/place landmark so they stop splitting a name's mass.

### Q7. Resolver as the engine for new gemeenten
Labels: `rules`, `scaling`. Backlog. Blocked by OSM3.
Seed with externally verified streets (Wikidata, OSM etymology), resolve the rest, queue `ambiguous` ones for review sheets. A new gemeente needs independent seeds; predictions as context add nothing.

### Q8. Resolver thresholds and label selection
Labels: `rules`. Backlog.
Tune the `ACCEPT_*` thresholds with the backtest before applying any more `--propose` output (tier 3-5: about 4.7k accepted, 1.3k would change kind, many weak, e.g. Bosrand -> forest). Improve label selection when namesakes disagree (kind-only vs a specific person; label accuracy about 74%).

### Q9. Raise tier 1: audit and verify
Labels: `wikidata`, `rules`. Backlog.
Audit accepted Wikidata person and thing matches for wrong identities; verify tier-2 streets (about 12.8k, general knowledge) against Wikidata/web search so they can move to tier 1. Needs a decision on how much of this runs as tooling versus review sheets; the unreviewed Wikidata place matches (about 1,135) go on sheets (R4).

### Q10. Wikidata fix detector: extend and keep current
Labels: `wikidata`. Backlog.
Extend `src/wikidata_fixes.py` to other generic targets and person-like names with non-person targets. Applying the list on Wikidata is the user's own work, not tracked here.

### Q11. Wikidata cache: pacing and freshness
Labels: `wikidata`, `pipeline`. Backlog.
The entity cache hit 429s: add polite pacing and User-Agent handling (fetch is resumable). The street cache is flat JSONL keyed by name: add `fetched_at`, store each item's `lastrevid`, and re-check items that changed.

### Q12. Data cleanups
Labels: `tech-debt`. Backlog.
- [ ] About 64 plant/animal streets with obscure names still carry a generic description.
- [ ] 6 Noord-Brabant streets without a buurt; 2 still "unresolved".
- [ ] Confirm the gemeente list against the official CBS/PDOK list (59 loaded, assumed complete).

---

## OSM as a refreshable evidence source (tracking issue plus items)

### OSM0. Tracking issue: OSM as a connected, refreshable evidence source
Labels: `osm`. Backlog.
Goal: OSM etymology is a first-class, versioned part of the pipeline, so we know what OSM says, when it changed and what that did to our tiers. Task list linking OSM1 to OSM8. Phase 1 (snapshots, change report, `--refresh`) is done.
Open decisions here: weekly vs monthly refresh and whether to schedule it; whether OSM may be the street list for new gemeenten or only evidence on top of the CBS/PDOK list.

### OSM1. One command after a refresh: re-apply OSM rules and report tier changes
Labels: `osm`, `rules`. Blocked by nothing.
After `osm_etymology.py --refresh`, re-apply the OSM-dependent rules (`osm_etymology`, `corrections` from_osm, `osm_places`), rebuild, and print a tier-change report (streets that gained or lost tier 1, label changes). Also verify the change report against known edits (Philipsweg Q170416, Doctor Anton Philipsweg 7210536, Frederiklaan). Keep OSM-wins-on-conflict in `rules/osm.py` covered by tests.

### OSM2. Widen what we read from OSM
Labels: `osm`, `wikidata`.
`subject:wikidata`, `name:etymology:wikipedia`, the 40 text-only `name:etymology` records as hints, and named non-`highway` features (pedestrian areas, squares as areas or relations, `place=square`).

### OSM3. Seed new gemeenten with OSM etymology; use it as the backtest set
Labels: `osm`, `rules`.
Wave procedure: acquire -> OSM etymology -> Wikidata -> reconcile -> rules (OSM first). OSM-tagged streets in each wave become the resolver's independent evaluation set.

### OSM4. Map more OSM/Wikidata items to kinds
Labels: `osm`, `wikidata`.
228 OSM items have no kind we can map (Holy Trinity, ranks, border...): extend `classify_entity` and the subcategory taxonomy; `osm_entity_kinds.json` stays the reviewed override table.

### OSM5. OSM fetches for any province or gemeente list
Labels: `osm`, `scaling`, `tech-debt`.
`osm_etymology.py` and `osm_places.py` query the `NL-NB` area only. Parametrise by province or gemeente list so `pipeline.py add` works anywhere. For all of NL consider Geofabrik extracts or replication diffs instead of area queries (about 1 in 100 streets carries etymology, so this is a seed, not full coverage).

### OSM6. Scheduled incremental OSM refresh and notification
Labels: `osm`, `pipeline`. Blocked by OSM1, OSM5.
Weekly incremental Overpass `(newer:"<last fetch>")` merged into the snapshot, plus a monthly full re-fetch to catch removals; a short summary after each refresh (new tier-1 streets, changed namesakes, new conflicts).

### OSM7. Decide: is OSM the street-list source for new gemeenten?
Labels: `osm`, `decision`.
The supplement already added named `highway=*` ways. For new gemeenten decide whether OSM replaces the drive-graph list entirely or stays evidence on top, and settle the Baarle-Hertog shared-name caveat (a name shared with Baarle-Hertog may carry Belgian segments in the merged geometry).

### OSM8. Upload tooling for OSM edits
Labels: `osm`.
Play by OSM's automated-edit rules: no unreviewed mass edits, per-batch changeset comments and `source=`, own account. Candidate designs: JOSM-ready `.osc`, a MapRoulette challenge, or Overpass-turbo-assisted selection per gemeente, small reviewed batches. Builds on `osm_suggestions.json` and `OSM_FIXES.md`. Design with the user first.

---

## Pipeline, scaling and tech debt

### S1. Acquisition for all ~340 gemeenten
Labels: `scaling`, `pipeline`. Backlog. Blocked by H1, OSM5.
Overpass limits (per-province batching), Wikidata lookup volume (hundreds of thousands of names; cache per core name), run time and resumability.

### S2. Map delivery with PMTiles
Labels: `scaling`, `map`. Backlog.
Replace per-gemeente scripts (today about 40 MB gzipped, about 1.2 MB initial load) with vector tiles.

### S3. Refactor `build_map.py`
Labels: `map`, `tech-debt`. Backlog.
A 525-line script with the HTML in strings and `DEFAULT_GEMEENTE = "Eindhoven"`. Split template from data, make the default configurable. Do together with S2 if PMTiles is next.

### S4. Re-fetch the early gemeenten from the CBS outline
Labels: `pipeline`, `tech-debt`. Backlog.
Eindhoven, Helmond and others were fetched from the OSM place polygon, the rest from the CBS outline; a re-fetch drifts (a Waalre re-fetch showed changed names). Re-fetch them with the CBS outline now that snapshots record every fetch, and review the diff.

### S5. Country-level analysis
Labels: `scaling`. Backlog.
Themes by province/region and historical layers (merged gemeenten, post-war estates). Blocked by S1.

### KPI1. (Proposed) Release KPIs computed before every major commit
Labels: `pipeline`, `proposed`. Backlog. Not yet agreed: this replaces permanently stored findings and measurements.
Instead of committing one-off numbers to docs, define a small fixed set of key measurements that one script prints (and writes into `PROVENANCE.json` or the release notes) before a release or major commit, so changes are visible over time without hand-copied figures.
Candidate KPIs:
- Tier 1 to 5 shares, overall and per `way_class` (street / path / planned).
- Share of streets with a specific namesake (tiers 1 and 2).
- OSM etymology agreement: share of OSM-tagged streets where our category matches OSM's.
- Resolver backtest accuracy (accepted precision) on the OSM-tagged evaluation set.
- Named OSM ways missing from the street list, per gemeente (coverage gap).
- Count of streets changed since the previous release, by cause (rule layer, correction, OSM refresh).
- Tests passing, and the knowledge/code/OSM snapshot versions used.
Open questions: which of these matter enough to track; whether the script runs in CI or only at release time; where history is kept (release assets are the likely answer, not git).
Done when: `python src/kpis.py` prints the agreed set and CI or the release checklist runs it.

---

## Not migrated, and why

| TODO item | Why |
|---|---|
| Eindhoven review sheet, held proposals, declined resolver proposals (~830), declined place readings (~270), spot-check 60 streets per wave, "only if systematic gap: targeted vocabulary pass", person-street first-name review, remaining Wikidata place matches (~1,135), Halifaxstraat / Vredenburg, 9 OSM conflicts | Review work: becomes sheets via R1 to R4 |
| Apply `OSM_FIXES.md` / `WIKIDATA_FIXES.md`, re-fetch after OSM edits | The user's own edits on external sites; the generated lists are the worklist |
| Wave 1-3 "do not redo by hand" analysis, resolver precision samples, OSM accuracy check, coverage-gap root cause, Baarle-Nassau check | Findings and measurements; in git history |
| Repository model checklist (config, classify files, move layers, create repo, bootstrap, .gitignore, golden fixture) | All done in M0 to M2 |
| `scripts/legacy/` (60 scripts) move to a tag | Obsolete: the directory is in neither repo; a local-only copy is all that remains |
| Eindhoven/WWII Generalenbuurt theme check | Moves onto the Eindhoven sheet (R4) |
| Hand work does not scale | A principle, recorded in D2, not a task |

## Counts

Issues drafted: H1-H6 (6), D1-D7 (7), P1-P3 (3), R1-R6 (6), Q1-Q12 (12), OSM0-OSM8 (9), S1-S5 (5), KPI1 (1): 49 including one tracking issue and one proposed issue.
