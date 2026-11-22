# Data sources and licences

The code in this repository is MIT-licensed (see `LICENSE`). The data it processes and produces is not covered by that licence:

| Source | What we use | Licence | Obligation |
|---|---|---|---|
| OpenStreetMap | street names and geometries, `name:etymology` tags, nearby places | ODbL 1.0 | credit "© OpenStreetMap contributors"; derived databases stay under ODbL |
| CBS / PDOK | buurt and wijk boundaries, province outlines | CC-BY 4.0 | credit CBS / PDOK |
| Wikidata | items, labels, descriptions (street name matching, OSM etymology items) | CC0 1.0 | none (credit appreciated) |

Our own classifications (category, subcategory, namesake, evidence tier) built on top of these are published in the **knowledge repository**
(`straatwijsheid/knowledge`, CC-BY 4.0) and in the build outputs. The maps and exports carry the attribution line; keep it when you reuse them.

The golden test fixture in `tests/fixture/` contains street *names* and our classifications with synthetic geometry; it holds no OpenStreetMap geometry.
