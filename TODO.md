# TODO

Working list for the street-name etymology project. Goal: classify what every street in the Netherlands is named after
(person / place / thing, with sub-kinds), show it on a map, and keep raising the share of streets we can identify.
Noord-Brabant (59 gemeenten, 38,090 streets) is done as a first pass; everything below is about quality, durability and scale.

## Documentation (needed)

Document the whole project in Markdown, so someone new (or future us) can understand, run and extend it.
There is currently no top-level README; only `src/rules/README.md` and `scripts/legacy/README.md` exist.

- [ ] **`README.md`**: what the project is, what it produces (map, CSVs, JSON), how to run it end to end, requirements.
- [ ] **Pipeline guide**: acquire (OSM/PDOK) -> Wikidata lookup -> reconcile -> rules -> analyze -> build map -> export CSV;
      commands, inputs/outputs of each step, the ordering gotchas (reconcile -> buurt themes for new gemeenten -> reconcile), runtimes,
      Overpass/Wikidata practicalities (`WIKIDATA_CONTACT`, VPN/rate limits).
- [ ] **Method & principles**: person/place/thing taxonomy and sub-kinds; evidence tiers (`src/tiers.py`); the rule that the buurt
      decides between readings of a name but never alone; why same-named streets are not assumed to share a namesake; the
      "kind-only" labels (Willem, Hendrik...).
- [ ] **Data dictionary**: every field in `streets_final.json`, `streets_classified.csv`, `buurt_themes*.json/csv`,
      `manual_overrides.json`, `data/knowledge/*`; the meaning of `source`, `confidence`, `evidence_tier`, `notes`.
- [ ] **Rules & knowledge**: expand `src/rules/README.md` (each rule, its inputs, how to review a `--check`, how to add a rule/exclusion).
- [ ] **Findings**: which gemeenten show significant theme clustering by wijk and how the test works (`analyze.py`, permutation test);
      coverage by wave; the evidence-tier breakdown (only ~8% externally verified).
- [ ] **Known limitations & audit history**: wave-depth differences (wave 3 weakest), theme-forced label noise (~25% of the
      1.1k remaining), Wikidata mismatches, the legacy scripts and why they are not re-runnable (`scripts/legacy/README.md`).
- [ ] **Map guide**: panel, lazy per-gemeente loading, gzipped data, tooltips, tiers, legend.
- [ ] **Contributing / workflow**: tests (`tests/test_tiers.py`, `tests/test_rules.py`), commit conventions, how to add a gemeente.

## Quality and durability

- [ ] **Name-level candidate table** (in progress: `src/names/`, `Context` now carries wijk). Per name (core): all candidate
      interpretations with their evidence (Wikidata, knowledge rules, observed classifications); a resolver picks one per street from
      buurt/wijk context; backtest on already-identified streets; no writes to `manual_overrides.json` until reviewed.
- [ ] **Raise tier 1**: audit accepted Wikidata *person* and *thing* matches for wrong identities; verify tier-2 streets (12.8k, general
      knowledge) against Wikidata/web search so they move to tier 1.
- [ ] **Bring waves 1-3 up to wave-4 depth** (wave 3: 53% not identified); re-run the rule families and add the theme vocabularies
      written for waves 4-6 (minerals, butterflies, trades, fort terms...).
- [ ] **Review the remaining `--check` proposals**: `bare_surname` (20), `same_name_harmonise` (16), `person_consensus` (2),
      `theme_forced_name_fit` (2), plus the leftovers below.
- [ ] **Theme-forced labels**: ~1.1k non-local labels still rest on the buurt theme plus a weak name fit (~25% sampled as wrong);
      decide: re-check against Wikidata by surname, or flag low-confidence in the CSV and tooltips.
- [ ] **Wire the rules into the build** (layers applied in a fixed order from code + data), so `manual_overrides.json` stops being the
      only record; keep the legacy snapshot as a frozen layer.

## Known small leftovers

- [ ] 42 foreign-place streets keep a generic description because the place is ambiguous (Halifax, Essen, Mackay, Thorner, Vredenburg, Mill Hill, Ravenstein, Mondsestraat...).
- [ ] Cousinsstraat (Dongen, Hoge Akker) is filed as a writer and probably is not one.
- [ ] ~64 plant/animal streets with obscure names still have a generic description; "hoen" is missing from the species dictionary.
- [ ] 6 Noord-Brabant streets without a buurt; 2 still "unresolved".
- [ ] Confirm the Noord-Brabant gemeente list against the official CBS/PDOK list (59 loaded, assumed complete).
- [ ] The remaining accepted Wikidata place matches (about 1,135) were only skimmed; check them against the street's location.

## Scaling to the Netherlands

- [ ] Acquisition for all ~340 gemeenten (Overpass limits; per-province batching); Wikidata lookup volume (hundreds of thousands of names, cache per core name).
- [ ] Map delivery: vector tiles (PMTiles) instead of per-gemeente scripts (today 40 MB gzipped, ~1.2 MB initial load).
- [ ] Hand work does not scale: lean on the candidate table, the rules and the evidence tiers; hand-classify only the residue.
- [ ] Country-level analysis: themes by province/region, historical layers (merged gemeenten, post-war estates).
