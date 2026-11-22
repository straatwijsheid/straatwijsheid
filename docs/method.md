# Method and principles

What the project claims about a street, how it decides, and how sure it says it is. The tooling is in [pipeline.md](pipeline.md); the rule families in [src/rules/README.md](../src/rules/README.md).

## The question

For each named street in each gemeente: **what is it named after?** The answer has two parts, kept apart on purpose:

- the **kind** of namesake, a `category` (**person**, **place** or **thing/concept**) and a finer `subcategory` (composer, saint, river, castle, flower, occupation...), and
- where we can, the **specific namesake** (`entity_label`: "Frits Philips"), with a source.

A street with a known kind but no named individual is a legitimate result: "a person, probably an artist" is more honest than a wrong name. Streets we cannot place at all are `unresolved`; the
map and the data say so rather than guess. Categories can also be `mixed` or `unclear` for buurt themes and streets that fit none.

Buurten (neighbourhoods) and wijken (districts) come from CBS. A buurt's **naming theme** ("composers", "trees and plants") is what its classified streets mostly are, and is a hint used to read the streets in it.

## Evidence tiers

Every street carries an `evidence_tier`, computed from its final record by `src/tiers.py` so it can be recomputed whenever rules change. Lower is stronger.

| Tier | Meaning | Typical basis |
|---|---|---|
| 1 | Identified, external evidence | a Wikidata match, an OpenStreetMap `name:etymology` tag, or a web source |
| 2 | Identified from knowledge, unverified | a namesake from general knowledge, not checked against a source |
| 3 | Kind known from the name | no individual, but the name shows the kind: a title (Burgemeester), a species word, a trade term, a surname match |
| 4 | Kind inferred from the buurt | the kind rests on the neighbourhood theme, or on a weak "thing" match |
| 5 | Not identified | generic or local names, anything unresolved |

**Evidence only moves toward tier 1.** A rule or a rebuild never silently replaces a stronger label with a weaker one: applying a rule does not overwrite a verified (tier 1) street unless `--force` says so.
The tier tells a reader how much to trust a label; it is not a probability, and `confidence` is a separate, per-source score.

## How a street is decided

The first-pass logic is in `src/reconcile.py`; everything after it is an override layer (rules, reviewed corrections).

1. **Look the name up.** The street name without its road word ("straat", "laan"...) is searched on Wikidata and the best match scored (`confidence`).
2. **Read it against its buurt.** A match at confidence 0.70 or more that agrees with the buurt's theme is kept. A weaker or conflicting match gives way to a strongly themed buurt (theme confidence 0.80 or more), with
   `source` `buurt_theme_override`; with no confident match and a theme of 0.60 or more the street gets the theme's kind with `buurt_theme_fallback` (discounted, tier 4). If the theme is not strong enough, the match is kept as it is.
3. **Titles.** A name starting with a person title (Burgemeester, Pastoor, Generaal, Sint...) is a person, whatever Wikidata found; a matched entity is kept only if it looks like a person, not the street itself, a tram stop or a windmill.
4. **Surname-only matches are weak.** Wikidata "family name" items say a surname exists, not whom the street honours, and many Dutch surnames are ordinary words (Wal, Vloet, Molendijk). Without a title or a buurt that names people, such a match is rejected as unresolved.
5. **Rules add what Wikidata cannot**: species, composers, saints, directional roads (`Eindhovensedijk` leads to Eindhoven), titles, places named after a nearby feature, consistency audits. Each rule owns one override layer.
6. **OpenStreetMap etymology** (`name:etymology:wikidata`) is independent evidence from the mapping community. It names the namesake (tier 1). It is applied only where it does not conflict: as new information for streets at tiers 3 to 5, or as an upgrade where
   our own tier 1 or 2 kind agrees. Where our classification and OSM disagree on the category, the street is left alone and reported (`src/osm_report.py`) for review; the confirmed case is then settled by a correction.
7. **Reviewed corrections** are last and strongest. A person who looked at the street decides, and gives a reason.

## Principles

- **The buurt decides between readings of a name, but never alone.** The same name can honour different people in different places. A namesake is asserted only where the street's own buurt supports that kind of person, and a label that rests on the buurt
  theme alone must also be backed by the name itself (a species word, a title or first-name pattern, a place).
- **Same-named streets do not share a namesake by assumption.** Wikidata results are per name, but each street is judged in its own gemeente and buurt. Gemeenten themselves are identified by CBS code, never by name (two are called Bergen).
  The one audit that looks across gemeenten, `same_name_harmonise`, only aligns the *kind* with the majority where the street has no support of its own, and never changes a person majority by vote.
- **Kind-only labels do not name a person.** A label such as "Willem (House of Orange)" says which kind of Willem was meant, not which; it counts as tier 3, not as an identification.
- **A kind is not an identity.** Colour on the map is shown only where a specific namesake is confirmed; a theme-based guess is shown grey even when its category is known.
- **Knowledge is data, code is logic.** Word lists, species, vocabularies, reviewed corrections and exclusions live in the [knowledge repository](https://github.com/straatwijsheid/knowledge), each decision with a reason, so improving a rule is mostly editing data and a reviewer can read it.
- **Say how a result was reached.** Every row carries its `source` and, where useful, `notes`; the map shows the basis in each tooltip.
- **Do not assert what the evidence does not carry.** A place name taken from a Wikidata match that is not a place nearby, a "river" for a street that merely sounds like one, a person for a common noun: these are reviewed away rather than counted.

## What this is not

It is not a verified record of what every street is named after. Tier 1 is the share backed by an external source; the rest is as good as the rules and the reviewers behind it, and says so. Structural limits are listed in [limitations.md](limitations.md).
