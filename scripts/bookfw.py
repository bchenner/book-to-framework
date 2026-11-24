#!/usr/bin/env python3
"""Checks and wiring for /book-to-framework. Every command prints what is wrong and exits 1 if anything is.

    bookfw.py init   <project> <id> --title "..." [--doc docs/x.md]     make docs/frameworks/<id>/ with empty files
    bookfw.py read   <slug> <chunk> [part]                              print a chunk of a book, about 2500 words at a time
    bookfw.py notes  <notes.md> --book <slug> [--chunks C01-C05]        check one book's notes against the book text
    bookfw.py check  <project> <id>                                     check rules.json (tests, sources, nothing dropped)
    bookfw.py render <project> <id>                                     write the generated blocks of the doc, and CARD.md
    bookfw.py audit  <project> <id> <target>                            check an apply ledger: 100% of the inventory, each fix shown
    bookfw.py status <project>                                          every framework: version, books, rules, ledgers that are out of date
    bookfw.py hooks  <project> <id> install|uninstall|test
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = Path.home() / ".book-to-framework" / "library"
P_HEAD = re.compile(r"^#{2,4} +(P\d+)\b[.:]? *(.*)$", re.M)
VAGUE = re.compile(r"\b(try to|consider|as appropriate|where possible|when needed|be mindful|feel free|good|nice|better|properly|appropriate(ly)?)\b", re.I)
KINDS = ("machine", "measure", "look")
STRENGTHS = ("consensus", "single", "user", "ours")
problems: list[str] = []
warnings: list[str] = []


def bad(msg):
    problems.append(msg)


def warn(msg):
    warnings.append(msg)


def finish(ok: str) -> int:
    for w in warnings:
        print("warn ", w)
    for p in problems:
        print("FAIL ", p)
    print(f"{len(problems)} problems, {len(warnings)} warnings" if problems else f"OK: {ok}" + (f" ({len(warnings)} warnings)" if warnings else ""))
    return 1 if problems else 0


def jload(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"missing: {p}")
    except json.JSONDecodeError as e:
        sys.exit(f"{p}: not valid JSON: {e}")


def jsave(p: Path, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def fdir(project, fid) -> Path:
    return Path(project) / "docs" / "frameworks" / fid


# ---------------------------------------------------------------- init

BRIEF = """# Brief: {title}

Filled from the user's words and the project. Anything marked ASSUMED was not said by the user.

| Row | Answer |
|---|---|
| Wanted framework | |
| What must be different in the output, as someone could see it | |
| Destination (project, pipeline, page, video, team) and who will apply it | |
| Where it applies, and where it must never apply | |
| What wins over it (user rules, house rules) | |
| What must be preserved (look, mechanics, tone) | |
| Known failures it must catch (the user's own words, with where) | |
| Examples the user loved | |
| How the user will judge it (real page, rendered scene, sheet) | |
| Books | |
| Out of scope | |
"""

DOC = """# {title}

<!-- fw:head:start -->
<!-- fw:head:end -->

## The model

(The idea in one paragraph, in our own words. Then 5 to 9 core principles.)

## How to use it

(Numbered steps, by stage. Decision tables here.)

## Rules

<!-- fw:rules:start -->
<!-- fw:rules:end -->

## Catalog

(Named patterns with a worked example each: what happens, when to use it, how it fails.)

## What goes wrong

(The failure, how to see it, the rule that catches it.)

## Where the books disagree, and what we do

<!-- fw:conflicts:start -->
<!-- fw:conflicts:end -->

## Not adopted

<!-- fw:notadopted:start -->
<!-- fw:notadopted:end -->

## Back-test

(From backtest.md: what each rule caught or missed on real past work.)

## Sources

<!-- fw:sources:start -->
<!-- fw:sources:end -->
"""


def cmd_init(a):
    d = fdir(a.project, a.id)
    if (d / "rules.json").exists():
        sys.exit(f"{d} exists already")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", a.id):
        sys.exit("the id is lowercase words joined by hyphens")
    doc = a.doc or f"docs/{a.id}.md"
    if (Path(a.project) / doc).exists():
        sys.exit(f"{doc} exists already: pass another --doc, or merge into it by hand")
    rules = {
        "id": a.id, "title": a.title, "version": "0.1", "updated": str(datetime.date.today()), "doc": doc,
        "card": f"docs/frameworks/{a.id}/CARD.md", "goal": "", "destination": "", "wins_over_this": ["what the user says now"], "preserve": [],
        "stages": ["plan", "build", "review"], "books": [], "core": [], "rules": [], "not_adopted": [], "conflicts": [],
        "hooks": {"watch": [], "ignore": [], "content": None, "checks": [], "deliver": []},
    }
    jsave(d / "rules.json", rules)
    jsave(d / "inventory.json", {"target": "", "made": "", "how": "", "items": []})
    (d / "brief.md").write_text(BRIEF.format(title=a.title), encoding="utf-8", newline="\n")
    (d / "backtest.md").write_text(f"# Back-test: {a.title}\n\n| Case | Verdict we know | Rules that fire | Rules that stay quiet | What we changed |\n|---|---|---|---|---|\n", encoding="utf-8", newline="\n")
    p = Path(a.project) / doc
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(DOC.format(title=a.title), encoding="utf-8", newline="\n")
    print(f"made {d} and {p}")
    return 0


# ---------------------------------------------------------------- notes

def words_of(s: str) -> list[str]:
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)
    return re.findall(r"[a-z0-9]+", s.lower().replace("’", "").replace("'", ""))


def pages_of(text: str) -> dict[int, str]:
    out, cur = {}, 0
    for ln in text.splitlines():
        m = re.fullmatch(r"\[\[page (\d+)\]\]", ln)
        if m:
            cur = int(m.group(1))
            out[cur] = ""
        elif cur:
            out[cur] += ln + "\n"
    return out


def span(expr: str) -> set[int]:
    out = set()
    for a, b in re.findall(r"(\d+)(?:\s*[-–]\s*(\d+))?", expr):
        lo, hi = int(a), int(b or a)
        if hi - lo < 400:
            out |= set(range(lo, hi + 1))
    return out


def principles(text: str) -> list[tuple[str, str, str]]:
    hs = list(P_HEAD.finditer(text))
    out = []
    for i, h in enumerate(hs):
        end = hs[i + 1].start() if i + 1 < len(hs) else len(text)
        body = text[h.end():end]
        cut = re.search(r"^## ", body, re.M)
        out.append((h.group(1), h.group(2).strip(), body[:cut.start()] if cut else body))
    return out


def field(body: str, name: str) -> str:
    m = re.search(rf"^\s*[-*]?\s*\*\*{name}:\*\*\s*(.+?)(?=\n\s*[-*]?\s*\*\*[A-Z][\w ]*:\*\*|\n#|\n\n|\Z)", body, re.M | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def cmd_read(a):
    lib = Path(a.lib) if a.lib else LIB
    man = jload(lib / a.book / "manifest.json")
    c = next((c for c in man["chunks"] if c["id"] == a.chunk), None) or sys.exit(f"no chunk {a.chunk}: {man['chunks'][0]['id']} to {man['chunks'][-1]['id']}")
    lines = (lib / a.book / "book.txt").read_text(encoding="utf-8").splitlines()[c["lines"][0] - 1:c["lines"][1]]
    parts, cur, n = [], [], 0
    for ln in lines:
        cur.append(ln)
        n += len(ln.split())
        if n >= 2500:
            parts, cur, n = parts + [cur], [], 0
    if cur:
        parts.append(cur)
    if not 1 <= a.part <= len(parts):
        sys.exit(f"{a.chunk} has {len(parts)} parts")
    print(*parts[a.part - 1], sep="\n")
    print(f"--- {a.chunk} part {a.part} of {len(parts)}" + (f"; next: read {a.book} {a.chunk} {a.part + 1}" if a.part < len(parts) else "; end of the chunk: save its ledger row and principles now"))
    return 0


def cmd_notes(a):
    man = jload(LIB / a.book / "manifest.json") if not a.lib else jload(Path(a.lib) / a.book / "manifest.json")
    book = ((Path(a.lib) if a.lib else LIB) / a.book / "book.txt").read_text(encoding="utf-8")
    text = Path(a.notes).read_text(encoding="utf-8")
    pages, scan = pages_of(book), man["mode"] == "scan"
    want = [c for c in man["chunks"]]
    if a.chunks:
        lo, hi = (a.chunks.split("-") + [a.chunks])[:2]
        want = [c for c in want if lo <= c["id"] <= hi]
    # every chunk read, with its own ledger row
    rows = {m.group(1): m.group(0) for m in re.finditer(r"^\|\s*(C\d+|S\d+)\s*\|.*$", text, re.M)}
    for c in want:
        if c["id"] not in rows:
            bad(f"reading ledger has no row for {c['id']} (lines {c['lines'][0]}-{c['lines'][1]})")
        elif len(re.sub(r"[|\s\d-]", "", rows[c["id"]])) < 25:
            bad(f"reading ledger row {c['id']} does not say what is in it")
    if not a.chunks and man["pictures"] >= 12:
        for n in range(1, man["sheets"] + 1):
            if f"S{n:02d}" not in rows:
                bad(f"reading ledger has no row for picture sheet S{n:02d}")
    ps = principles(text)
    if len(ps) < 3:
        bad(f"only {len(ps)} principles found (headings like '### P1. Short rule')")
    ids = [p[0] for p in ps]
    for x in sorted({i for i in ids if ids.count(i) > 1}):
        bad(f"{x} is used twice")
    img_ids = {p["id"] for p in man["pics"]}
    for pid, title, body in ps:
        src, anc = field(body, "Source"), field(body, "Anchor")
        for need in ("Says", "For us", "Test"):
            if len(field(body, need)) < 15:
                bad(f"{pid}: no real **{need}:** line")
        cited = span(re.sub(r"\bimg\b.*", "", src))
        if not src or (not cited and "image" not in anc):
            bad(f"{pid}: **Source:** names no page (m. N)")
            continue
        for n in cited - set(pages):
            bad(f"{pid}: page {n} is not in the book (1-{max(pages)})")
        m = re.search(r"\[\[image (\d+)\]\]", anc)
        if m:
            if m.group(1) not in img_ids:
                bad(f"{pid}: image {m.group(1)} is not in the book")
            continue
        q = words_of(anc)
        if len(q) < 4:
            bad(f"{pid}: **Anchor:** needs 4 to 15 words copied from the cited page, or [[image NNN]]")
            continue
        if len(q) > 15:
            bad(f"{pid}: the anchor is {len(q)} words long (15 at most)")
        near = sorted({n + d for n in cited for d in (-1, 0, 1)} & set(pages))
        hay = [w for n in near for w in words_of(pages[n])]
        if " " + " ".join(q) + " " not in " " + " ".join(hay) + " ":
            best = max((difflib.SequenceMatcher(None, " ".join(q), " ".join(hay[i:i + len(q)])).ratio() for i in range(max(1, len(hay) - len(q) + 1))), default=0)
            if not (scan and best >= 0.82):
                bad(f"{pid}: the anchor is not on page {src} (closest match {best:.0%})")
    # own words: no long run copied from the book
    body = re.sub(r"^.*\*\*Anchor:\*\*.*$", "", text, flags=re.M)
    bw, nw = words_of(book), words_of(body)
    k = 14
    grams = {tuple(bw[i:i + k]) for i in range(len(bw) - k + 1)}
    i = 0
    while i <= len(nw) - k:
        if tuple(nw[i:i + k]) in grams:
            bad(f"copied from the book (write it in our own words): \"{' '.join(nw[i:i + k])} ...\"")
            i += k
        else:
            i += 1
    for h in ("Reading ledger", "core model", "Principles", "does not transfer", "Conflicts"):
        if not a.chunks and not re.search(rf"^## .*{h}", text, re.M | re.I):
            bad(f"section missing: '{h}'")
    return finish(f"{len(ps)} principles, {len(want)} chunks accounted for")


# ---------------------------------------------------------------- check and render

def load(project, fid):
    return jload(fdir(project, fid) / "rules.json")


def all_principles(project, fw):
    """{"Lyons P3": title} for every book of the framework."""
    out = {}
    for b in fw["books"]:
        p = Path(project) / b["notes"]
        if not p.exists():
            bad(f"book {b['key']}: notes file {b['notes']} is missing")
            continue
        for pid, title, _ in principles(p.read_text(encoding="utf-8")):
            out[f"{b['key']} {pid}"] = title
    return out


def ranges(src: str) -> list[str]:
    """'Lyons P3-P5' or 'Lyons P3, P5' -> single ids."""
    m = re.match(r"^(.+?) (P\d.*)$", src)
    if not m:
        return [src]
    out = []
    for part in re.split(r"\s*,\s*", m.group(2)):
        r = re.fullmatch(r"P(\d+)\s*[-–]\s*P?(\d+)", part)
        out += [f"{m.group(1)} P{n}" for n in range(int(r.group(1)), int(r.group(2)) + 1)] if r else [f"{m.group(1)} {part}"]
    return out


def run_check(project, fid):
    fw = load(project, fid)
    P = Path(project)
    for k in ("goal", "destination"):
        if len(fw.get(k, "")) < 15:
            bad(f"'{k}' is empty")
    if not 3 <= len(fw["core"]) <= 9:
        bad(f"{len(fw['core'])} core principles (3 to 9)")
    if not fw["preserve"]:
        bad("'preserve' is empty: say what this framework must not change")
    for b in fw["books"]:
        if b.get("read", "") != "whole" and not b.get("why_part"):
            bad(f"book {b['key']}: read is not 'whole' and there is no 'why_part'")
    known = all_principles(project, fw)
    used, ids = set(), []
    for r in fw["rules"]:
        rid = r.get("id", "?")
        ids.append(rid)
        do = r.get("do", "")
        if not 12 <= len(do) <= 260:
            bad(f"{rid}: 'do' is {len(do)} characters (12 to 260)")
        if VAGUE.search(do):
            warn(f"{rid}: vague word '{VAGUE.search(do).group(0)}' in 'do'")
        if len(r.get("why", "")) < 15:
            bad(f"{rid}: no 'why'")
        t = r.get("test", {})
        if t.get("kind") not in KINDS:
            bad(f"{rid}: test.kind must be one of {', '.join(KINDS)}. A rule with no test gets cut")
        if len(t.get("how", "")) < 15:
            bad(f"{rid}: test.how is empty. A rule with no test gets cut")
        if t.get("kind") == "machine" and not t.get("run"):
            bad(f"{rid}: a machine test needs 'run'")
        st = r.get("strength")
        if st not in STRENGTHS:
            bad(f"{rid}: strength must be one of {', '.join(STRENGTHS)}")
        src = [x for s in r.get("sources", []) for x in ranges(s)]
        if not src:
            bad(f"{rid}: no source")
        for s in src:
            if re.search(r" P\d+$", s):
                used.add(s)
                if s not in known:
                    bad(f"{rid}: source '{s}' is in no notes file")
        keys = {s.rsplit(" ", 1)[0] for s in src if s in known}
        if st == "consensus" and len(keys) < 2:
            bad(f"{rid}: 'consensus' needs 2 books or more, it has {len(keys)}")
        if not r.get("stage") or set(r["stage"]) - set(fw["stages"]):
            bad(f"{rid}: stage must be from {fw['stages']}")
        if re.search(r"\d", do) and not r.get("number_from"):
            bad(f"{rid}: it holds a number: set number_from to 'book', 'measured', 'user' or 'ours (start)'")
    for x in sorted({i for i in ids if ids.count(i) > 1}):
        bad(f"rule id {x} is used twice")
    if not fw["rules"]:
        bad("no rules")
    for n in fw["not_adopted"]:
        if len(n.get("why", "")) < 10:
            bad(f"not adopted {n.get('principle')}: no reason")
        for s in ranges(n.get("principle", "")):
            used.add(s)
            if s not in known:
                bad(f"not adopted: '{s}' is in no notes file")
    for c in fw["conflicts"]:
        if len(c.get("resolution", "")) < 15:
            bad(f"conflict {c.get('between')}: no resolution")
        used |= {x for s in c.get("between", []) for x in ranges(s)}
    for s in known:
        if s not in used:
            bad(f"dropped in silence: {s} ({known[s][:60]}). Use it in a rule or list it in not_adopted")
    n = len(fw["rules"]) or 1
    hard = sum(1 for r in fw["rules"] if r.get("test", {}).get("kind") in ("machine", "measure"))
    must = sum(1 for r in fw["rules"] if r.get("must"))
    if hard / n < 0.4:
        warn(f"only {hard} of {n} rules can be measured or run; the rest depend on someone looking")
    if must > 15:
        bad(f"{must} rules are 'must' (15 at most: more than that and nobody holds them in mind)")
    if n > 45:
        warn(f"{n} rules: merge or cut")
    if not any(r.get("test", {}).get("kind") == "machine" for r in fw["rules"]):
        warn("no machine test: nothing stops a builder who forgets")
    bt = fdir(project, fid) / "backtest.md"
    if not bt.exists() or len([x for x in bt.read_text(encoding="utf-8").splitlines() if x.startswith("|")]) < 5:
        bad("backtest.md needs 3 real past cases or more")
    doc = P / fw["doc"]
    if doc.exists():
        t = doc.read_text(encoding="utf-8")
        for m in re.finditer(r"^\([A-Z].*\)$", t, re.M):
            bad(f"{fw['doc']}: template text is still there: {m.group(0)[:60]}")
        for m in set(re.findall(r"\b[A-Z]{1,3}\d{1,3}\b", t)) & set():
            pass
    else:
        bad(f"{fw['doc']} is missing")
    card = P / fw["card"]
    if card.exists():
        w = len(card.read_text(encoding="utf-8").split())
        if w > 1500:
            bad(f"CARD.md is {w} words (1500 at most): mark fewer rules 'must' or shorten 'do'")
        if f"v{fw['version']} " not in card.read_text(encoding="utf-8"):
            bad("CARD.md is from another version: run render")
    else:
        bad("CARD.md is missing: run render")
    return fw


def cmd_check(a):
    fw = run_check(a.project, a.id)
    return finish(f"{fw['title']} v{fw['version']}: {len(fw['rules'])} rules, {len(fw['books'])} books")


def block(text, name, new):
    pat = re.compile(rf"(<!-- fw:{name}:start -->).*?(<!-- fw:{name}:end -->)", re.S)
    if not pat.search(text):
        bad(f"the doc has no fw:{name} block")
        return text
    return pat.sub(lambda m: f"{m.group(1)}\n{new.rstrip()}\n{m.group(2)}", text)


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def cmd_render(a):
    fw = load(a.project, a.id)
    P = Path(a.project)
    doc = P / fw["doc"]
    if not doc.exists():
        sys.exit(f"missing: {doc}")
    t = doc.read_text(encoding="utf-8")
    head = (f"Version {fw['version']}, {fw['updated']}. Generated blocks come from `docs/frameworks/{fw['id']}/rules.json`: change that file, then run `bookfw.py render`.\n\n"
            f"- **Goal:** {fw['goal']}\n- **Applies to:** {fw['destination']}\n- **What wins over this:** {'; '.join(fw['wins_over_this'])}\n"
            f"- **Must not change:** {'; '.join(fw['preserve'])}\n- **Short version (read before work):** `{fw['card']}`")
    t = block(t, "head", head)
    out = []
    for st in fw["stages"]:
        rs = [r for r in fw["rules"] if st == (r.get("stage") or [""])[0]]
        if not rs:
            continue
        out.append(f"### {st.capitalize()}\n\n| Rule | Do | Why | Test | From |\n|---|---|---|---|---|")
        for r in rs:
            lim = "".join(f" *{k}:* {r[f]}" for k, f in (("When", "when"), ("Not when", "not_when")) if r.get(f))
            num = f" ({r['number_from']})" if r.get("number_from") else ""
            out.append(f"| **{r['id']}**{' must' if r.get('must') else ''} | {cell(r['do'])}{num}{cell(lim)} | {cell(r['why'])} | *{r['test']['kind']}:* {cell(r['test']['how'])} | {cell('; '.join(r['sources']))} ({r['strength']}) |")
        out.append("")
    t = block(t, "rules", "\n".join(out))
    t = block(t, "conflicts", "| Between | Resolution |\n|---|---|\n" + "\n".join(f"| {cell(' / '.join(c['between']))} | {cell(c['resolution'])} |" for c in fw["conflicts"]) if fw["conflicts"] else "None found.")
    t = block(t, "notadopted", "\n".join(f"- **{n['principle']}:** {n['why']}" for n in fw["not_adopted"]) or "Nothing was left out.")
    t = block(t, "sources", "\n".join(f"- **{b['key']}:** {b['author']}, *{b['title']}* (read: {b.get('read')}). Notes: `{b['notes']}`" for b in fw["books"]))
    doc.write_text(t, encoding="utf-8", newline="\n")
    must = [r for r in fw["rules"] if r.get("must")]
    rest = [r for r in fw["rules"] if not r.get("must")]
    c = [f"# {fw['title']}: card v{fw['version']} ", "", f"Read all of this before the work it covers. Full text: `{fw['doc']}`.", "",
         f"**Goal:** {fw['goal']}", f"**Wins over this:** {'; '.join(fw['wins_over_this'])}", f"**Must not change:** {'; '.join(fw['preserve'])}", "",
         "## Core", ""] + [f"{i}. {x}" for i, x in enumerate(fw["core"], 1)] + ["", "## Must", ""]
    c += [f"- **{r['id']}** ({', '.join(r['stage'])}) {r['do']}" + (f" *Not when:* {r['not_when']}" if r.get("not_when") else "") + f" **Test:** {r['test']['how']}" for r in must]
    c += ["", "## Also", ""] + [f"- **{r['id']}** {r['do']}" for r in rest]
    c += ["", "## Before you call it done", "", "Go through each Must by its test and name every one the work does not meet. Judge the whole result too: rules kept one by one do not make it good.",
          "", f"<!-- card-end:{fw['id']} v{fw['version']} -->"]
    (P / fw["card"]).write_text("\n".join(c) + "\n", encoding="utf-8", newline="\n")
    print(f"card: {len(' '.join(c).split())} words, {len(must)} must, {len(rest)} also")
    return finish(f"rendered {fw['doc']} and {fw['card']}")


# ---------------------------------------------------------------- audit

def check_ledger(project, fid, target):
    fw, d = load(project, fid), fdir(project, fid)
    led = jload(d / "apply" / f"{target}.json")
    inv = jload(d / led.get("inventory", "inventory.json"))
    P = Path(project)
    items = {i["id"]: i for i in inv["items"]}
    if len(items) != len(inv["items"]):
        bad("the inventory uses an id twice")
    if not items:
        bad("the inventory is empty")
    if len(inv.get("how", "")) < 20:
        bad("inventory 'how' must say how the list was made (so someone can check nothing is left out)")
    if led.get("version") != fw["version"]:
        bad(f"the ledger was made with v{led.get('version')}, the framework is v{fw['version']}: audit the new rules too")
    rids, seen = {r["id"] for r in fw["rules"]}, set()
    n = {"ok": 0, "fix": 0, "na": 0}
    open_ = 0
    for r in led["rows"]:
        i = r.get("item", "?")
        if i not in items:
            bad(f"{i} is not in the inventory")
            continue
        seen.add(i)
        v = r.get("verdict")
        if v not in n:
            bad(f"{i}: verdict must be ok, fix or na")
            continue
        n[v] += 1
        for x in set(r.get("rules", [])) - rids:
            bad(f"{i}: rule {x} does not exist")
        if v != "na" and not r.get("rules"):
            bad(f"{i}: names no rule it was checked against")
        if v == "na" and len(r.get("note", "")) < 10:
            bad(f"{i}: 'na' needs a reason in 'note'")
        if v == "fix":
            for k in ("finding", "fix"):
                if len(r.get(k, "")) < 12:
                    bad(f"{i}: a finding with no '{k}' is half an audit")
            if items[i].get("load_bearing") and not r.get("preserves"):
                bad(f"{i}: load-bearing: say in 'preserves' what still works after the fix")
            s = r.get("status")
            if s not in ("done", "proposed", "blocked"):
                bad(f"{i}: status must be done, proposed or blocked")
            if s != "done":
                open_ += 1
            if s == "blocked" and len(r.get("note", "")) < 10:
                bad(f"{i}: blocked by what?")
            if s == "done":
                if len(r.get("state", "")) < 8:
                    bad(f"{i}: 'state' must say the one state both pictures show (same data, same open panels, same frame)")
                for k in ("before", "after"):
                    if not r.get(k) or not (P / r[k]).exists():
                        bad(f"{i}: no real '{k}' file ({r.get(k)})")
                if r.get("before") and r.get("before") == r.get("after"):
                    bad(f"{i}: before and after are the same file")
    for i in items:
        if i not in seen:
            bad(f"not looked at: {i} {items[i].get('where', '')} {items[i].get('what', '')}"[:140])
    return f"{len(seen)} of {len(items)} items: {n['ok']} ok, {n['fix']} with a fix ({open_} still open), {n['na']} not applicable"


def cmd_audit(a):
    return finish(check_ledger(a.project, a.id, a.target))


def cmd_status(a):
    root = Path(a.project) / "docs" / "frameworks"
    reg = Path(a.project) / ".claude" / "frameworks.json"
    on = {x["rules"] for x in json.loads(reg.read_text(encoding="utf-8"))["frameworks"] if x.get("enabled", True)} if reg.exists() else set()
    for r in sorted(root.glob("*/rules.json")):
        fw = jload(r)
        rel = r.relative_to(a.project).as_posix()
        print(f"{fw['id']} v{fw['version']} ({fw['updated']}): {len(fw['rules'])} rules, books {', '.join(b['key'] for b in fw['books']) or 'none'}, hooks {'on' if rel in on else 'off'}")
        for led in sorted((r.parent / "apply").glob("*.json")):
            d = jload(led)
            print(f"  {led.stem}: {len(d['rows'])} rows, v{d.get('version')}" + ("" if d.get("version") == fw["version"] else "  OUT OF DATE"))
    return 0


# ---------------------------------------------------------------- hooks

EVENTS = {"PreToolUse": "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell", "PostToolUse": "Read|Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell", "SessionStart": "clear|compact"}
MARK = "framework-gate.mjs"


def cmd_hooks(a):
    P = Path(a.project)
    rel = f"docs/frameworks/{a.id}/rules.json"
    reg_p, set_p, gate = P / ".claude" / "frameworks.json", P / ".claude" / "settings.json", P / ".claude" / "hooks" / MARK
    reg = jload(reg_p) if reg_p.exists() else {"version": 1, "frameworks": []}
    if a.action == "test":
        return gate_test(P, a.id)
    if a.action == "install":
        fw = run_check(a.project, a.id)
        if not fw["hooks"].get("watch"):
            bad("hooks.watch is empty: which files does this framework cover?")
        if problems:
            return finish("")
        gate.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / MARK, gate)
        reg["frameworks"] = [x for x in reg["frameworks"] if x["rules"] != rel] + [{"rules": rel, "enabled": True}]
        jsave(reg_p, reg)
        st = jload(set_p) if set_p.exists() else {}
        hooks = st.setdefault("hooks", {})
        changed = False
        for ev, matcher in EVENTS.items():
            lst = hooks.setdefault(ev, [])
            if not any(MARK in h.get("command", "") for g in lst for h in g.get("hooks", [])):
                lst.append({"matcher": matcher, "hooks": [{"type": "command", "command": f'node "$CLAUDE_PROJECT_DIR/.claude/hooks/{MARK}"', "timeout": 60}]})
                changed = True
        if changed:
            if set_p.exists():
                bk = Path(tempfile.gettempdir()) / f"settings-{P.resolve().name}-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"
                shutil.copyfile(set_p, bk)
                print("old settings kept at", bk)
            jsave(set_p, st)
        print(f"installed: {gate.relative_to(P)}, {reg_p.relative_to(P)}, {set_p.relative_to(P)}")
        return gate_test(P, a.id)
    reg["frameworks"] = [x for x in reg["frameworks"] if x["rules"] != rel]
    jsave(reg_p, reg)
    if not reg["frameworks"] and set_p.exists():
        st = jload(set_p)
        for ev in list(st.get("hooks", {})):
            st["hooks"][ev] = [g for g in st["hooks"][ev] if not any(MARK in h.get("command", "") for h in g.get("hooks", []))]
            if not st["hooks"][ev]:
                del st["hooks"][ev]
        jsave(set_p, st)
    print(f"uninstalled {a.id} (its docs stay)")
    return 0


def gate_test(P: Path, fid: str) -> int:
    """Feeds the installed gate the payloads Claude Code sends, for this project's real watch list."""
    P = P.resolve()
    fw = load(P, fid)
    gate = P / ".claude" / "hooks" / MARK
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "FRAMEWORK_GATE_STATE": td, "CLAUDE_PROJECT_DIR": str(P), "FRAMEWORK_GATE_ONLY": fid}

        def send(**kw):
            kw = {"session_id": "t1", "cwd": str(P), **kw}
            r = subprocess.run(["node", str(gate)], input=json.dumps(kw), capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
            if r.returncode:
                bad(f"the gate exited {r.returncode}: {r.stderr[:200]}")
            return json.loads(r.stdout) if r.stdout.strip() else {}

        def denied(o):
            return o.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

        pat = fw["hooks"]["watch"][0]
        name = re.sub(r"\*\*/", "a/", pat).replace("**", "a/b.txt").replace("*", "x")
        name = re.sub(r"\{([^,}]*)[^}]*\}", r"\1", name)
        f = str(P / name)
        text = fw["hooks"].get("test_content") or ("x" if not fw["hooks"].get("content") else "")
        edit = {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": f, "content": text}}
        other = {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": str(P / "zz-not-watched" / "zz.unrelated"), "content": "x"}}
        card = str(P / fw["card"])
        read = {"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": card}, "tool_response": {"file": {"content": Path(card).read_text(encoding="utf-8")}}}
        cases = [
            ("a watched edit is refused before the card is read", denied(send(**edit)), True),
            ("a file outside the watch list passes", denied(send(**other)), False),
            ("a shell write to a watched file is refused", denied(send(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": f"cat > '{name}' <<'X'\n{text}\nX"})), True),
            ("reading a watched file in the shell passes", denied(send(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": f"grep -n foo {name}"})), False),
            ("half the card does not count", (send(**{**read, "tool_input": {"file_path": card, "limit": 5}, "tool_response": {"file": {"content": "# half"}}}), denied(send(**edit)))[1], True),
            ("after the card is read the edit passes", (send(**read), denied(send(**edit)))[1], False),
            ("a subagent must read it for itself", denied(send(agent_id="sub1", **edit)), True),
            ("another session must read it for itself", denied(send(**{**edit, "session_id": "t2"})), True),
            ("after compact it must be read again", (send(hook_event_name="SessionStart", source="compact"), denied(send(**edit)))[1], True),
            ("a broken payload never blocks", denied(send(hook_event_name="PreToolUse", tool_name="Write", tool_input=None)), False),
        ]
        for label, got, want in cases:
            print(("pass  " if got == want else "FAIL  ") + label)
            if got != want:
                bad(label)
    return finish(f"gate works for {fid} ({len(cases)} cases)")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("init"); s.add_argument("project"); s.add_argument("id"); s.add_argument("--title", required=True); s.add_argument("--doc"); s.set_defaults(fn=cmd_init)
    s = sp.add_parser("read"); s.add_argument("book"); s.add_argument("chunk"); s.add_argument("part", nargs="?", type=int, default=1); s.add_argument("--lib"); s.set_defaults(fn=cmd_read)
    s = sp.add_parser("notes"); s.add_argument("notes"); s.add_argument("--book", required=True); s.add_argument("--chunks"); s.add_argument("--lib"); s.set_defaults(fn=cmd_notes)
    for n, fn in (("check", cmd_check), ("render", cmd_render)):
        s = sp.add_parser(n); s.add_argument("project"); s.add_argument("id"); s.set_defaults(fn=fn)
    s = sp.add_parser("audit"); s.add_argument("project"); s.add_argument("id"); s.add_argument("target"); s.set_defaults(fn=cmd_audit)
    s = sp.add_parser("status"); s.add_argument("project"); s.set_defaults(fn=cmd_status)
    s = sp.add_parser("hooks"); s.add_argument("project"); s.add_argument("id"); s.add_argument("action", choices=["install", "uninstall", "test"]); s.set_defaults(fn=cmd_hooks)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
