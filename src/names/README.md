# Name-level candidate table

What we know about a *name* is kept apart from what a *street* turns out to be. Street names repeat across the country and mean
different things in different places (Willemstraat: the House of Orange, or Willem Drees), so the table records, per name, every
interpretation we have evidence for, and a resolver picks one per street from its buurt and wijk.

```
python src/names/run.py --build                 # data/names/candidates.jsonl (derived, git-ignored, rebuilt in ~3 s)
python src/names/run.py --show Willem kerk      # a name's candidates; how each of its streets resolves now
python src/names/run.py --backtest              # how well does it recover classifications it is not shown?
python src/names/run.py --propose               # dry run on streets with no named namesake: what it would accept
.venv/bin/python tests/test_names.py
```

* **Key**: the name's core (no article, no road word), lowercased: `Beukenlaan`, `Beukenstraat`, `De Beuken` -> `beuken`.
* **Candidate**: a kind `(category, subcategory)` with its evidence: where the name was already classified as that kind (weighted by
  evidence tier), knowledge-rule hits (vocabulary, species, famous people, directional roads, place names, ordinary words, title
  patterns), and what Wikidata matched. Evidence is *mass*; a candidate's prior is its share of the name's mass.
* **Resolution**: `score = (1-lam)*prior + lam*fit`, where `fit` is how well the kind matches what the street's neighbours in the
  same buurt (0.7) and wijk (0.3) are named after. It returns a kind, a label **only if the namesakes seen agree** (otherwise
  kind-only), a margin, and `accept`/`ambiguous`. It never writes to `manual_overrides.json`.

## What the backtest says (current data)

*Leave-one-out*, 3,000 streets with a named namesake, own classification hidden:

| | kind right | when it accepts (79%) |
|---|---|---|
| name only | 80% | 88% |
| name + buurt/wijk | 81% | **91%** (category 99%) |

* The buurt's main value is **calibration, not top-1**: for ambiguous names it lifts the precision of accepted answers from 77% to 87%
  (at the cost of accepting fewer), and barely changes the top choice. For names with one dominant meaning it changes nothing.
* Streets verified externally (tier 1): 97% with Wikidata evidence, **48%** without it. That is the honest estimate of how much
  rests on Wikidata being present for a name.
* *New-gemeente simulation* (a whole gemeente hidden, its tier-1 streets as seeds, then its own confident predictions as context):
  72% kind / 84% category overall, **85% kind when it accepts** (74% of streets); the second pass with neighbour context adds
  nothing, because neighbours that are themselves predictions carry no new information. Context only helps with *independent*
  neighbours (verified streets), so a new gemeente needs a seed of externally verified streets.

Caveats: the "truth" is the current dataset, partly my own judgement made with the same knowledge, so these numbers flatter the
resolver; labels match only ~74%.

## Next

* Use the resolver as the engine for new gemeenten (seed with Wikidata, resolve the rest, send `ambiguous` to review).
* Add independent evidence per candidate (web search results, OSM tags such as `wikidata=*`/`name:etymology` on the street itself).
* Fold subcategory families (local_landmark vs local_landscape_feature) so near-synonyms do not split a name's mass.
