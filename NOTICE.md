# Data sources and licences

The code in this repository is MIT-licensed (see `LICENSE`). The data it processes and produces is not covered by that licence. This page is a practical summary for reusers, not legal advice.

## Sources

| Source | What we use | Licence | Obligation |
|---|---|---|---|
| OpenStreetMap | street names and geometries, `name:etymology` tags, nearby places, the map's basemap tiles | ODbL 1.0 | credit "© OpenStreetMap contributors"; derived databases stay under ODbL (see below) |
| CBS / PDOK | buurt and wijk boundaries, province and gemeente outlines (CBS Wijk- en buurtkaart via PDOK) | CC-BY 4.0 | credit CBS / PDOK |
| Wikidata | items, labels, descriptions (street-name matching, items referenced by OSM etymology tags) | CC0 1.0 | none (credit appreciated) |

We use no Wikipedia text, Commons media or other CC-BY-SA material. Keep it that way: it would change the terms of everything below.

## Attribution line

The map footer and `PROVENANCE.json` carry this line, with the build date and the code, knowledge and OSM snapshot versions:

> Data © OpenStreetMap contributors (ODbL), CBS/PDOK (CC-BY 4.0), Wikidata (CC0).

Keep it (or an equivalent that names all three) when you reuse a map, an export or a screenshot.

## Reusing what we publish

| What | Licence | Reuse |
|---|---|---|
| Code (`straatwijsheid/straatwijsheid`) | MIT | any use; keep the copyright notice |
| Knowledge repository (`straatwijsheid/knowledge`): classifications, corrections, review answers, curated lists | CC-BY 4.0 | any use, including commercial, with credit as in its `ATTRIBUTION.md` |
| Maps, images and screenshots built from the data | produced work | credit "© OpenStreetMap contributors" and the other sources; no share-alike on the image itself |
| CSV/JSON street lists in the build outputs (`streets_classified.csv`, `streets_final.json`, `buurt_themes*`) | database combining our judgements with OSM-derived rows (street names, way classes, geometry) | treat as an ODbL derivative database: credit OSM contributors and, if you publish a database built from it, offer it under ODbL. Our own columns (category, subcategory, namesake, evidence tier) are CC-BY 4.0 on their own |
| Wikidata cache and `all_streets_wikidata.jsonl` (planned release asset) | CC0 for the Wikidata content; our derived category and confidence fields are CC-BY 4.0 | free to reuse; mention "Contains data from Wikidata (CC0 1.0)" |

Rules of thumb: if you extract only our judgements (what a street is named after), CC-BY is enough. If you republish street names with geometry or other OSM data, ODbL applies to that database.

## Services we call

- Overpass API (OpenStreetMap data): we send a generic client name, with no personal details. Be polite with it and use a mirror for large runs (`overpass_url` in `config.local.toml`).
- Wikidata / Wikimedia APIs: polite pacing and a User-Agent. An optional contact address can be given in the git-ignored `config.local.toml` or the `WIKIDATA_CONTACT` environment variable; it is never written to a tracked file or an output.
- The map's basemap tiles come from OpenStreetMap's public tile servers, which are for light use (see the OpenStreetMap tile usage policy). A public site with real traffic needs a different tile provider, or our own tiles, before it is published.

## Test fixture

The golden test fixture in `tests/fixture/` contains street *names* and our classifications with synthetic geometry; it holds no OpenStreetMap geometry.

## Personal data

The repositories hold no personal data about contributors beyond git commit metadata (author name and email). Namesakes in the data are overwhelmingly historical or public figures; contributors should not add private details about living private individuals to review sheets.
