"""The whole pipeline in one place, for any gemeenten.

  python src/pipeline.py add Tilburg Breda       new gemeenten, end to end
  python src/pipeline.py rebuild                 everything downstream of the data (after rules/overrides/knowledge changed)
  python src/pipeline.py status                  what is missing at each stage
  python src/pipeline.py bootstrap               fresh checkout: build directory + clone the knowledge repository

`add` runs, in order (each stage is also a script you can run alone):
  1 acquire    src/acquire.py            streets + buurten for the gemeenten (skips ones already fetched)
  2 wikidata   src/enrich_wikidata.py    look up every street name not cached yet (needs a Wikidata contact, see src/config.py; run it in your own shell if it is long)
  3 reconcile  src/reconcile.py          Wikidata guesses + buurt themes + overrides -> streets_final.json
  4 themes     src/themes.py             derive buurt themes for buurten that have none, then reconcile again so the themes act
  5 osm        src/osm_etymology.py      refresh OpenStreetMap etymology tags (--refresh-osm)
  6 rules      src/rules/run.py          check (print what each rule proposes) or --apply-rules to write them
  7 outputs    analyze, build_map, export_csv, tier statistics

Rules that need review (corrections, vocabulary exclusions) stay a human step: by default stage 6 only *checks*.
"""
from __future__ import annotations

import config
import argparse
import collections
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
SRC = ROOT / "src"


def run(*args):
    print("\n$", " ".join(str(a) for a in args), flush=True)
    subprocess.run([PY, *map(str, args)], cwd=ROOT, check=True)


def stage_acquire(gems):
    run(SRC / "acquire.py", *gems)


def stage_wikidata(gems):
    if not config.CONTACT:
        sys.exit("Stage wikidata needs a Wikidata contact (a contact address, never stored in a tracked file): set WIKIDATA_CONTACT or wikidata_contact in config.local.toml and re-run, or run\n"
                 f"  {PY} src/enrich_wikidata.py --missing\nyourself, then continue with: python src/pipeline.py rebuild --themes")
    run(SRC / "enrich_wikidata.py", "--missing", *[x for g in gems for x in ("--gemeente", g)])


def stage_themes(gems):
    run(SRC / "reconcile.py")
    run(SRC / "themes.py", *[x for g in gems for x in ("--gemeente", g)])
    run(SRC / "reconcile.py")


def stage_osm():
    run(SRC / "osm_etymology.py", "--fetch")
    run(SRC / "osm_etymology.py", "--build")


def stage_rules(apply=()):
    """Check what every enabled rule proposes, or regenerate the named rules' override layers. Regenerating all layers at once would change
    thousands of historical, partly reviewed entries (see issue #24: layer audit), so applying always names the rules."""
    if apply:
        run(SRC / "rules" / "run.py", "--apply", *apply)
        run(SRC / "reconcile.py")
    else:
        run(SRC / "rules" / "run.py", "--check")


def stage_outputs():
    run(SRC / "reconcile.py")
    run(SRC / "analyze.py")
    run(SRC / "build_map.py")      # also writes output/PROVENANCE.json (code + knowledge commits, OSM snapshot dates)
    run(SRC / "export_csv.py")
    tiers()


def stage_bootstrap(clone=True):
    """Prepare a fresh checkout: the build directory, and the knowledge repository (cloned from config.KNOWLEDGE_REPO unless it is already there)."""
    config.ensure_dirs()
    print(config.describe())
    k = config.KNOWLEDGE
    if not (k / "global").exists():
        if not clone:
            sys.exit(f"No knowledge at {k}. Clone it (git clone {config.KNOWLEDGE_REPO} {k}) or set knowledge_dir in config.local.toml.")
        print(f"\nCloning the knowledge repository {config.KNOWLEDGE_REPO} -> {k}")
        r = subprocess.run(["git", "clone", config.KNOWLEDGE_REPO, str(k)])
        if r.returncode:
            sys.exit("Clone failed (a private repository needs access: `gh auth login`, or clone it yourself and set knowledge_dir in config.local.toml).")
    import knowledge, provenance
    st = provenance.git_state(k)
    print(f"\nknowledge: {st['commit'] or 'not a git checkout'}{' (modified)' if st['dirty'] else ''}; {len(knowledge.shard_dirs())} gemeente folders")
    have = sorted((config.RAW).glob("streets_*.geojson"))
    print(f"build data: {len(have)} gemeenten acquired" + ("" if have else "; start with  python src/pipeline.py add <gemeente> ..."))
    return knowledge.check()


def tiers():
    rows = json.loads((config.ENRICHED / "streets_final.json").read_text())
    c = collections.Counter(r["evidence_tier"] for r in rows)
    n = len(rows)
    print(f"\n{n} streets in {len({r['gemeente'] for r in rows})} gemeenten; evidence tiers: " + ", ".join(f"{t}: {c[t]} ({c[t] / n:.1%})" for t in sorted(c)))


def status():
    import geopandas as gpd
    gems = sorted(set(gpd.read_file(config.RAW / "streets.geojson")["gemeente"]))
    final = json.loads((config.ENRICHED / "streets_final.json").read_text())
    themes = json.loads((config.ENRICHED / "buurt_themes_full.json").read_text())["buurten"]
    have_final = {r["gemeente"] for r in final}
    have_theme = {t["gemeente"] for t in themes}
    sys.path.insert(0, str(SRC))
    from enrich_wikidata import missing_street_names
    miss = missing_street_names(config.ENRICHED / "all_streets_wikidata.jsonl")
    print(f"acquired: {len(gems)} gemeenten; classified: {len(have_final)}; with themes: {len(have_theme)}")
    print(f"not classified: {sorted(set(gems) - have_final) or 'none'}; without themes: {sorted(set(gems) - have_theme) or 'none'}")
    print(f"street names not yet looked up on Wikidata: {len(miss)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["add", "rebuild", "status", "bootstrap"])
    ap.add_argument("gemeenten", nargs="*")
    ap.add_argument("--skip-wikidata", action="store_true", help="add: do not look names up (e.g. already done in your own shell)")
    ap.add_argument("--refresh-osm", action="store_true", help="re-fetch the OSM etymology tags (Noord-Brabant-wide)")
    ap.add_argument("--apply-rules", nargs="+", metavar="RULE", help="regenerate these rules' override layers instead of only checking (name them; see rules/run.py --list)")
    ap.add_argument("--no-clone", action="store_true", help="bootstrap: do not clone the knowledge repository, only check it is there")
    ap.add_argument("--themes", action="store_true", help="rebuild: also derive missing buurt themes")
    a = ap.parse_args(argv)
    if a.command == "bootstrap":
        return stage_bootstrap(clone=not a.no_clone)
    if a.command == "status":
        return status()
    if a.command == "add":
        if not a.gemeenten:
            ap.error("add needs at least one gemeente")
        stage_acquire(a.gemeenten)
        if not a.skip_wikidata:
            stage_wikidata(a.gemeenten)
    if a.command == "add" or a.themes:
        stage_themes(a.gemeenten)
    if a.refresh_osm:
        stage_osm()
    if a.command == "add" or a.apply_rules:
        stage_rules(apply=a.apply_rules or ())
    stage_outputs()


if __name__ == "__main__":
    main()
