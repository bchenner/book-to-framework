# Hooks

`bookfw.py hooks <project> <id> install` copies `framework-gate.mjs` into `<project>/.claude/hooks/`, lists the framework in `.claude/frameworks.json`, adds three events to `.claude/settings.json` (existing hooks stay; the old file is kept in the temp folder) and runs the gate test. One gate serves every framework of the project. Running sessions pick new hooks up after a restart.

## The `hooks` block of rules.json
```json
"hooks": {
  "watch":  ["src/videos/*/scenes/**", "projects/*/shot-list*.md"],
  "ignore": ["**/*.test.ts"],
  "content": null,
  "checks":  [{"rules": ["V4"], "paths": ["projects/*/gags.json"], "run": ["python", "scripts/gag_lint.py", "{file}"]}],
  "deliver": [{"command": "render\\.py full", "run": ["python", "scripts/gag_lint.py", "--all"], "block": false}]
}
```
- `watch`: globs from the project root (`**` crosses folders, `{a,b}` is a choice). Only files whose author must know the framework. Too wide, and agents learn to ignore it.
- `content`: a regular expression the new text must match, for files that only sometimes matter. Then set `test_content` to a matching text for the gate test.
- `checks`: run after Edit and Write, exit 1 = fail, 45 s at most, output goes back to the agent. `{file}` is the absolute path, `{root}` the project.
- `deliver`: a regular expression on a shell command. `run` must pass. With `"block": true` the command is refused: only after the user said yes. Without `run`, the checklist is shown once per version.

## What it does
| Event | Result |
|---|---|
| Edit or Write of a watched file, card not read | Refused, with the path of the card |
| Shell command that writes a watched file | The same (redirects, `tee`, `sed -i`, `cp`, `Set-Content`, `open(.., "w")`) |
| The whole card was shown | Remembered for this session and this subagent, for this version |
| Clear or compact | Forgotten |
| Anything breaks (no node file, bad JSON, a check that cannot start) | The tool runs |

It does not see a file written by a script whose command does not name it. Delivery checks catch that.

## Checks worth writing
Count things in the plan file, not in prose. Read the running thing, not only the code. Print the file, the rule id and the fix. Exit 0 when the file is not its business.

## Other agents
Codex, Antigravity and Gemini do not run these hooks. Put the card's path in `AGENTS.md` and in every brief, and run the delivery check yourself before accepting their work.

## Remove
`bookfw.py hooks <project> <id> uninstall` (docs stay).
