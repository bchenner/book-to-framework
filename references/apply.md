# Applying a framework to a target

1. **Inventory for this target** (step 2). A second target gets its own file: set `"inventory": "inventory-<target>.json"` in the ledger. Compare the count with the source (files, scenes, controls) and write how in `how`.
2. **Audit every item.** Open each one, with its submenus, states (loading, empty, error, full), motion and behavior. For each: what would a person want here, is it here, is there too much, could it be done better? Then the rules. Split big inventories into parts of about 25 items per agent, at most 4 agents, each writing its own rows; you merge and spot-check 3 rows per part.
3. **Order the fixes** by what the user will notice, not by what is easy. One idea per fix.
4. **Fix** on a branch if the project uses them. Stay inside the project's gates. Files another thread owns: report, do not edit.
5. **Prove it.** Capture the real thing in the same state before and after: same data, same open panels, same size, same frame. Look at each pair. If you cannot tell them apart, the fix did nothing.
6. **Write conformance tests** for the rules a script can check, in the project's own test suite.
7. `bookfw.py audit <project> <id> <target>`.
8. **Show the user**: pictures labeled with where they are in the product and what to look at, biggest change first, on the device they use. Then coverage and what is open.

## Ledger: `apply/<target>.json`
```json
{
  "framework": "ux", "version": "1.0", "target": "settings", "inventory": "inventory.json",
  "rows": [
    {"item": "I001", "verdict": "ok", "rules": ["U3", "U8"]},
    {"item": "I002", "verdict": "fix", "rules": ["U4"], "finding": "Stop shows while nothing runs", "fix": "Hide it when idle",
     "preserves": "Stop still works during a run", "status": "done", "state": "idle chat, no messages, dark theme, 1440 wide",
     "before": "review/ux/I002-before.png", "after": "review/ux/I002-after.png"},
    {"item": "I003", "verdict": "na", "note": "admin only, not part of this target"}
  ]
}
```
`status`: `done`, `proposed` (needs a yes), `blocked` (by what, in `note`). When the target is something still to be made (a new video, a new page), the inventory is the plan (shot list, outline), `before` is the plan without the framework, and the ledger is filled while building.
