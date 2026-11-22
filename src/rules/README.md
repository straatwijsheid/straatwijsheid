# Classification rules

Versioned, tested rule families. Each is a pure function of the data: it takes a `Context` (the streets, the current
`streets_final.json`, the Wikidata cache, place names) and returns `Override` records. Only `run.py` touches
its override layer (`data/enriched/overrides/<rule>.json`, see `src/overrides.py`).

```
python src/rules/run.py --list                 # the rules
python src/rules/run.py --check [RULE ...]      # dry run: what each proposes, and how that compares with the data now
python src/rules/run.py --apply RULE [...]      # regenerate those rules' override layers (prints how each layer changed); --cascade also redoes the rules above
.venv/bin/python tests/test_rules.py            # unit tests;   tests/test_tiers.py for the evidence tiers
```

After `--apply`, re-run `src/reconcile.py --full`, `src/analyze.py`, `src/build_map.py`, `src/export_csv.py`.

| rule | module | what it does |
|---|---|---|
| `directional_road` | `directional.py` | `<Place>se<road>` -> the place the road leads to |
| `vocabulary` | `vocabulary.py` | flowers, trees, birds, composers, painters, writers, royals, saints, science, myth, regions... by name |
| `titles` | `vocabulary.py` | Burgemeester/Pastoor/first-name patterns -> an unidentified person |
| `species` | `species.py` | a generic "Plant"/"Bird" description -> the actual species |
| `bare_surname` | `surnames.py` | Wikidata family-name-only matches, resolved with the buurt's naming theme |
| `same_name_harmonise` | `audits.py` | same name, different class, no buurt support -> the majority class |
| `person_consensus` | `audits.py` | unidentified person streets take the kind of person the buurt supports |
| `theme_forced_name_fit` | `audits.py` | a label whose only basis is the buurt theme must also be backed by the name |
| `wikidata_place_review` | `place_review.py` | accepted Wikidata place matches that are not places, or mislead |

## Principles

* **The buurt decides between readings of a name, but never alone.** The same name can mean different people in different
  places, so identities are only asserted where the street's own buurt supports that kind of person, and a label that
  rests on the theme alone must also be backed by the name itself (a species word, a title or first-name pattern, a place).
* **Evidence only moves toward tier 1** (`src/tiers.py`): `apply` never replaces a verified (tier 1) street without `--force`.
* **Knowledge is data**, in `data/knowledge/`: `species.txt`, `species_streets.txt`, `vocabulary.json`, `famous_people.txt`,
  `person_labels.json`, `place_match_corrections.json`, `directional_places.json`, `common_stems.txt`, `common_words.txt`,
  `common_compounds.txt`. Improve a rule by editing data first; code only holds logic.

## What `--check` shows today

Rules are not required to be fixed points of the data (later rules supersede earlier ones), but `--check` makes drift visible:
`directional_road` reproduces every one of its 639 entries; `wikidata_place_review` and `theme_forced_name_fit` have almost
nothing left to change (they were applied in bulk); `vocabulary` and `titles` propose upgrades (e.g. naming Chopin where the data
only says "composer") for streets classified before those vocabularies grew. Review a `--check` before `--apply`.

The hand-written street-by-street classifications are not rules: see `scripts/legacy/README.md`.
