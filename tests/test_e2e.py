"""End to end on the golden fixture (tests/fixture: 84 streets in 3 gemeenten, a canned Wikidata cache, the matching override layers; no network,
no real knowledge repository): reconcile must reproduce expected_final.json, and the downstream steps must run.
Run with: .venv/bin/python tests/test_e2e.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixture"


def run(script, env):
    r = subprocess.run([sys.executable, str(ROOT / "src" / script)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"{script} failed:\n{r.stdout[-800:]}\n{r.stderr[-1500:]}"


def test_reconcile_reproduces_the_golden_classification_and_outputs_build():
    with tempfile.TemporaryDirectory() as d:
        build = Path(d) / "build"
        shutil.copytree(FIX / "build", build)
        env = {**os.environ, "STREETS_BUILD_DIR": str(build), "STREETS_KNOWLEDGE_DIR": str(FIX / "knowledge"), "WIKIDATA_CONTACT": ""}
        run("reconcile.py", env)
        got = {(r["gemeente_code"], r["street"]): r for r in json.loads((build / "enriched" / "streets_final.json").read_text())}
        expected = json.loads((FIX / "expected_final.json").read_text())
        assert len(got) == len(expected) == 84, (len(got), len(expected))
        bad = [(e["gemeente"], e["street"], {k: (e[k], got[(e["gemeente_code"], e["street"])].get(k)) for k in e if e[k] != got[(e["gemeente_code"], e["street"])].get(k)})
               for e in expected if any(e[k] != got[(e["gemeente_code"], e["street"])].get(k) for k in e)]
        assert not bad, f"{len(bad)} streets differ from the golden file, e.g. {bad[:3]}"
        for script in ("analyze.py", "export_csv.py", "build_map.py"):
            run(script, env)
        assert (build / "output" / "streets_classified.csv").exists() and (build / "output" / "streets_map.html").exists()
        prov = json.loads((build / "output" / "PROVENANCE.json").read_text())
        assert {"generated_at", "code", "knowledge", "osm_snapshots"} <= prov.keys()


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} end-to-end tests pass")
    sys.exit(1 if fails else 0)
