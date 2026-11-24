# What went wrong before, and what now stops it

Collected from earlier book-to-framework projects (a UX standard from 6 books, an animation standard from 12, a script standard from 7). Each step of the skill exists because of one of these.

| What happened | What stops it now |
|---|---|
| The book list came first and was checked only later: repeats and a misfit | Step 3 verifies before reading |
| A history book was listed as a craft book | Step 3 sorts craft from history |
| Unfinished downloads and unreadable formats slipped in | The extractor refuses them |
| "Read end to end", but some chapters were never assigned | Chunks cover every line; `notes` fails on a missing ledger row |
| Notes were saved in an agent's private folder, or not at all, so no rule could be traced | Notes live in the project; every rule names principles that must exist |
| Readers went silent and stalled for hours | One book or part per reader, `bookfw.py read` prints one part at a time, notes saved after every chunk, a fresh reader starts at the first open chunk |
| The framework was written without knowing the product: it felt like a step backwards | Step 2 comes before the rules |
| It flattened things that mattered, and the look changed | `load_bearing`, `preserve`, and `preserves` on each fix |
| The "before" was a mock-up, not the real thing | Real captures only, on the device the user will judge on |
| Before and after showed different states | `state` is required, one state for both |
| The user could not tell which part they were looking at | Say where the picture is from and what to look at, one change at a time |
| The result looked the same as before, or like boxes were ticked | Step 9 ends with a look at the whole result |
| Only the surface was audited; the user's examples were taken as the whole scope | Inventory of 100% at the smallest unit; `audit` lists what nobody looked at |
| Findings came with no fix | A `fix` row without a fix fails |
| A book was added, the audit stayed on the old rules | Versions: an older ledger is reported out of date, and the gate asks for the card again |
| Agents skipped the framework: a rule in a Markdown file is not enough | The read gate, per session, per subagent, again after compact |
| The doc grew to hundreds of lines with few tests; builders read it and the faults came back | Each rule has a test; machine tests run in hooks; a short card instead of the long doc |
| A check was reported clean that had only read the code, never the running thing | A test is tried on one good and one bad case before it counts; runtime beats static |
| Two sessions edited the same files | Step 8: the project's coordination board first |
| Relative hook paths blocked every command after a `cd` | Hooks use `$CLAUDE_PROJECT_DIR` and fail open |
| Preparation ate the turn and no reader was running | Once the user says go: brief, extract, start readers. Everything else happens while they read |
