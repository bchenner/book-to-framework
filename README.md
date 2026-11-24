# book-to-framework

A [Claude Code](https://claude.com/claude-code) skill that turns books into a **working framework** for your project: principles, rules that each carry a test, decision tables and a checklist. Then it applies the framework to the project and installs hooks so later agents actually follow it.

```
/book-to-framework "a UX standard" --for "my web app"
/book-to-framework add ux "a new book"
/book-to-framework apply ux settings-page
```

## Why

Asking an agent to "read these books and make rules" usually gives you a long Markdown file that nobody follows, with chapters skipped, quotes invented, and no link between a rule and its source. This skill makes each of those fail a check:

| Problem | Check |
|---|---|
| Skipped chapters | Every chunk of the book needs a row in the reading ledger |
| Invented claims | Every principle has a short anchor that must be on the page it cites |
| Copied text | Runs of 14 words from the book fail |
| Vague rules | A rule with no test gets cut |
| Ideas dropped in silence | Every principle is used in a rule, or listed as not adopted with a reason |
| Partial audits | Every item of the inventory needs a verdict, and every finding a fix |
| Agents that never read it | A hook refuses the edit until the agent has read the rule card |

## How it works

1. **Brief**: what should be different in the output, for whom, and how you will judge it.
2. **Destination first**: an inventory of what the framework covers, what must not change, and what you loved or rejected before.
3. **Books**: checked for value, then extracted (EPUB, PDF, text; scanned PDFs on Windows).
4. **Read**: one agent per book or part, notes saved after every chunk, checked by script.
5. **Build**: `rules.json` is the source of truth; the doc tables and a short card are generated from it.
6. **Back-test** on real past work.
7. **Hooks**: a read gate, checks after edits, checks at delivery.
8. **Apply**: 100% of the inventory, real before and after.

## Install

```bash
git clone https://github.com/bchenner/book-to-framework ~/.claude/skills/book-to-framework
pip install pymupdf pillow
python ~/.claude/skills/book-to-framework/scripts/selftest.py        # about 20 s; add --ocr on Windows
```

Needs Python 3.10+, Node 18+ (for the hook) and Claude Code. Scanned PDFs are read with the OCR built into Windows; on macOS or Linux run [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) first. Convert `.mobi`, `.azw3` and `.djvu` with Calibre.

**Pick the reader model (optional):** put a `local.json` next to `SKILL.md`, for example `{"reader": {"label": "my choice", "tool": "Agent", "target": {"model": "sonnet"}}}`. Without it, readers run on the session's model.

## The hook

`bookfw.py hooks <project> <id> install` adds one gate to the project's `.claude/settings.json` (existing hooks stay) and runs a 10-case test. A watched file cannot be edited until that session, or that subagent, has read the card. It asks again after a compact and when the framework's version rises. If anything in the gate breaks, the tool runs: it never blocks work by its own fault.

## Your books

Bring your own, legally obtained copies. Extracted text stays in `~/.book-to-framework/library/`, outside every repo. Notes are written in the agent's own words, with anchors of 15 words at most.

## License

MIT
