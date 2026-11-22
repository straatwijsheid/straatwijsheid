"""Package the built map as a static site for publishing (GitHub Pages).

  python src/package_map.py            build/dist/straatwijsheid-map.zip and the unzipped site in build/dist/site/

The site is the map (`index.html`), its per-gemeente data files (`data/`, both the plain `.js` and the pre-gzipped `.js.gz`) and `PROVENANCE.json`.
Nothing else from `build/output/` goes in: the CSVs and reports are separate downloads, not part of the map. Build the map first (`pipeline.py rebuild`).
The page refers to its data by relative paths, so it works from the root of a domain and from a sub-path such as /straatwijsheid/.
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

import config

DIST = config.BUILD_DIR / "dist"
SITE = DIST / "site"
ZIP = DIST / "straatwijsheid-map.zip"


def package() -> Path:
    page = config.OUTPUT / "streets_map.html"
    data = config.OUTPUT / "data"
    if not page.exists() or not data.is_dir():
        sys.exit(f"No built map in {config.OUTPUT}: run  python src/pipeline.py rebuild  first.")
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    shutil.copy(page, SITE / "index.html")
    shutil.copytree(data, SITE / "data")
    prov = config.OUTPUT / "PROVENANCE.json"
    if prov.exists():
        shutil.copy(prov, SITE / "PROVENANCE.json")
    (SITE / ".nojekyll").write_text("")           # publish the files as they are
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(SITE.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(SITE).as_posix())
    return ZIP


if __name__ == "__main__":
    z = package()
    n = sum(1 for p in SITE.rglob("*") if p.is_file())
    print(f"{n} files; {z} ({z.stat().st_size / 1e6:.0f} MB). The unzipped site is {SITE}")
