"""Name-level candidate table.

Street names repeat across the country and often mean different things in different places, so what we know about a
*name* is kept separately from what a *street* turns out to be:

  candidates.py   for each name (its core, without the road word): every interpretation we have evidence for, with the evidence
  resolve.py      for one street: choose among its name's candidates using the street's buurt and wijk
  run.py          build / inspect / backtest

The table merges four kinds of evidence: what Wikidata says the name matches, what our knowledge rules say it denotes
(vocabularies, species, famous people, places, ordinary words), and what the name was judged to be wherever it has already
been classified (weighted by evidence tier). Nothing here writes to manual_overrides.json.
"""
