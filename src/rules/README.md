# Rules and knowledge reference

Rules are versioned, tested families of classification logic. Each is a pure function of the data: it takes a `Context` (the streets, the current classification, the Wikidata cache, place names, the buurt of
every street) and returns `Override` records. Each rule owns one **override layer**, a file per gemeente at
`knowledge/gemeenten/<province>/<gemeente>/overrides/<rule>.json`. Only `run.py` writes layers (see `src/overrides.py`). For the reasoning behind the rules see [docs/method.md](../../docs/method.md); for where
rules fit in a run, [docs/pipeline.md](../../docs/pipeline.md).

```
python src/rules/run.py --list                       # the rules, and which are disabled
python src/rules/run.py --check [RULE ...]           # dry run: what each rule proposes, and how that compares with the data now
python src/rules/run.py --apply RULE [...]           # regenerate those rules' layers (prints how each layer changed); --cascade also redoes the enabled rules above it
python src/rules/run.py --apply RULE --force         # also replace tier-1 (verified) streets
.venv/bin/python tests/test_rules.py                 # unit tests;   tests/test_tiers.py for the evidence tiers
```

After `--apply`, run reconcile, analyze, build_map and export_csv (`pipeline.py rebuild` does all of them).

## Layers and their order

A street's final classification is built up in layers. `reconcile.py` computes the base (Wikidata plus buurt theme), then the layers are applied in the order of `PRECEDENCE` in `src/overrides.py`; **a later layer wins on the same street**.

1. `legacy_hand`: the first-wave hand and LLM classifications (about 29k). Frozen and irreplaceable; no rule regenerates it.
2. the rule layers, in this order: `vocabulary`, `titles`, `directional_road`, `species`, `label_cleanup`, `bare_surname`, `same_name_harmonise`, `person_consensus`, `theme_forced_name_fit`, `wikidata_place_review`, `name_resolver`, `osm_places`, `osm_etymology`
3. `corrections`: reviewed street-level decisions. Last, so it overrides everything.

The order is dependency order: a rule that refines another rule's output comes after it (`species` turns the generic "Plant" description that `vocabulary` and the hand lists left into the actual species; the audits check what the classifiers produced;
the resolver and the OpenStreetMap rules work on what is still unresolved, or verify it).

A rule computes its proposals from the hand classifications plus the layers *below* its own, never from its own previous layer or anything above it. That is what makes re-applying repeatable and keeps a layer from depending on its own old output.

## The rules

| Rule | Module | Inputs (knowledge data and context) | What it does |
|---|---|---|---|
| `vocabulary` | `vocabulary.py` | `global/vocabulary.json` (flowers, trees, birds, composers, painters, writers, royals, saints, science, myth, regions...), `global/famous_people.txt`, `global/person_labels.json` | the name alone shows the kind or the person; streets that do not already name a specific namesake (tier 3 to 5) |
| `titles` | `vocabulary.py` | title and first-name patterns | Burgemeester, Pastoor, Dokter, "Jan X"... become an unidentified person of a kind (mayor, religious, other); streets at tier 5 |
| `directional_road` | `directional.py` | `global/directional_places.json`; gemeente, wijk and buurt names in the data | `<Place>se<road>` (Eindhovensedijk) leads to that place: place/dutch_town or foreign_town |
| `species` | `species.py` | `global/species.txt` (Dutch stem = English name \| Latin name), `global/species_streets.txt` (exact street names) | a generic "Plant" or "Bird" description becomes the actual species, in the stable format `<Latin>; Dutch name '<stem>'` |
| `label_cleanup` | `labels.py` | the saint list in the vocabulary | a label must name the namesake and not repeat the road word: "Saint Janstraat" becomes "Saint John" |
| `bare_surname` | `surnames.py` | `global/common_words.txt`, `common_stems.txt`, famous surnames, the buurt's person-ness | **disabled.** Streets matched only to a Wikidata "family name"; an ordinary word becomes a local name, a famous surname the buurt backs becomes that person |
| `same_name_harmonise` | `audits.py` | other streets with the same name | the same name in several places with one reading and no buurt support for the outlier: the outlier takes the majority *kind*. A person majority is never harmonised by vote |
| `person_consensus` | `audits.py` | the buurt's subthemes | unidentified person streets take the kind of person the buurt supports |
| `theme_forced_name_fit` | `audits.py` | the street name, common words | a label whose only basis is the buurt theme must also be backed by the name (a species word, a title, a place); otherwise it becomes an ordinary compound word or a person by first-name pattern |
| `wikidata_place_review` | `place_review.py` | `global/place_match_corrections.json` (`not_a_place`, `named_places`) | **disabled.** accepted Wikidata place matches that are wrong (Brugstraat is not Bruges) are repaired; obscure places abroad get a generic description |
| `name_resolver` | `src/names/` | the name-level candidate table (Wikidata, our knowledge, already classified streets, OSM) | for streets at tiers 3 to 5, choose among the name's candidate readings using the street's buurt and wijk; reviewed-safe changes only |
| `osm_places` | `osm_places.py` | `build/raw/osm_places.json` (`src/osm_places.py --fetch`) | a street named like a hamlet, neighbourhood, stream, lake or park within 1 km is a local name (or river, lake); tier 2, since a feature nearby shows the place exists, not that the street is named for it |
| `osm_etymology` | `osm.py` | `build/enriched/osm_etymology.json` (`src/osm_etymology.py`) | OpenStreetMap `name:etymology:wikidata` names the namesake, tier 1; only non-conflicting proposals (see the method) |
| `corrections` | `corrections.py` | `knowledge/gemeenten/<province>/<gemeente>/corrections.json` | reviewed decisions, each with a reason; `from_osm: true` takes the namesake from the street's OSM etymology and keeps the kind given |

A rule that is disabled (`knowledge/global/rules_status.json`, with the date and why) is left out of runs that name no rule; naming it explicitly still runs it.

## Reading a `--check`

```
[titles] excluded 3 reviewed-and-rejected: ['Ter Vorseldreef', ...]

[titles] proposes 17: 0 already in the data, 17 would change
    Geldrop-Mi Johan Frisostraat    now unresolved/None/None -> person/other/None
    ...
  layer titles: 17 entries; against the layer on disk: 17 added, 0 removed, 0 changed, 0 unchanged
```

- **excluded**: proposals dropped because the street is in `global/rule_exclusions.json` for this rule.
- **proposes N: A already in the data, B would change**: what the rule would assert, compared with the classification *excluding its own layer*. "Already in the data" means another source says the same; "would change" lists examples as
  `now category/subcategory/label -> proposed`.
- **layer ... against the layer on disk**: what `--apply` would do to the stored file: entries added, removed, changed, unchanged. A rule is not required to be a fixed point of the data (later rules supersede earlier ones),
  but this line makes drift visible.

**Review a `--check` before an `--apply`.** Read the examples, especially the "would change" ones, and the removed entries. `--apply` never replaces a tier-1 street unless `--force` is given (except for the three rules whose job
is to correct or verify: `wikidata_place_review`, `corrections`, `osm_etymology`). Apply by naming the rules: regenerating every layer at once would rewrite thousands of historical entries.

## Add an exclusion

If a rule proposes something wrong, do not edit its layer by hand: the next `--apply` brings it back. Add the street to `knowledge/global/rule_exclusions.json` under the rule's name, with the reason, and `--apply` the rule:

```json
"vocabulary": {"Valkhof": "probably a place name rather than a falcon"}
```

## Add a correction

Add an entry to the gemeente's `corrections.json` (fields: `gemeente`, `street`, `category`, `subcategory`, `entity_label`, `entity_description`, `confidence`, `reason`, optional `from_osm`; always a `reason`), then `--apply corrections`.
A correction that names a street not in the data is skipped, not an error. The format and workflow are in [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Add a rule

1. A module in `src/rules/` with a function that takes a `Context` and returns `Override` records (`Override(gemeente_code, street, category, subcategory, entity_label, ..., rule="name")`). Helpers in `base.py`: `core()` (the name without article and road word), `person()`, `local_name()`.
2. Register it in `RULES` in `run.py` (name -> function, one-line description) and give it a place in `PRECEDENCE` in `src/overrides.py`.
3. Word lists go in `knowledge/global/`, not in code. Tests in `tests/test_rules.py`.
4. `--check` it on real data, review, `--apply` it, rebuild.

## Knowledge files

| File (`knowledge/global/`) | Used by | Format |
|---|---|---|
| `vocabulary.json` | `vocabulary` | named lists per theme (`APPLE`, `ART` name -> person, ...) |
| `famous_people.txt` | `vocabulary` | `Street|kind|Person name` per line |
| `person_labels.json` | `vocabulary` | street -> [subcategory, person name] |
| `species.txt`, `species_streets.txt` | `species` | `stem=English name\|Latin name`; `Street=English\|Latin\|stem` |
| `directional_places.json` | `directional_road` | `places` (stem -> place), `foreign` (places abroad), `also_directional` |
| `place_match_corrections.json` | `wikidata_place_review` | `not_a_place`, `named_places` |
| `common_words.txt`, `common_stems.txt`, `common_compounds.txt` | `bare_surname`, `theme_forced_name_fit` | one word or name per line; names made only of these are ordinary compounds, not namesakes |
| `rule_exclusions.json` | `run.py` | rule -> {street: reason} |
| `rules_status.json` | `run.py` | `disabled`: rule -> dated reason |
| `theme_labels.json` | `themes.py` | labels for derived buurt themes |
| `osm_entity_kinds.json`, `osm_suggestions.json` | `osm_etymology`, reports | reviewed kinds for OSM etymology items; tags worth adding in OpenStreetMap |
| `gemeenten.json`, `gemeenten_index.json` | `acquire.py`, everything | acquisition exceptions; the gemeente registry (CBS code to name and province) |

## Principles

* **The buurt decides between readings of a name, but never alone.** The same name can mean different people in different places, so identities are asserted only where the street's own buurt supports that kind of person, and a label that rests on the
  theme alone must also be backed by the name itself.
* **Evidence only moves toward tier 1** (`src/tiers.py`).
* **Knowledge is data**: improve a rule by editing data first; code only holds logic.
