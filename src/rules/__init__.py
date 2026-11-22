"""Versioned classification rules.

Each rule family lives in its own module and is a pure function of its inputs: it takes street
names / final records plus a Context and returns Override records. Nothing here reads or writes
global state; the CLI in `run.py` is the only place that writes override layers.

Curated knowledge the rules rely on (species, vocabularies, famous people, ...) is data under
knowledge/, not code. The one-off, street-by-street hand classifications made while the
dataset was being built are kept verbatim under scripts/legacy/ (see its README); their results
live in the override layers (see src/overrides.py).
"""
