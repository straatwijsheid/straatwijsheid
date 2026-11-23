# Publishing the map

The map is a static site. It is built on a machine that has the data (a full build needs hours of network access and is never run in CI), packaged, attached to a release, and deployed to GitHub Pages by a workflow.

```
pipeline.py rebuild  ->  package_map.py  ->  release asset  ->  "publish map" workflow  ->  GitHub Pages
```

## One-time setup

1. **Pages needs a public repository on a free plan.** Both repositories are public, so Pages is available. (GitHub Pages is not available for private repositories on the free plan.)
2. **Pages is enabled with GitHub Actions as the source** (Settings, Pages, Build and deployment). The site is at <https://maps.straatwijsheid.nl/> (custom domain, a CNAME to `straatwijsheid.github.io`; the github.io address redirects to it).
3. **Custom domain:** `maps.straatwijsheid.nl`, set under Settings, Pages, Custom domain, with a CNAME record to `straatwijsheid.github.io`. The map uses relative paths and works at the root of a domain as well as under `/straatwijsheid/`.

## Each publication

```bash
.venv/bin/python src/pipeline.py rebuild                # the map and its data in build/output/
.venv/bin/python src/package_map.py                     # build/dist/straatwijsheid-map.zip (and the unzipped site, build/dist/site/)
gh release create v0.1 build/dist/straatwijsheid-map.zip --title "v0.1" --notes "..."     # or: gh release upload TAG build/dist/straatwijsheid-map.zip --clobber
gh workflow run "publish map" -f tag=v0.1               # empty tag: the latest release
.venv/bin/python src/review_sheet.py --export build/dist/review-inputs.json.gz   # what the review sheets are made from
gh release upload v0.1 build/dist/review-inputs.json.gz  # then run "regenerate sheets" in the knowledge repository (Actions) for the new sheets
```

The workflow downloads `straatwijsheid-map.zip` from the release, checks it contains `index.html` and `data/`, and deploys it. The page reports where it came from in its footer (code commit, knowledge commit, OpenStreetMap snapshot dates).

To look at the packaged site before publishing: `python3 -m http.server --directory build/dist 8772` and open `http://localhost:8772/site/`.

## What is in the package

`index.html` (the map), `data/` (per-gemeente data, the buurt polygons and the search index, each as plain `.js` and pre-gzipped `.js.gz`), `PROVENANCE.json`, `.nojekyll`. Not the CSVs or the reports: they are separate downloads.

## Before the map is public

- The basemap is OpenStreetMap's public tile server, used under its [tile usage policy](https://operations.osmfoundation.org/policies/tiles/); [NOTICE.md](../NOTICE.md) says how we meet it. The map must keep: the HTTPS tile URL, the visible credit "© OpenStreetMap contributors" linked to the copyright page, no prefetching or offline copies, and no restrictive referrer policy (browsers send their own User-Agent and Referer). The server is best-effort with no guarantee, and access can be withdrawn; if the site grows a real audience, switch provider or serve our own tiles by changing `tile_url` and `tile_attribution` (`config.local.toml` or `TILE_URL` / `TILE_ATTRIBUTION`), no code change.
- [NOTICE.md](../NOTICE.md) must be accurate.
