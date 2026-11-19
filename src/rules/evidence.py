"""Which sources count as evidence of a specific namesake (shared by several rules)."""
TRUSTED = {"wikidata", "wikidata_surname_only", "web_search", "claude_knowledge", "title_heuristic"}
THEME_SOURCES = {"buurt_theme_override", "buurt_theme_fallback"}
WEAK_SOURCES = {"wikidata_weak_match", "wikidata_no_match", "wikidata_low_similarity", "surname_unsupported"}
