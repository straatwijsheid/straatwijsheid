"""Run with: .venv/bin/python tests/test_tiers.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tiers import evidence_tier as t

CASES = [
    (dict(category="person", subcategory="scientist", source="wikidata", entity_label="Christiaan Huygens"), 1),
    (dict(category="person", subcategory="writer_poet", source="web_search", entity_label="Anna Blaman"), 1),
    (dict(category="person", subcategory="military", source="claude_knowledge", entity_label="Bernard Montgomery"), 2),
    (dict(category="person", subcategory="monarch_statesman", source="claude_knowledge", entity_label="Willem (House of Orange)",
          entity_description="... so only the kind of namesake is asserted"), 3),
    (dict(category="thing", subcategory="flora", source="claude_knowledge", entity_label="Beech"), 2),
    (dict(category="person", subcategory="unspecified_individual", source="wikidata_surname_only", entity_label=None), 3),
    (dict(category="person", subcategory="mayor_local", source="title_heuristic", entity_label=None), 3),
    (dict(category="thing", subcategory="occupation_guild", source="claude_knowledge", entity_label=None), 3),
    (dict(category="place", subcategory="local_landmark", source="claude_knowledge", entity_label=None), 3),
    (dict(category="person", subcategory="other", source="claude_knowledge", entity_label=None,
          notes="Named after a person who could not be identified"), 3),
    (dict(category="person", subcategory="musician_composer", source="claude_knowledge", entity_label=None,
          notes="Kind of person inferred from buurt theme; individual not identified"), 4),
    (dict(category="thing", subcategory="fauna", source="buurt_theme_fallback", entity_label=None), 4),
    (dict(category="person", subcategory="other", source="buurt_theme_override", entity_label="Pink"), 4),
    (dict(category="thing", subcategory=None, source="wikidata_thing_match", entity_label=None), 4),
    (dict(category="place", subcategory="local_landscape_feature", source="claude_knowledge", entity_label=None), 5),
    (dict(category="place", subcategory="local_landscape_feature", source="buurt_theme_fallback", entity_label=None), 5),
    (dict(category="unresolved", subcategory=None, source="wikidata_weak_match", entity_label="Pink"), 5),
    (dict(category="person", subcategory="other", source="surname_unsupported", entity_label=None), 5),
]
bad = [(r, want, t(r)) for r, want in CASES if t(r) != want]
for r, want, got in bad:
    print("FAIL", r, "expected", want, "got", got)
print(f"{len(CASES) - len(bad)}/{len(CASES)} tier cases pass")
sys.exit(1 if bad else 0)
