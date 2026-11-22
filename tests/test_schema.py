"""Core refuses a knowledge checkout whose schema_version it does not read.
Run with: .venv/bin/python tests/test_schema.py"""
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config
import gemeenten
import schema
from _registry import write_registry


class Tmp:
    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        self.old = config.KNOWLEDGE
        config.KNOWLEDGE = Path(self.d.name) / "k"
        write_registry({"GM0772": ("Eindhoven", "Noord-Brabant")})
        return self

    def __exit__(self, *a):
        config.KNOWLEDGE = self.old
        self.d.cleanup()


def refused(msg_part):
    try:
        gemeenten.index()
    except schema.SchemaMismatch as e:
        assert msg_part in str(e), str(e)
        return str(e)
    raise AssertionError("an incompatible knowledge checkout must be refused")


def test_matching_version_is_accepted():
    with Tmp():
        assert schema.found() == schema.SCHEMA_VERSION and gemeenten.name_of("GM0772") == "Eindhoven"


def test_newer_knowledge_says_update_the_code():
    with Tmp():
        (config.KNOWLEDGE / "schema_version").write_text(f"{schema.SCHEMA_VERSION + 1}\n")
        assert "update this code" in refused("newer")


def test_older_knowledge_says_update_the_checkout():
    with Tmp():
        (config.KNOWLEDGE / "schema_version").write_text(f"{schema.SCHEMA_VERSION - 1}\n")
        assert "git -C knowledge pull" in refused("older")


def test_missing_or_garbled_file_is_refused():
    with Tmp():
        (config.KNOWLEDGE / "schema_version").unlink()
        refused("no readable schema_version")
        (config.KNOWLEDGE / "schema_version").write_text("one\n")
        refused("no readable schema_version")


def test_the_real_checkout_matches_this_code():
    import _need_knowledge  # noqa: F401
    schema.require()


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} schema tests pass")
    sys.exit(1 if fails else 0)
