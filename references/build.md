# Building the framework

## From principles to rules
1. List every principle of every book (`### P` lines). Group by **the decision it helps with at the destination** ("when may a gag appear?"), never by book or chapter.
2. In each group, note agreement (2 books or more: `consensus`), single sources, disagreement, and what the user already decided (`user` wins).
3. Write the rule as one action somebody can do, then its reason, limits and test. Split a rule that says two things. Merge rules that fail together.
4. Mark at most 15 as `must`: the ones whose absence the user would notice. The rest are `also`.

A good rule: names the actor and the moment, can be broken, and two people checking it would agree. A bad rule: "make it feel natural".

**Tests**, best first:
- `machine`: a script that exits 1 (a lint, a probe, a unit test). Needs `run`. Try it on one good and one bad case.
- `measure`: a number someone can read off (seconds, count, contrast).
- `look`: what to look at, and what wrong looks like. Never just "check that it is good".

## rules.json
```json
{
  "id": "visual-comedy", "title": "...", "version": "1.0", "updated": "2026-11-24",
  "doc": "docs/visual-comedy.md", "card": "docs/frameworks/visual-comedy/CARD.md",
  "goal": "What is different in the output, as a viewer or user would see it.",
  "destination": "Who applies it, where.",
  "wins_over_this": ["what the user says now", "CLAUDE.md rules"],
  "preserve": ["..."],
  "stages": ["plan", "build", "review"],
  "books": [{"key": "Lyons", "slug": "comedy-for-animators", "title": "...", "author": "...", "notes": "docs/research/books/lyons-comedy-for-animators.md", "read": "whole"}],
  "core": ["3 to 9 sentences"],
  "rules": [{
    "id": "V1", "stage": ["plan"], "must": true,
    "do": "One action, 260 characters at most.",
    "why": "...", "when": "...", "not_when": "...",
    "test": {"kind": "measure", "how": "...", "run": ["python", "scripts/x.py", "{file}"]},
    "sources": ["Lyons P3", "Wright P5-P6"], "strength": "consensus", "number_from": "ours (start)"
  }],
  "not_adopted": [{"principle": "Lyons P9", "why": "..."}],
  "conflicts": [{"between": ["Lyons P3", "CLAUDE.md one point of interest"], "resolution": "..."}],
  "hooks": {"watch": ["src/**/scenes/*.tsx"], "ignore": [], "content": null, "checks": [], "deliver": []}
}
```
`strength`: `consensus`, `single`, `user` (the user said it: quote and date in `sources`), `ours` (inferred: say from what). A book only partly read needs `"read": "part: ..."` and `why_part`.

## Version
0.x while building; 1.0 after the back-test; +0.1 for a new or changed rule; +1.0 for a new book that changes the core. Each change of a rule raises it: that makes old ledgers show as out of date and asks agents to read the card again.

## The doc
Write for someone who has never seen the books. The model, then how to use it by stage, decision tables, the rules (generated), a catalog of named patterns with a worked example from the destination each, what goes wrong. If it passes about 350 lines, move the catalog to its own file.

## Back-test table
| Case | Verdict we know | Rules that fire | Rules that stay quiet | What we changed |
Cases are real, with a path or link. At least one the user loved and one the user rejected.
