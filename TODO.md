# TODO

Working list for the street-name etymology project. Goal: classify what every street in the Netherlands is named after
(person / place / thing, with sub-kinds), show it on a map, and keep raising the share of streets we can identify.
Noord-Brabant (59 gemeenten, 38,090 streets) is done as a first pass; everything below is about quality, durability and scale.

## Project: GitHub-ready (near-term priority, set 2026-11-22)

**Goal.** A public core repo that a stranger can clone, bootstrap and test, plus a separate knowledge repo (see "Repository model" below). Ordered by dependency:
each milestone unblocks the next; items outside this list (tier-2 verification, resolver declines, review sheets, OSM upload tooling, PMTiles, OSM refresh phases 2-6)
are quality work that does not block publishing.

**M0. Finish what is in flight: DONE 2026-11-22. Carried forward, not blockers: Henriëttestraat and Hubertastraat (Philipsdorp; OSM free-text hints in `review_notes.json`: Henrietta Martina Bax, probably Anton's mother-in-law; Hubertastraat 'mother of M.E.H. Tjaden'), and the held `bare_surname` / `wikidata_place_review` reviews**
- [x] Wikidata lookup of the new names done; rebuilt with themes; rules applied to the supplement (2026-11-22): species, vocabulary, titles, directional_road, same_name_harmonise,
      person_consensus, theme_forced_name_fit, name_resolver, osm_places (tightened: a park/square named exactly like the street is not evidence), osm_etymology (2,228 overrides).
      Held back: `bare_surname` (168 proposals, sampled ~50% wrong: Ankerstraat/Koggestraat -> monarchs) and `wikidata_place_review` (68, turns Linden/Heide into "foreign towns").
      **Not committed yet.** 44,600 streets: tier 1 9.9%, tier 2 31.8%, tier 3 14.2%, tier 4 5.5%, tier 5 38.6%.
- [x] Tiers per `way_class`: street 10% tier 1 / 37% tier 5; path 12% / 54%; planned 11% / 56%. Decide whether paths/planned roads count in the headline numbers (they will appear in the README).
- [x] Elisabethlaan (Eindhoven, Philipsdorp): OSM tag Q76366670 = Maria Heyligers is right: her full name was Maria Elisabeth Heijligers (the user's correction; confirmed in Wikipedia's Frederik Philips article and a civil record). Briefly withdrawn on the wrong premise, restored as tier 1. Philipsdorp streets honour the family: Frederiklaan (Frederik), Elisabethlaan (his wife), Annastraat (Anton's wife); Henriëttestraat still open.
- [ ] Review the held `bare_surname` (168) and `wikidata_place_review` (68) proposals; improve `bare_surname` (common nouns like Anker, Kogge are not surnames).
- [x] Baarle-Nassau (46% gap) checked 2026-11-22: not an enclave artefact. The CBS outline does contain the Baarle-Hertog enclaves and 82 Belgian ways lie inside it, but every one of those names also has a Dutch way, so there are no Belgian-only streets in our list (a re-fetch with an `(area.nl)` filter returned the identical 322 names). The 46% is rural tracks and paths (148 added, mostly `track`) the drive-network fetch never had. Residual limitation: a street name shared with Baarle-Hertog (Molenstraat, Kapelstraat...) may carry its Belgian segments in the merged geometry. `osm_streets.py` now fetches only ways inside the NL area.

**M1. Foundations that everything else touches: DONE 2026-11-22 (config, override layers, snapshots)**
- [x] `src/config.py` + git-ignored `config.local.toml` (done 2026-11-22; `config.example.toml` documents it): build dir, knowledge dir, `WIKIDATA_CONTACT`, Overpass URL; lookup order env > local file > default; every script reads paths from it (outputs byte-identical before/after, a test covers precedence and the build directory). With no build dir set the layout is unchanged; the repository split (M2) only has to change defaults. Still hard-coded on purpose: `OSM_FIXES.md`/`WIKIDATA_FIXES.md` (docs in the repo root), the fixed `data/` knowledge file layout, `scripts/legacy/`. (Precursor of the build/ split and of unattended runs.)
- [x] Override layering (done 2026-11-22): `manual_overrides.json` is gone. `src/overrides.py` holds the layers: `legacy_hand` (28,419, frozen: `data/knowledge/overrides/`) plus one file per rule (`data/enriched/overrides/<rule>.json`), applied in dependency order (`PRECEDENCE`; species after vocabulary, corrections last). `reconcile.compute_final(upto=RULE)` gives the state below a rule; `rules/run.py --apply RULE` regenerates only that rule's layer from that state and prints the diff against the old layer (`--cascade` redoes the rules above); rules named in `data/knowledge/rules_status.json` are skipped in all-rule runs (`bare_surname`, `wikidata_place_review`). `streets_final.json` is byte-identical before and after the migration; `tests/test_overrides.py`.
      **Finding:** the existing rule layers are the product of *sequential, partly reviewed* applications, so regenerating them from scratch churns thousands of streets (dry run 2026-11-22: name_resolver 757 of 1,090 entries change, vocabulary +533/-96, osm_etymology 123 changed, label_cleanup and species regenerate empty because their inputs now arrive differently). Do not regenerate wholesale; treat it as a separate reviewed "layer audit" (below).
- [ ] **Layer audit**: for each rule layer, review what a clean regeneration would change (`rules/run.py --check --cascade vocabulary` prints the per-layer diff), decide per rule whether the regenerated layer is better, and commit them one at a time. Until then layers are historical records; new streets get their rules applied with `--apply RULE` as before.
- [x] OSM snapshot versioning (done 2026-11-22; covers OSM project Phase 1 except the scheduler): `src/snapshots.py` records every fetch (fetched_at, sha256, bytes, rows, query hash) in `raw/snapshots.json` and archives a gzipped copy (etymology ways, places; per-gemeente street files are recorded, not archived); `--status`, `--verify`, `--backfill` (existing files were recorded as baseline, marked 'backfilled'). `osm_etymology.py --refresh` = fetch + `src/osm_changes.py` (per-way diff of the etymology-related tags against the previous archive, written to `output/OSM_CHANGES.md` and appended to `enriched/osm_changes.jsonl`) + build. Contributor names are dropped; way version/timestamp are kept (`out meta`). `acquire.py` records a snapshot per gemeente. First refresh (2026-11-22) showed 0 changes since 2026-11-21 (20,653 ways); change detection is covered by `tests/test_snapshots.py`. Left for later: stamp the snapshot dates into the outputs (M2), apply the OSM rules automatically after a refresh (OSM Phase 2), scheduling (Phase 5).

**M2. Split the repos: DONE 2026-11-22** (needs M1)
- [x] Classification and sharding (done 2026-11-22): global curated lists moved to `data/knowledge/global/` (+ `provinces.json`, filled by `acquire.py` from the CBS/PDOK province outlines); per-gemeente knowledge sharded to `data/knowledge/gemeenten/<province>/<gemeente>/` (`corrections.json`, `review_notes.json`, `REVIEW.md`, `overrides/<layer>.json`; `src/knowledge.py`, `tests/test_knowledge.py`); the rule layers moved out of `data/enriched/` into the shards; generated fix reports now go to `output/reports/`; `data/raw`, `data/enriched`, `output`, `scripts/legacy` are git-ignored/untracked. `streets_final.json` byte-identical before and after; all 8 test files pass.
- [x] M2 build/bootstrap/CI (done 2026-11-22): default layout is `build/` (raw, enriched, output, cache, names; git-ignored) and `knowledge/` (the knowledge repository checked out; was `data/knowledge`); `pipeline.py bootstrap [--no-clone]` creates the build dir, clones the knowledge repo from `knowledge_repo` and checks the provinces; `src/provenance.py` writes `output/PROVENANCE.json` (code + knowledge commit, dirty flag, OSM snapshot dates) and the map footer shows it with the data attributions; snapshot manifest paths are now relative to `raw/` (portable); `osmnx` dropped from requirements; golden fixture `tests/fixture` (84 streets, 3 gemeenten, synthetic geometry, canned Wikidata cache, matching layers) + `tests/test_e2e.py` (reconcile reproduces `expected_final.json`, analyze/export_csv/build_map run); tests that need the curated lists import `tests/_need_knowledge.py` and stop with a clear message without the knowledge checkout; `.github/workflows/tests.yml` (checks out the knowledge repo too: needs the `KNOWLEDGE_READ_TOKEN` secret while it is private; verified in a clean copy with a fresh venv); `LICENSE` (MIT), `NOTICE.md`, `knowledge/{LICENSE (CC-BY 4.0),ATTRIBUTION.md,README.md}`.
- [x] History rewrites and first pushes (done, validated 2026-11-22): core history holds only `src/`, `tests/`, `.github/` and root docs (no data, outputs or legacy scripts; the only `/Users/marius` hit left is the text of this TODO); knowledge history holds only `global/` and `gemeenten/` plus licence/README; both repos pushed to `straatwijsheid/straatwijsheid` (MIT) and `straatwijsheid/knowledge` (CC-BY 4.0), both private. `KNOWLEDGE_READ_TOKEN` is set on core; CI (`tests`) is green on HEAD 36d9be1.
- Noted (not done): the layer audit still applies. Re-applying `species` or `person_consensus` alone changes their layers (species 9 -> 0 entries, person_consensus 3 -> 4), a pre-existing drift because they depend on other layers; restored, not regenerated.
- [x] Golden fixture + end-to-end test + GitHub Actions (done and validated 2026-11-22): `tests/fixture` (84 streets, 3 gemeenten) with `tests/test_e2e.py`; the workflow runs all 9 `tests/test_*.py` on a fresh Python 3.14 venv with `pip install -r requirements.txt`; all 9 also pass locally.

**M3. Public hygiene** (can run in parallel with M2)
- [x] Remove `/Users/marius/...` paths (done: `scripts/legacy/` is in neither repo; `git grep` finds none in core or knowledge).
- [x] Dropped the unused `osmnx` requirement; clean `pip install -r requirements.txt` is exercised by CI on every push.
- [x] **Decisions (2026-11-22)**: project name **Straatwijsheid** (straatwijsheid.nl); one NL-wide knowledge repo sharded by province/gemeente (not per region); code, docs and map in English, review sheets Dutch-primary with bilingual table headers `Nederlands (English)`; private first, public after the M3 hygiene pass; history: core repo gets a `filter-repo` allowlist rewrite (code, tests, docs only; no data, outputs or legacy scripts) and the knowledge repo gets the filtered `data/knowledge` history; fall back to a fresh start if the rewrite is not clean. Since decided: code licence MIT, knowledge licence CC-BY 4.0, GitHub org `straatwijsheid` with repos `straatwijsheid` and `knowledge`.
- [ ] **Later (user)**: set up email on straatwijsheid.nl (e.g. a contact/maintainer address) and replace the personal address used for the GitHub org/account sign-up, org billing/contact email, and any contact line in the README/CONTRIBUTING; keep the Wikidata contact in `config.local.toml` (never committed). The org `straatwijsheid` exists.
- [x] **M2 classification decisions (2026-11-22)**: knowledge repo sharded `gemeenten/<province>/<gemeente>/` (province first: every gemeente lies in exactly one province, and it gives `CODEOWNERS` regional maintainers and avoids same-name collisions such as Bergen NH vs Bergen L); global curated lists in `global/`; generated fix reports (`OSM_FIXES.md`, `WIKIDATA_FIXES.md`, `OSM_CHANGES.md`) live in the build output, not in git; `scripts/legacy/` is not carried into either repo. Province per gemeente comes from the CBS/PDOK gemeente dataset (to fetch; stored in `global/gemeenten.json`).
- [ ] **NL scaling: identify gemeenten by CBS code (GM####), not by name.** Override keys, snapshots and the street list are keyed `(gemeente name, street)`, which collides for same-named gemeenten (Bergen NH / Bergen L; check others when more provinces are added). Keep the name for display, add the code as the key, migrate the layers.
- [ ] `all_streets_wikidata.jsonl` (8 MB, hours to rebuild): stays in the build dir; publish as a release asset under CC0 (it holds only Wikidata QIDs, labels, descriptions = CC0, plus our own derived category/confidence fields); NOTICE states 'Contains data from Wikidata (CC0 1.0)'. No Wikipedia text in it (that would be CC-BY-SA); keep it that way.
- [ ] **Later: automate review-sheet regeneration with GitHub Actions.** Open question: the sheets are generated from `streets_final.json`, which needs the build pipeline (OSM, Wikidata, hours of lookups), so the trigger partly lives outside GitHub. Options: a scheduled or self-hosted runner that runs `pipeline.py rebuild` and opens a PR against the knowledge repo with the regenerated sheets; or an Action in the knowledge repo that, on a merged PR, only re-renders the sheet from a published `streets_final` release asset (no network). Needs the merge-aware sheet generator first (see the review-sheets-as-PRs plan).
- [ ] Map language toggle (Dutch/English) and a minimal localisation scaffold (Dutch-relevant languages + English only; not full i18n). Later.
- [ ] Site copy: tagline 'Where the streets have a name' and tier-5 label 'Where the streets have no (known) name' with a call to contribute via review-sheet PRs.
- [ ] Data-source terms in a `NOTICE`/README section: OpenStreetMap contributors (ODbL), CBS/PDOK (CC-BY 4.0), Wikidata (CC0); how derived outputs may be reused. Secret scan (none expected: `WIKIDATA_CONTACT` is never stored).
- [ ] Contributing guide: how to add a gemeente, a rule, an exclusion, a correction; how local knowledge reaches the knowledge repo.

**M4. Documentation** (after M2: paths and layout are final; fold in the Documentation section below)
- [ ] README, pipeline guide, method & principles, data dictionary, known limitations, map guide, findings (the Documentation items below).

**M5. First public release**
- [ ] Publish the map (GitHub Pages) and a dated raw snapshot + Wikidata cache as release assets; tag v0.1.

## Documentation (needed)

Document the whole project in Markdown, so someone new (or future us) can understand, run and extend it.
A top-level `README.md` exists (what it is, outputs, tiers, run instructions); `src/rules/README.md` and `src/names/README.md` cover those parts. The items below are what is still missing.

- [x] **`README.md`** (exists; revisit after M3): what the project is, what it produces (map, CSVs, JSON), how to run it end to end, requirements.
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
      coverage by wave; the evidence-tier breakdown (only ~9% externally verified).
- [ ] **Known limitations & audit history**: wave-depth differences (wave 3 weakest), theme-forced label noise (~25% of the
      1.1k remaining), Wikidata mismatches, the legacy scripts and why they are not re-runnable (`scripts/legacy/README.md`).
- [ ] **Map guide**: panel, lazy per-gemeente loading, gzipped data, tooltips, tiers, legend.
- [ ] **Contributing / workflow**: tests (`tests/test_tiers.py`, `tests/test_rules.py`), commit conventions, how to add a gemeente.

## Quality and durability

- [x] **Name-level candidate table, v1** (`src/names/`, committed): per-name candidates with evidence, a resolver using buurt/wijk,
      backtests (LOO and new-gemeente), `--propose` dry run. Findings: the buurt improves *calibration* (accepted precision 77% -> 87% on
      ambiguous names), not the top choice; without Wikidata evidence tier-1 streets are only 48% recoverable.
- [ ] **Candidate table follow-ups**
      - [ ] Merge near-synonym subcategories (local_landmark vs local_landscape_feature, thing/place landmark) so they stop splitting a name's mass.
      - [ ] Use the resolver as the engine for new gemeenten: seed with externally verified streets (Wikidata, OSM etymology), resolve the
            rest, queue the `ambiguous` ones for review. A new gemeente needs independent seeds; predictions as context add nothing.
      - [ ] Review the resolver's `--propose` output (tier 3-5: ~4.7k accepted, 1.3k would change kind; many weak, e.g. Bosrand -> forest)
            before applying anything; tune `ACCEPT_*` thresholds with the backtest.
      - [ ] Label accuracy is ~74%: improve label selection when namesakes disagree (kind-only vs a specific person).
- [x] **OpenStreetMap etymology evidence, v1** (applied, uncommitted until you say so): `src/osm_etymology.py`, `src/osm_report.py`,
      rule `osm_etymology`, source `osm_etymology` = tier 1, evidence in the candidate table. 20,648 ways fetched in Noord-Brabant;
      1,731 streets carry usable etymology (1,264 `name:etymology:wikidata`, 427 via the street's own item's "named after", 40 text only).
      644 applied (173 new namesakes for streets at tier 3-5, 471 tier-2 -> tier-1 upgrades). Tier 1 is now 9.3% (was 7.7%).
      Independent accuracy check: our tier-1/2 *category* agrees with OSM for 99% of 1,148 comparable streets (bias: tagged streets are well known).
- [ ] **OSM follow-ups**
      - [ ] Review the 9 conflicts (`python src/osm_report.py`): Oranje-Nassau/Mecklenburg (house as person vs place), Amazons/Argonauts/Muses
            (mythological thing vs person: taxonomy), Borneo, Romeinsestraat (OSM looks wrong), Jupiterweg (OSM says juniper: wrong),
            Sint Eustatiusstraat (OSM: the island; our label "Saint Eustatiusstraat" is a bug).
      - [ ] **Wikidata fix list** (`WIKIDATA_FIXES.md`, generated by `src/wikidata_fixes.py`): 17 street items whose *named after* points at the "notable oak tree" / "individual beech tree" items (Dutch labels eik / beukenboom), plus Willem Mariastraat ('s-Hertogenbosch, P138 = the citadel). Apply on Wikidata; extend the detector (other generic targets, person-like names with non-person targets).
      - [ ] **OSM fix list** (`OSM_FIXES.md`, generated by `src/osm_fixes.py`): 160 ways in 20 gemeenten whose `wikidata` tag points at a different
            street's item (e.g. Jupiterweg in Oss tagged with Jeneverbes), plus Romeinsestraat (Budel): one way still has Q47162 (Romain Rolland) where the other now has Q220 (Rome; the street is named after Rome, confirmed by the user's local knowledge, our earlier 'Romans' reading was wrong).
            The user applies these in OSM with their own account; after edits, re-fetch (`osm_etymology.py --fetch --build`), re-run the
            report, and drop fixed entries. Standing rule: report every OSM failure found with street, gemeente, way ids, what is wrong and what is correct.
      - [ ] 228 OSM items have no kind we can map (e.g. Holy Trinity, ranks, border): extend `classify_entity` and the subcategory taxonomy.
      - [ ] 40 text-only `name:etymology` records and `name:etymology:wikipedia`: parse for namesakes.
      - [ ] Wikidata entity cache (`cache/wikidata_entities.json`) hit 429 rate limits; fetch is resumable, add polite pacing/User-Agent handling.
      - [ ] Use OSM-tagged streets as an evaluation set in the candidate-table backtest (independent of our own labels).
      - [ ] Whole-Netherlands fetch: the same query per province; ~1 in 100 streets carries etymology, so it is a seed, not full coverage.
- [ ] **Raise tier 1**: audit accepted Wikidata *person* and *thing* matches for wrong identities; verify tier-2 streets (12.8k, general
      knowledge) against Wikidata/web search so they move to tier 1.
- [ ] **Waves 1-3: do NOT redo by hand (revised after measuring)**. Wave 3 is the weakest (53% not identified, 2% tier 1), but its tier-5
      streets are overwhelmingly generic field/farm/hamlet names (a 90-street sample: ~7% identifiable), and the share of tier-3-5
      streets the resolver would now name or re-kind is ~10% in *every* wave (wave 3: 227 of 1.3k; wave 6: 341 of 2.0k). Same-name
      propagation, rules and OSM already carried most of the wave 4-6 vocabulary back. Plan instead:
      - [x] Resolver proposals reviewed and applied (`src/names/propose.py`, rule `name_resolver`): raw 2,725 accepted changes -> 1,183 after
            dropping reviewed streets, vague kinds, synonym shuffles and downgrades -> 355 after the evidence rules (no Wikidata-only
            places, no buurt-name "towns", persons as kind only unless OSM/famous-people/vocabulary backs a name) at score >= 0.45, margin >= 0.20;
            353 applied (2 excluded). A 100-street sample of the 1,183 was ~85% right; the 70-street sample of the final 355 ~90%.
      - [ ] **Declined resolver proposals (~830 streets)**, mostly place readings of ordinary words resting on Wikidata alone ('village',
            'mountain', 'human settlement' for Zwartven, Windberg, Burenstraat...) and buurt/wijk names matched as 'towns'. Revisit with independent
            evidence (OSM `place=*` nodes/areas by name and location; coordinates from Wikidata) rather than lowering thresholds.
      - [x] **Independent-evidence pass done (2026-11-21)**: `src/osm_places.py --fetch` (12.7k named OSM places/water/parks/reserves in Noord-Brabant)
            + rule `osm_places`: a street named like a hamlet/neighbourhood/stream/lake/park within 1 km is `place / local name` (rivers and lakes
            get their kind), tier 2. 750 streets applied (660 were tier 5, 90 had a wrong person/thing kind); tier 5 fell 14.5k -> 13.8k (36.3%),
            tier 2 now 35.0%. Of the 375 declined place readings only ~100 had a nearby feature at all, and those mostly confirmed "named after its
            own hamlet", not "town"/"village": so the declined town/village guesses stay declined.
      - [x] **Policy decided (user)**: streets named after their own neighbourhood/hamlet are `place / local name` (no separate subcategory).
      - [ ] Remaining declined place readings (~270 with no nearby OSM feature): Wikidata-only settlements; leave as they are unless the local review sheet says otherwise.
      - [x] Eindhoven review round 1 (user answered 12): applied 10 (Anthing, Boreel, Kolfschoten, Smits van Oyen, Ouborg, Annastraat as tier 2 with sources; Glaslaan, Luchthavenweg, Kaneelstraat, Tilburgseweg-West as kinds); Bentinck and Boosten kept open with notes. New checks added: Philipsdorp Frederiklaan/Henriëttestraat (Wikidata matches look wrong) and Hubertastraat. Notes live in `data/knowledge/review_notes.json`.
      - [ ] **Local-knowledge review**: `REVIEW_EINDHOVEN.md` (`python src/review_sheet.py <gemeente>...`): 168 Eindhoven person streets with no namesake, by buurt.
            Answers go into `corrections.json` / buurt themes. Extend to Helmond, Veldhoven, Geldrop-Mierlo, Nuenen, Son en Breugel on request.
            Check: the Generalenbuurt theme is labelled "Allied/Dutch WWII generals"; the streets look like 18th-19th c. Dutch generals instead.
      - [ ] **OSM upload tooling (user, later)**: how to play by OSM's rules (no mass edits without the import/automated-edit procedure; per-edit
            changeset comments, sources, own account) while avoiding one-at-a-time edits: e.g. a JOSM-ready `.osc`/MapRoulette challenge or
            Overpass-turbo-assisted bulk-select per gemeente, small reviewed batches, `source=` + changeset discussion. Design with the user.
      - [ ] **Street-list coverage gap (root cause found 2026-11-21)**: `acquire.py` builds the street list from an osmnx `network_type="drive"` graph with
            `retain_all=False`, which drops (a) service roads such as `service=parking_aisle`/`driveway`, (b) pedestrian/footway/cycleway/track ways,
            (c) disconnected components (short isolated streets) and (d) anything clipped by the outline. Found via Elisabethlaan in Philipsdorp (OSM way
            715072023, a parking aisle tagged `name:etymology:wikidata=Q76366670`, Maria Heyligers): 534 distinct names on ways that OSM taggers marked with
            `wikidata`/`name:etymology:*` are absent from our list (vs 1,733 matched), and Cranendonck lacks 12% of its named OSM highways.
            Fix: replace the drive graph by an Overpass query for every named `highway=*` way in the outline (with `highway`/`service` kept as a column
            so tiers/maps can filter), re-run acquire for all gemeenten, look up the new names, and run them through the pipeline as one more wave
            (`pipeline.py add` handles it). Measure the gap per gemeente first (named OSM ways vs our list).
            **Status 2026-11-21**: gap measured (6,808 of 44,887 named street names, 15.2%, missing; worst Baarle-Nassau 46%, Nuenen 28%, Loon op Zand 27%);
            new fetch `src/osm_streets.py` (every named `highway=*` way except proposed/platform/bus_stop/services...; `highway`, `way_class` street|path|planned);
            `acquire.py --supplement` added 6,510 streets to the 59 gemeenten (existing rows untouched, `origin: supplement`; 3,115 paths, 281 planned);
            map has Paths / Roads-under-construction toggles; CSV and streets_final carry `highway` and `way_class`.
      - [ ] **Next for the supplement**: look up the 4,632 new street names on Wikidata (`WIKIDATA_CONTACT=... src/enrich_wikidata.py --missing`, ~45 min, user's shell),
            then `pipeline.py rebuild --themes`, `rules/run.py --check` (osm_etymology will now match the 526 tagged streets that were missing, e.g. Elisabethlaan),
            and review tiers per way_class (paths/planned should maybe be reported separately).
      - [ ] Baarle-Nassau (46% gap): check the Belgian enclaves (Baarle-Hertog) are not double counted.
      - [ ] OSM additions: `data/knowledge/osm_suggestions.json` + OSM_FIXES.md section C. Philipsweg (Cranendonck): 15 ways to tag; Doctor Anton
            Philipsweg: 4 of 16 ways tagged so far, 12 to go; Doctor Anton Philipsweg, Tilburg (7210536) now tagged; 6 ways at Maarheeze still to tag. Re-fetch 2026-11-21 moved both streets to tier 1 (`data/knowledge/osm_entity_kinds.json` fixes the kind for Q592767 / Q170416). Re-fetch again (`osm_etymology.py --fetch --build`, then rules --apply osm_etymology, rebuild) after more edits.
      - [ ] Person streets (about 400 of the declined) get a kind but no name unless backed; a name-level review of shared first names (Hendrik, Willem, Maurits...) could add namesakes via the buurt.
      - [ ] Spot-check 60 streets per wave 1-3 against Wikidata/web search to confirm the residue really is unidentifiable.
      - [ ] Only if that finds a systematic gap in a buurt theme: a targeted vocabulary pass for that theme, not a full redo.
      - [ ] Note: OSM etymology tags are concentrated in the early gemeenten (1,305 of 1,731 streets), so OSM cannot yet audit waves 3-6
            (14-85 tagged streets each).
- [ ] **Review the remaining `--check` proposals**: `bare_surname` (20), `same_name_harmonise` (16), `person_consensus` (2),
      `theme_forced_name_fit` (2), plus the leftovers below.
- [ ] **Theme-forced labels**: ~1.1k non-local labels still rest on the buurt theme plus a weak name fit (~25% sampled as wrong);
      decide: re-check against Wikidata by surname, or flag low-confidence in the CSV and tooltips.
- [ ] **Wire the rules into the build** (layers applied in a fixed order from code + data), so `manual_overrides.json` stops being the
      only record; keep the legacy snapshot as a frozen layer.

## Known small leftovers

- [x] 40 of the 42 foreign-place streets with a generic description resolved from their buurt (`corrections.json`); 2 remain: Halifaxstraat (Altena: England, Nova Scotia or the bomber?), Vredenburg (Bergen op Zoom, a composers' buurt: TivoliVredenburg?).
- [x] Saint labels that repeated the road word (150 streets), Cousinsstraat, Abdijlaan label, "hoen" species: fixed.
- [ ] ~64 plant/animal streets with obscure names still have a generic description.
- [ ] 6 Noord-Brabant streets without a buurt; 2 still "unresolved".
- [ ] Confirm the Noord-Brabant gemeente list against the official CBS/PDOK list (59 loaded, assumed complete).
- [ ] The remaining accepted Wikidata place matches (about 1,135) were only skimmed; check them against the street's location.

## Scaling to the Netherlands

- [ ] Acquisition for all ~340 gemeenten (Overpass limits; per-province batching); Wikidata lookup volume (hundreds of thousands of names, cache per core name).
- [ ] Map delivery: vector tiles (PMTiles) instead of per-gemeente scripts (today 40 MB gzipped, ~1.2 MB initial load).
- [ ] Hand work does not scale: lean on the candidate table, the rules and the evidence tiers; hand-classify only the residue.
- [ ] Country-level analysis: themes by province/region, historical layers (merged gemeenten, post-war estates).

## Tech debt: generalise the pipeline (2026-11-21)

**Done** (outputs verified byte-identical: `streets_final.json` unchanged before/after):
- [x] One orchestrator, `src/pipeline.py add <gemeenten> | rebuild | status`, replacing the hand-run wave wrappers (`acq.sh`, `run4.sh`, `run6.sh`).
- [x] `enrich_wikidata.py --missing` finds uncached names itself; the 13 per-wave `*_new_streets.txt` lists, `all_streets.txt`, `pilot_sample.txt` are gone.
- [x] `src/themes.py` (any gemeente, labels in `data/knowledge/theme_labels.json`) replaces the legacy `themes_new.py` with its hard-coded gemeente list; it also filled 3 buurten the legacy run had missed.
- [x] `acquire.py`: no module globals or hand-grown per-wave lists; any number of gemeenten per call, skips fetched ones, retries; exceptions in `data/knowledge/gemeenten.json`; default is the CBS buurten outline.
- [x] Pilot (Eindhoven-only) pipeline removed: `reconcile.py` has a single mode; pilot data, logs, `speed_test` deleted; no `"Eindhoven"` defaults left in src.
- [x] The 29,115 hand-written legacy overrides in `manual_overrides.json` are tagged `rule: legacy_hand` so rule-generated and frozen entries are distinguishable.
- [x] `tests/test_pipeline.py`; README run instructions and layout updated.

**Remaining debt**
- [x] `manual_overrides.json` split into layers (see M1).
- [ ] Buurt themes: 394 hand-written (`claude_reasoning`) + 1,670 derived from street classifications that were themselves shaped by those themes (circular). Decide whether derived themes should be recomputed after rules change (`themes.py --rebuild`) and whether the reconcile feedback loop needs damping.
- [ ] Early gemeenten (Eindhoven, Helmond, ...) were fetched from the OSM place polygon, the rest from the CBS outline; a re-fetch uses the CBS outline for all and OSM drifts (a Waalre re-fetch showed a few changed street names). Version the raw snapshots (date + checksum) so a refresh shows what changed (see the OSM project).
- [ ] `osm_etymology.py` and `osm_places.py` query the `NL-NB` area only: parametrise by province or gemeente list so `pipeline.py add` works anywhere in NL.
- [ ] `build_map.py` is a 525-line script with the HTML in strings and `DEFAULT_GEMEENTE = "Eindhoven"`; split template/data, make the default configurable (and see Scaling: PMTiles).
- [x] (done in M2: `tests/test_e2e.py`, run in CI) An end-to-end smoke test on a tiny fixture gemeente (acquire is network-bound: fixture geojson + a canned Wikidata cache), run in CI-style on every change.
- [ ] The Wikidata cache is a flat JSONL keyed by street name: add `fetched_at` and re-check policy (also in the OSM project, Phase 5).
- [ ] `scripts/legacy/` (60 scripts) stays as provenance; consider moving it to a git tag/branch once nothing references it.

## Repository model: code repo + build directory + knowledge repo (agreed 2026-11-22)

Three places, three lifecycles:
1. **Core repo (git)**: the Python code and what is needed to run and test it: pipeline, rules, tests, docs, a small golden test fixture, and the *generic
   rule reference data that changes in lockstep with the rules* (species list, saint/title patterns, vocabulary patterns: `data/knowledge/vocabulary.json`,
   `species*.txt`, `common_*.txt`, `directional_places.json`, `theme_labels.json`, `gemeenten.json`).
2. **Build directory (not under git, path configurable, may live outside the repo)**: everything rebuildable from sources: raw OSM/PDOK downloads, Wikidata cache,
   OSM etymology/places snapshots, `streets_final.json`, adjacency/candidate tables, derived buurt themes, rule-generated override layers, `output/` (map, CSV).
   Published as release assets (map, dated raw snapshot) when needed.
3. **Knowledge repo (separate git repo, "street-knowledge")**: human judgement that cannot be regenerated: the 29k `legacy_hand` overrides, hand-written buurt
   themes (`claude_reasoning`), `corrections.json`, `rule_exclusions.json`, `famous_people.txt`, `person_labels.json`, place-match corrections,
   `osm_suggestions.json`, `osm_entity_kinds.json`, `review_notes.json`, the per-gemeente review sheets (`reviews/<gemeente>.md`, see below), future `user_notes`. Own history, own licence,
   open to contributions from other people with local knowledge.

Design points / risks to settle (challenges to the model, not objections):
- **Code and knowledge versions must match.** The core repo reads the knowledge repo through one configured path (`KNOWLEDGE_DIR`, default a sibling checkout
  `../street-knowledge`), checks a `schema_version` file at start-up, and stamps the knowledge commit hash into every output (`streets_final.json`
  metadata, CSV header, map footer) so any published number can be tied to exact code + knowledge + OSM snapshot.
- **Rule reference data vs judgements.** Splitting `data/knowledge/` is the real work: vocabulary/species lists *define* rules (core repo), corrections/exclusions/overrides
  are *judgements about streets* (knowledge repo). Where a file is both (famous_people, place-match corrections) it goes to the knowledge repo.
- **Tests must not need the knowledge repo.** Rule tests use the golden fixture in core; an optional integration check runs against the real knowledge repo.
- **History**: create the knowledge repo with `git filter-repo --path ...` so the files keep their history; then remove them from core (core history stays large:
  125 MB; rewrite only before going public).
- **Licensing**: OSM/Wikidata-derived data has its own terms (ODbL, CC0): note them in the knowledge repo README; the knowledge repo can be CC-BY or CC0 while the code is MIT.

- [ ] One `config.py` (replaces the idea of `paths.py`): BUILD_DIR, KNOWLEDGE_DIR, `WIKIDATA_CONTACT`, Overpass URL. Lookup order: environment variable > git-ignored
      `config.local.toml` in the core repo > default; a committed `config.example.toml` documents the keys. The contact address lives only in the local file (never in
      the knowledge repo, which is meant to be shared, and never in a tracked file); `pipeline.py` and `enrich_wikidata.py` read it so no manual `export` is needed.
      Replace the ~15 hard-coded `ROOT/data/...` and `output` paths.
- [ ] Classify every file in `data/knowledge/` and `data/enriched/` into core / knowledge / build (table in this file).
- [ ] Move the layers: `legacy_hand.json` + hand themes -> knowledge repo (already in `data/knowledge/overrides/`); rule layers -> build (`data/enriched/overrides/`, regenerable with `rules/run.py --apply`).
- [ ] Create the knowledge repo (filter-repo keeps history), add README, licence, schema_version; wire `pipeline.py` to it; stamp commit hashes into outputs.
- [ ] `pipeline.py bootstrap`: from a clean clone + knowledge repo, rebuild `build/` (acquire, Wikidata, OSM, rules, outputs).
- [ ] Add `build/` to `.gitignore`, `git rm --cached` rebuildable data; publish map and dated OSM snapshot as release assets; keep the Wikidata cache as a versioned snapshot (not reproducible: Wikidata changes).
- [ ] **Review sheets as pull requests (user, 2026-11-22)**: the `<gemeente>` review sheets (today `REVIEW_EINDHOVEN.md`, generated by `src/review_sheet.py`) move to the knowledge repo as `reviews/<gemeente>.md`, so people with local knowledge propose corrections as PRs against that repo. Needs: (1) the sheet generator writes into the knowledge repo and **merges** instead of overwriting, since answers live in the markdown table's "Your answer" column and a regeneration must keep them (store answers in a machine-readable file, e.g. `reviews/answers/<gemeente>.json`, and render them into the sheet); (2) an **ingest** command that parses merged answers, validates them (street exists, source given, confidence stated) and turns accepted ones into `corrections.json` entries with the contributor's source as `source_url`/`reason`; (3) a PR template + CONTRIBUTING section (what counts as a source: a link, a document, 'local knowledge' flagged as tier 2 at most; no unsourced person names asserted as tier 1); (4) GitHub Actions on the knowledge repo that runs the ingest validation on every PR; (5) decide whether answers are free text (friendly to the GitHub UI) or a small structured form (safer to parse).
- [ ] Golden fixture (a few gemeenten, canned Wikidata cache) and an end-to-end test.

## Project: OSM as a connected, refreshable evidence source (raised 2026-11-21)

**Goal.** OSM etymology tags are the strongest evidence we have (human-curated, per street). Today they are a manual one-shot snapshot bolted on after waves 1-6.
Make them a first-class, versioned part of the pipeline, so we always know what OSM says, when it changed, and what that did to our tiers, and so the same
machinery serves the NL-wide scale-up and the user's edits flowing back to OSM. **Do these as one connected effort, in this order; each phase builds on the previous.**
Related open items elsewhere: OSM follow-ups and OSM fix list (Quality section), OSM upload tooling, Coverage check, Scaling to the Netherlands, Pipeline guide.

**Why now (findings)**
- Etymology was added after the waves, so it was applied retroactively with one Noord-Brabant query; `acquire.py` and the Wikidata enrichment never touch it.
- Only 1,733 of 38,090 streets (4.5%) carry any etymology tag, concentrated in early gemeenten; waves 3-6 have 14-85 tagged streets each.
- The rule ignored OSM on tier-1 streets until today; 27 wrong tier-1 Wikidata matches (Hugo de Groot, Mendelssohnlaan, Paul Kruger...) surfaced only through an accident (Frederiklaan).
- No record of *when* a tag appeared or changed (the user's Philipsweg / Anton Philipsweg edits were discovered by manual re-fetch).

**Phase 1: snapshot with history (foundation; everything else depends on it)**
- [x] Snapshot with `fetched_at`, checksum, way versions (see M1).
- [x] Diff against the previous snapshot -> `OSM_CHANGES.md` + `osm_changes.jsonl` (see M1).
- [x] `osm_etymology.py --refresh` = fetch + diff + build.
- [ ] Verify against known edits: Philipsweg (Q170416, 4 of 16 ways), Doctor Anton Philipsweg (7210536, 268417255), Frederiklaan should all show up as changes.

**Phase 2: connect it to the rules and the build**
- [ ] After a refresh, one command re-applies the OSM-dependent rules (`osm_etymology`, `corrections` from_osm, `osm_places`), rebuilds (reconcile --full, analyze, map, CSV) and prints a tier-change report (streets that gained/lost tier 1, label changes).
- [ ] Make overrides from rule-generated sources idempotent/regenerable: re-running a rule must not leave stale entries (today removing `rule: osm_etymology` entries and re-applying is a manual trick; see the 2026-11-21 near-loss of ~680 overrides).
- [ ] Keep OSM-wins-on-conflict logic (rules/osm.py) covered by tests; extend to relation/area cases once Phase 3 lands.

**Phase 3: widen what we read**
- [ ] Also read `subject:wikidata`, `name:etymology:wikipedia` fully, `name:etymology` free text (40 text-only streets: surface as hints), and named non-`highway` features (pedestrian areas, squares as areas/relations, `place=square`).
- [ ] Map more OSM/Wikidata items to kinds (228 unmapped items: Holy Trinity, ranks, border...); keep `data/knowledge/osm_entity_kinds.json` as the reviewed override table.
- [ ] Coverage check (Cranendonck 59 of 477 named OSM highways not in our street list): decide whether OSM is the street list source or only evidence.

**Phase 4: make it part of every wave and of the NL scale-up**
- [ ] Wave procedure: acquire -> OSM etymology fetch/refresh -> Wikidata lookup -> reconcile -> rules (OSM first) -> report. New gemeenten are seeded with OSM-tagged streets before the resolver runs, and OSM-tagged streets in each wave become its evaluation set.
- [ ] Per-province/gemeente fetch (Overpass is fine for Noord-Brabant; for all of NL use Geofabrik extracts or replication diffs instead of area queries).

**Phase 5: keep it current**
- [ ] Scheduled refresh (e.g. weekly): incremental Overpass `(newer:"<last fetch>")` on the tag-filtered query merged into the snapshot, plus a monthly full re-fetch to catch removals; Phase 1 diff then reports what changed.
- [ ] Wikidata side: store each cached item's `lastrevid`; re-check items that changed (label, "named after", instance of), since OSM tags only point at items and the cache never expires today.
- [ ] Notify: a short summary after each refresh (new tier-1 streets, changed namesakes, ways that now conflict with our readings).

**Phase 6: the return flow to OSM (user's edits)**
- [ ] Phase 1's changelog confirms which suggested edits landed (`OSM_FIXES.md` sections A-C shrink automatically).
- [ ] Upload tooling per OSM's automated-edit rules (see the OSM upload tooling item): JOSM/MapRoulette task export of confident additions and fixes, small reviewed batches per gemeente, per-batch changeset comments; builds on the suggestion lists (`osm_suggestions.json`, `OSM_FIXES.md`).

**Open decisions (user)**
- Weekly vs monthly refresh cadence, and whether to automate it (scheduled task) or run by hand.
- Whether OSM may be our street list for new gemeenten, or only evidence on top of the CBS/PDOK-based list.
