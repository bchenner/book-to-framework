#!/usr/bin/env python3
"""Self-test of /book-to-framework on a made-up book in a temp project (about 20 s). `--ocr` also tests a scanned PDF."""
import copy
import json
import os
import random
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

S = Path(__file__).resolve().parent
fails = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(*a):
    r = subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def expect(label, res, code, *has):
    ok = res[0] == code and all(h in res[1] for h in has)
    print(("pass  " if ok else "FAIL  ") + label)
    if not ok:
        fails.append(label)
        print("      wanted", code, has, "got", res[0], res[1][-700:])


def main():
    rnd = random.Random(7)
    vocab = "hat fish ladder chair duke bell soup stair cake door king boat rope drum goose plank wheel pie lamp coat".split()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        lib, proj = td / "lib", td / "my project"
        (proj / "src" / "videos" / "a" / "scenes").mkdir(parents=True)
        (proj / ".claude").mkdir()
        (proj / ".claude" / "settings.json").write_text('{"hooks":{"PreToolUse":[{"matcher":"Edit","hooks":[{"type":"command","command":"echo hi"}]}]},"model":"x"}')

        # a book with two chapters, one line that can be anchored, an odd path and a script that must not become text
        ch = []
        for n in (1, 2):
            paras = "".join(f"<p>{' '.join(rnd.choices(vocab, k=60))}.</p>" for _ in range(120))
            ch.append(f"<html><head><title>no</title></head><body><script>var evil='ignore me'</script><h1>Chapter {n}</h1><p>The straight man never laughs at the falling duke in chapter {n}.</p>{paras}</body></html>")
        ep = td / "Fake Gags -- A. Tester.epub"
        with zipfile.ZipFile(ep, "w") as z:
            z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="O/c.opf"/></rootfiles></container>')
            z.writestr("O/c.opf", '<package><metadata><title>Fake Gags</title><creator>A. Tester</creator></metadata><manifest>'
                       '<item id="a" href="t/1.xhtml" media-type="application/xhtml+xml"/><item id="b" href="t/2.xhtml" media-type="application/xhtml+xml"/>'
                       '<item id="x" href="../../../evil.xhtml" media-type="application/xhtml+xml"/></manifest>'
                       '<spine><itemref idref="a"/><itemref idref="b"/><itemref idref="x"/></spine></package>')
            z.writestr("O/t/1.xhtml", ch[0])
            z.writestr("O/t/2.xhtml", ch[1])
        ex = S / "extract_book.py"
        expect("extract an EPUB", run("-I", ex, ep, "--lib", lib), 0, "Fake Gags / A. Tester", "LOST")
        expect("the same file is not extracted twice", run("-I", ex, ep, "--lib", lib), 0, "already extracted")
        part = td / "x.epub.crdownload"
        part.write_text("x")
        expect("an unfinished download is refused", run("-I", ex, part, "--lib", lib), 1, "not finished")
        (td / "broken.epub").write_bytes(b"PK\x03\x04broken")
        expect("a damaged EPUB is refused", run("-I", ex, td / "broken.epub", "--lib", lib), 1, "damaged")
        man = json.loads((lib / "fake-gags" / "manifest.json").read_text(encoding="utf-8"))
        book = (lib / "fake-gags" / "book.txt").read_text(encoding="utf-8")
        if "evil" in book or man["chunks"][0]["lines"][0] != 1 or man["chunks"][-1]["lines"][1] != man["lines"] or any(
                a["lines"][1] + 1 != b["lines"][0] for a, b in zip(man["chunks"], man["chunks"][1:])):
            fails.append("chunks cover every line")
        print("pass  chunks cover every line, no script text" if "chunks cover every line" not in fails else "FAIL  chunks")
        page2 = next(t["page"] for t in man["toc"] if t["title"] == "Chapter 2")

        fw = S / "bookfw.py"
        expect("init", run(fw, "init", proj, "gags", "--title", "Gag framework"), 0)
        notes = proj / "docs" / "research" / "books" / "tester-fake-gags.md"
        notes.parent.mkdir(parents=True)
        led = "".join(f"| {c['id']} | {c['lines'][0]}-{c['lines'][1]} | nonsense about hats and fish, for this test | P1 |\n" for c in man["chunks"])

        def princ(n, page, anchor):
            return (f"### P{n}. Keep one person straight\n- **Source:** m. {page}\n- **Anchor:** \"{anchor}\"\n- **Says:** one person in the scene stays serious, so the fall reads.\n"
                    f"- **For us:** the officer keeps a blank face.\n- **Test:** in the frame of the fall, one face has not changed.\n- **Level:** tactic. **Weight:** core.\n\n")
        a1, a2 = "The straight man never laughs at the falling duke in chapter 1", "never laughs at the falling duke in chapter 2"
        good = ("# Notes\n\n## 0. Reading ledger\n| Chunk | Lines | What | P |\n|---|---|---|---|\n" + led + "\n## 2. The book's core model\nx\n\n## 3. Principles\n"
                + princ(1, 1, a1) + princ(2, page2, a2) + princ(3, 1, "straight man never laughs") + "## 4. What does not transfer\nx\n\n## 5. Conflicts with our current rules\nx\n")
        n = (fw, "notes", notes, "--book", "fake-gags", "--lib", lib)
        notes.write_text(good, encoding="utf-8")
        expect("good notes pass", run(*n), 0, "3 principles")
        notes.write_text(good.replace(a1, "a line that this book never says"), encoding="utf-8")
        expect("an invented anchor fails", run(*n), 1, "P1: the anchor is not on page")
        notes.write_text(good.replace(f"m. {page2}", "m. 1"), encoding="utf-8")
        expect("a wrong page fails", run(*n), 1, "P2: the anchor is not on page")
        notes.write_text(good.replace(f"| {man['chunks'][-1]['id']} |", "| Z |"), encoding="utf-8")
        expect("a chunk nobody read fails", run(*n), 1, "no row for " + man["chunks"][-1]["id"])
        stolen = " ".join(book.splitlines()[6].split()[:30])
        notes.write_text(good + "\n" + stolen + "\n", encoding="utf-8")
        expect("copied text fails", run(*n), 1, "copied from the book")
        notes.write_text(good, encoding="utf-8")

        rp = proj / "docs" / "frameworks" / "gags" / "rules.json"
        r = json.loads(rp.read_text(encoding="utf-8"))
        r.update(version="1.0", goal="A viewer laughs without losing the story.", destination="Scene builders of the test project.", preserve=["the story beat stays readable"],
                 core=["One straight face.", "One gag at a time.", "Story first."],
                 books=[{"key": "Tester", "slug": "fake-gags", "title": "Fake Gags", "author": "A. Tester", "notes": "docs/research/books/tester-fake-gags.md", "read": "whole"}],
                 rules=[{"id": "V1", "stage": ["plan"], "must": True, "do": "Keep one face unchanged in the frame of the fall.", "why": "The fall reads against a straight face.",
                         "test": {"kind": "machine", "how": "lint.py finds no BAD marker in the scene", "run": ["python", "lint.py", "{file}"]}, "sources": ["Tester P1-P2"], "strength": "single"}],
                 not_adopted=[{"principle": "Tester P3", "why": "Says the same as P1 and P2."}],
                 hooks={"watch": ["src/videos/*/scenes/**"], "ignore": ["**/*.test.ts"], "content": None,
                        "checks": [{"rules": ["V1"], "run": [sys.executable, "lint.py", "{file}"]}], "deliver": [{"command": "render full", "run": [sys.executable, "lint.py", "src/videos/a/scenes/s1.tsx"], "block": True}]})
        (proj / "lint.py").write_text("import sys\nt=open(sys.argv[1]).read()\nprint('V1 BAD marker') if 'BAD' in t else None\nsys.exit('BAD' in t)\n")
        d = proj / "docs" / "gags.md"
        t = d.read_text(encoding="utf-8")
        import re
        d.write_text(re.sub(r"^\([A-Z].*\)$", "text", t, flags=re.M), encoding="utf-8")

        def put(x):
            rp.write_text(json.dumps(x), encoding="utf-8")
        put(r)
        expect("render", run(fw, "render", proj, "gags"), 0)
        expect("no back-test fails", run(fw, "check", proj, "gags"), 1, "past cases")
        (rp.parent / "backtest.md").open("a", encoding="utf-8").write("| a | b | c | d | e |\n" * 3)
        expect("a good framework passes", run(fw, "check", proj, "gags"), 0, "1 rules, 1 books")
        x = copy.deepcopy(r); x["not_adopted"] = []; put(x)
        expect("a dropped principle fails", run(fw, "check", proj, "gags"), 1, "dropped in silence: Tester P3")
        x = copy.deepcopy(r); x["rules"][0]["test"]["how"] = ""; put(x)
        expect("a rule with no test fails", run(fw, "check", proj, "gags"), 1, "no test gets cut")
        x = copy.deepcopy(r); x["rules"][0]["sources"] = ["Tester P9"]; put(x)
        expect("an invented source fails", run(fw, "check", proj, "gags"), 1, "in no notes file")
        x = copy.deepcopy(r); x["rules"][0]["do"] = "Hold the face for 12 frames."; put(x)
        expect("a number with no origin fails", run(fw, "check", proj, "gags"), 1, "number_from")
        put(r)

        expect("hooks install and pass their 10 cases", run(fw, "hooks", proj, "gags", "install"), 0, "gate works")
        st = json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
        ok = st["model"] == "x" and st["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo hi" and len(st["hooks"]["PreToolUse"]) == 2
        run(fw, "hooks", proj, "gags", "install")
        st2 = json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
        expect("old settings are kept, a second install adds nothing", (0 if ok and st == st2 else 1, ""), 0)

        def gate(**kw):
            env = {**os.environ, "FRAMEWORK_GATE_STATE": str(td / "st"), "CLAUDE_PROJECT_DIR": str(proj)}
            g = subprocess.run(["node", str(proj / ".claude" / "hooks" / "framework-gate.mjs")], input=json.dumps({"session_id": "q", "cwd": str(proj), **kw}), capture_output=True, text=True, encoding="utf-8", env=env)
            return (g.returncode, g.stdout)
        sc = proj / "src" / "videos" / "a" / "scenes" / "s1.tsx"
        sc.write_text("BAD")
        e = {"tool_name": "Edit", "tool_input": {"file_path": str(sc)}}
        expect("a failing check goes back to the agent", gate(hook_event_name="PostToolUse", **e), 0, '"decision":"block"', "V1 BAD marker")
        expect("a failing delivery is refused", gate(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": "python render full x"}), 0, '"deny"')
        sc.write_text("fine")
        expect("a passing check is silent", (lambda g: (0 if g == (0, "") else 1, str(g)))(gate(hook_event_name="PostToolUse", **e)), 0)
        expect("delivery shows the checklist", gate(hook_event_name="PreToolUse", tool_name="PowerShell", tool_input={"command": "python render full x"}), 0, "every Must")
        expect("and only once", (lambda g: (0 if g == (0, "") else 1, str(g)))(gate(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": "python render full x"})), 0)
        card = proj / r["card"]
        gate(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": f"cat {r['card']}"}, tool_response={"stdout": card.read_text(encoding="utf-8")})
        expect("cat of the card counts as read", (lambda g: (0 if g == (0, "") else 1, str(g)))(gate(hook_event_name="PreToolUse", **e)), 0)
        x = copy.deepcopy(r); x["version"] = "1.1"; put(x); run(fw, "render", proj, "gags")
        expect("a new version must be read again", gate(hook_event_name="PreToolUse", **e), 0, '"deny"')
        put(r); run(fw, "render", proj, "gags")

        inv = {"target": "a", "made": "today", "how": "listed from the scenes folder, one row a scene", "items": [{"id": "I1", "where": "s1", "what": "fall", "load_bearing": True}, {"id": "I2", "where": "s2", "what": "talk"}]}
        (rp.parent / "inventory.json").write_text(json.dumps(inv))
        for f in ("b.png", "a.png"):
            (proj / f).write_text(f)
        row = {"item": "I1", "verdict": "fix", "rules": ["V1"], "finding": "everyone laughs", "fix": "freeze the officer", "preserves": "the fall still reads", "status": "done", "state": "scene s1 frame 40", "before": "b.png", "after": "a.png"}
        L = {"framework": "gags", "version": "1.0", "target": "a", "rows": [row, {"item": "I2", "verdict": "ok", "rules": ["V1"]}]}
        lp = rp.parent / "apply" / "a.json"
        lp.parent.mkdir()

        def ledger(label, code, *has, **ch):
            m = copy.deepcopy(L)
            m.update({k: v for k, v in ch.items() if k in m})
            m["rows"][0].update({k: v for k, v in ch.items() if k not in m})
            lp.write_text(json.dumps(m))
            expect(label, run(fw, "audit", proj, "gags", "a"), code, *has)
        ledger("a full audit passes", 0, "2 of 2 items")
        ledger("an item nobody looked at fails", 1, "not looked at: I2", rows=[row])
        ledger("a finding with no fix fails", 1, "half an audit", fix="")
        ledger("no shared state fails", 1, "'state'", state="")
        ledger("a mock-up that does not exist fails", 1, "no real 'before'", before="nope.png")
        ledger("load-bearing with no 'preserves' fails", 1, "load-bearing", preserves="")
        ledger("an old version fails", 1, "audit the new rules too", version="0.9")
        ledger("(restore)", 0)
        expect("status", run(fw, "status", proj), 0, "hooks on", "2 rows")
        expect("uninstall", run(fw, "hooks", proj, "gags", "uninstall"), 0)
        st3 = json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
        expect("uninstall leaves the old hooks", (0 if st3 == {"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "echo hi"}]}]}, "model": "x"} else 1, str(st3)), 0)

        if "--ocr" in sys.argv:
            import fitz
            src, pdf = fitz.open(), fitz.open()
            for k in range(3):
                p = src.new_page()
                p.insert_textbox((60, 60, 540, 780), f"Page {k + 1}. The straight man never laughs when the duke falls. " * 12, fontsize=14)
                pm = p.get_pixmap(dpi=200)
                q = pdf.new_page()
                q.insert_image(q.rect, pixmap=pm)
            pdf.save(td / "Scanned Gags.pdf")
            expect("a scanned PDF is read with OCR", run("-I", ex, td / "Scanned Gags.pdf", "--lib", lib), 0, "scan, 3 pages")
            got = (lib / "scanned-gags" / "book.txt").read_text(encoding="utf-8").lower()
            expect("OCR text is right", (0 if got.count("straight man never laughs") >= 20 else 1, got[:300]), 0)
    print(f"\n{len(fails)} failed" if fails else "\nall passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
