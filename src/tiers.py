"""Evidence tiers: how a street's classification was arrived at.

The tier is derived from a street's final record (source, entity_label, category, subcategory,
notes), so it works for any data source and can be recomputed whenever the rules change.
Lower numbers are stronger evidence; refinement work should only ever move streets *down*
in number (toward 1), never silently replace a stronger label with a weaker one.

  1  Identified, external evidence   a specific namesake backed by Wikidata or a web source
  2  Identified, from knowledge      a specific namesake from general knowledge, not verified
  3  Kind known from the name        no individual, but the name itself shows the kind
                                     (a title/first-name pattern, a species word, a trade term,
                                     a Wikidata "family name" match, an institution word)
  4  Kind inferred from the buurt    the kind rests on the neighbourhood's naming theme (or a
                                     weak thing-match) rather than on the name
  5  Not identified                  no namesake and no kind: generic/local names and anything
                                     unresolved
"""

TIER_NAMES = {
    1: "Identified (external evidence)",
    2: "Identified (from knowledge, unverified)",
    3: "Kind known from the name",
    4: "Kind inferred from neighbourhood theme or weak match",
    5: "Not identified",
}

WEAK_SOURCES = {"wikidata_weak_match", "wikidata_no_match", "wikidata_low_similarity", "surname_unsupported"}
THEME_SOURCES = {"buurt_theme_override", "buurt_theme_fallback"}
EXTERNAL_SOURCES = {"wikidata", "web_search"}
LOCAL_FEATURE = "local_landscape_feature"
KIND_ONLY_MARKER = "only the kind of namesake is asserted"   # a label like "Willem (House of Orange)" names a kind, not a person
INFERRED_MARKERS = ("inferred from", "kind of person inferred", "kind inferred from the buurt")


def _s(v):
    return v if isinstance(v, str) and v else None


def evidence_tier(row) -> int:
    category, sub = _s(row.get("category")), _s(row.get("subcategory"))
    source, label = _s(row.get("source")), _s(row.get("entity_label"))
    notes = (_s(row.get("notes")) or "").lower()

    if category in (None, "unresolved", "unclear") or source in WEAK_SOURCES:
        return 5
    if category == "place" and sub == LOCAL_FEATURE and not label:
        return 5
    if source in THEME_SOURCES or source == "wikidata_thing_match" or any(m in notes for m in INFERRED_MARKERS):
        return 4
    if label:
        if KIND_ONLY_MARKER in (_s(row.get("entity_description")) or "").lower():
            return 3
        return 1 if source in EXTERNAL_SOURCES else 2
    return 3
