# Known limitations

Structural limits of the data and method: things that stay true until the design changes. Measurements and one-off findings are not kept here; the evidence tiers and the data say how much is identified.

## What a "street" is here

- **A street is a named way in OpenStreetMap.** We take every `highway=*` way with a `name` inside a gemeente's CBS outline, except types that are not streets (platforms, bus stops, services...). A street that OSM does not have, or has without a name, is not in the data.
  Streets are as complete, as current and as correctly named as OpenStreetMap is; a recent renaming appears when the data is re-fetched.
- **One row per distinct name per gemeente.** All ways with the same name in one gemeente are merged into one street with one geometry and one classification. Two different streets that share a name in the same gemeente cannot be told apart, and a long street
  split over several buurten belongs to one of them.
- **Way class is a coarse label.** Streets are split into street, path (footway, cycleway, track...) and under construction by the *most street-like* OpenStreetMap type among the street's ways. A street with mixed ways is placed by that rule; service roads and parking aisles count as
  streets; the path and construction layers on the map follow from it. Mapping choices in OSM (a street tagged as a service road, a footway named like a street) therefore show up here.
- **Shared names across a border.** The CBS outline of Baarle-Nassau contains the Belgian Baarle-Hertog enclaves. Only ways inside the Dutch area are fetched, but a name shared with Baarle-Hertog (Molenstraat, Kapelstraat...) may carry segments of the Belgian street in its merged geometry.
- **Merged and renamed gemeenten** need an entry in `gemeenten.json` to be fetched (a buurt prefix picks the right area out of the current gemeente). Gemeenten that no longer exist keep their historic CBS code in the registry.

## What a classification claims

- **A namesake is an interpretation.** Where there is no external evidence (tiers 2 to 5) the label is a judgement: general knowledge for tier 2, a kind read from the name for tier 3, a guess from the neighbourhood for tier 4. Only tier 1 is backed by a source, and even a source can be a naming
  tradition rather than a documented decision.
- **Labels resting on the buurt theme are weaker.** A label that exists because the neighbourhood is themed ("composers") and the name only weakly fits is less reliable than one the name itself supports. The pipeline requires name support for such labels, but the residue is real, and it is tier 4 at best.
- **Themes are partly circular.** A buurt's theme is derived from its streets' classifications, which an earlier theme may have shaped, so a theme can reinforce itself without new evidence (see issue #27). Hand-written themes are the independent exception.
- **Category is a simplification.** Person, place or thing/concept, with sub-kinds, cannot describe everything: a hospital named after a saint, a street named after a family estate, or a name with several plausible origins is filed under the closest kind and sometimes
  left `unclear`. The map's sub-groups are buckets of finer subcategories.
- **Wikidata matching is per name.** A match is found for the name without its road word and then judged in each place; ordinary words coincide with places and surnames, and the wrong entity can score well. The rules and reviews catch many cases; they cannot catch all.
- **The Wikidata answers are a dated cache**, not a reproducible function: Wikidata changes, and a refresh can change a result.

## Where the depth differs

- **The first gemeenten were classified more thoroughly.** Early gemeenten (Eindhoven and its neighbours) were classified by hand and by language-model reading, in waves, before the rules existed; those classifications are kept as the frozen `legacy_hand` layer. Later gemeenten rest more on Wikidata, rules and themes,
  so the share of identified streets differs between gemeenten for reasons of method as well as of the streets. Compare gemeenten with the evidence tier in view, not the label alone.
- **The first-wave scripts are not in either repository.** `legacy_hand` is irreplaceable data whose generating scripts were archived and are not re-runnable; the layer is frozen and only corrections change it.
- **OpenStreetMap etymology tags are unevenly spread**, concentrated where mappers have worked on them, and are currently fetched for Noord-Brabant only. Where they exist they are the strongest evidence; their absence is not evidence of anything.

## Coverage and presentation

- **Coverage is Noord-Brabant** today. Other provinces need acquisition, a Wikidata lookup and the rules; the pipeline is generic, the data is not yet there (see the issue tracker for the plan).
- **The map shows a few gemeenten at a time**; the data files are per gemeente and there is no tiled whole-country view yet.
- **Reviews are local knowledge, not authority.** A correction from a contributor is as good as its source; unsourced knowledge is capped at tier 2.
