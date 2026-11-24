// Framework gate: a Claude Code hook that makes agents use the frameworks made by /book-to-framework.
// Installed per project by `bookfw.py hooks <project> <id> install`; reads .claude/frameworks.json and each rules.json.
//
// A rule in a Markdown file is not enough: agents skip it. So:
//   PreToolUse   Edit | Write ...     a watched file: refused until this session (and this subagent) has read the CARD
//   PreToolUse   Bash | PowerShell    a shell write to a watched file: the same. A delivery command: its check must pass
//                                     (deliver.run), and the checklist is shown once
//   PostToolUse  Read | shell         the whole card was shown (its end marker is in the output): remembered, by version
//   PostToolUse  Edit | Write         the machine checks of that file run; a failure goes back to the agent
//   SessionStart clear | compact      the card is no longer in the context: forgotten
//
// Anything that goes wrong here lets the tool run: the gate never blocks work by its own fault.

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const STATE_DIR = process.env.FRAMEWORK_GATE_STATE || path.join(os.tmpdir(), 'framework-gate');
const slash = (p) => String(p || '').replace(/\\/g, '/');
/** A path as Git Bash may write it ("/e/x"), in the form Node reads ("E:/x"). */
const native = (p) => {
    const s = slash(p).replace(/^["']|["']$/g, '');
    return process.platform === 'win32' ? s.replace(/^\/([a-z])(?=\/|$)/i, (_, d) => d.toUpperCase() + ':') : s;
};

function rootOf(start) {
    let d = path.resolve(start || '.');
    for (let i = 0; i < 40; i++) {
        if (fs.existsSync(path.join(d, '.claude', 'frameworks.json'))) return d;
        const up = path.dirname(d);
        if (up === d) break;
        d = up;
    }
    return null;
}
function frameworks(root) {
    const out = [];
    const reg = JSON.parse(fs.readFileSync(path.join(root, '.claude', 'frameworks.json'), 'utf8'));
    for (const f of reg.frameworks || []) {
        if (f.enabled === false) continue;
        try {
            const fw = JSON.parse(fs.readFileSync(path.join(root, f.rules), 'utf8'));
            if (process.env.FRAMEWORK_GATE_ONLY && fw.id !== process.env.FRAMEWORK_GATE_ONLY) continue;
            out.push(fw);
        } catch { /* a missing or broken framework never blocks */ }
    }
    return out;
}

/** Glob -> RegExp: ** crosses folders, * does not, {a,b} is a choice. */
export function glob(g) {
    let r = '', depth = 0;
    for (let i = 0; i < g.length; i++) {
        const c = g[i];
        if (c === '*' && g[i + 1] === '*') { i++; if (g[i + 1] === '/') { i++; r += '(?:.*/)?'; } else r += '.*'; }
        else if (c === '*') r += '[^/]*';
        else if (c === '?') r += '[^/]';
        else if (c === '{') { depth++; r += '(?:'; }
        else if (c === '}' && depth) { depth--; r += ')'; }
        else if (c === ',' && depth) r += '|';
        else r += c.replace(/[.+^$()|[\]\\]/g, '\\$&');
    }
    return new RegExp('^' + r + '$', process.platform === 'win32' ? 'i' : '');
}
const hit = (globs, rel) => (globs || []).some(g => glob(g).test(rel));
export function watched(fw, rel, text) {
    const h = fw.hooks || {};
    if (!rel || rel.startsWith('..') || rel.startsWith('docs/frameworks/') || rel === slash(fw.doc)) return false;
    if (hit(h.ignore, rel) || !hit(h.watch, rel)) return false;
    return !h.content || new RegExp(h.content).test(text || '');
}

const stateFile = (inp) => path.join(STATE_DIR, (String(inp.session_id || 'none') + (inp.agent_id ? '-' + inp.agent_id : '')).replace(/[^\w-]/g, '') + '.json');
const readState = (inp) => { try { return JSON.parse(fs.readFileSync(stateFile(inp), 'utf8')); } catch { return {}; } };
const writeState = (inp, s) => { fs.mkdirSync(STATE_DIR, { recursive: true }); fs.writeFileSync(stateFile(inp), JSON.stringify(s)); };
const key = (root, fw) => slash(root).toLowerCase() + '#' + fw.id;
const hasRead = (inp, root, fw) => readState(inp)[key(root, fw)] === fw.version;
const marker = (fw) => `<!-- card-end:${fw.id} v${fw.version} -->`;

const REDIRECT = /(?:^|[^<>&=0-9])>{1,2}(?![&>])\s*("[^"\n]+"|'[^'\n]+'|[^\s;|&<>()]+)/g;
const WRITES = /\btee\b|\bsed\b[^|;&]*\s-i|\b(cp|mv)\s|\b(Set|Add)-Content\b|\bOut-File\b|\b(Copy|Move)-Item\b|WriteAllText|write_text|writeFile|\bopen\([^)]*['"][wa]/i;
/** The files a shell command may write: what it redirects into; with a writing command, every path in it. */
function shellTargets(command, cwd, root) {
    const toks = [...command.matchAll(REDIRECT)].map(m => m[1]);
    if (WRITES.test(command)) toks.push(...(command.match(/"[^"\n]+"|'[^'\n]+'|[^\s;|&<>()"',]+/g) || []));
    return toks.map(t => native(t)).filter(t => /[/.]/.test(t) && t.length < 400)
        .map(t => slash(path.relative(root, path.resolve(cwd, t)))).filter(r => r && !r.startsWith('..'));
}
const deny = (why) => ({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: why } });
const tell = (event, text) => ({ hookSpecificOutput: { hookEventName: event, additionalContext: text } });
const mustRead = (root, fw, what) => deny(`${what} is covered by the framework "${fw.title}" (v${fw.version}), and its card has not been read in this session. `
    + `Read all of ${slash(path.join(root, fw.card))} (no offset or limit), make the work follow it, then do this again. `
    + `It is about ${Math.round(((fw.core || []).length * 25 + (fw.rules || []).length * 30) / 50) * 50} words.`);

function run(root, argv, file) {
    const args = argv.map(x => String(x).replaceAll('{file}', file || '').replaceAll('{root}', root));
    const r = spawnSync(args[0], args.slice(1), { cwd: root, encoding: 'utf8', timeout: 45000, windowsHide: true, maxBuffer: 8e6 });
    if (r.error || r.status === null) return null;                  // could not run: not the agent's fault
    return { ok: r.status === 0, text: ((r.stdout || '') + (r.stderr || '')).trim().slice(-1800) };
}

export function decide(inp) {
    const ev = inp.hook_event_name, tool = inp.tool_name || '', ti = inp.tool_input || {};
    const cwd = native(inp.cwd || process.cwd());
    if (ev === 'SessionStart') {
        if (inp.source === 'clear' || inp.source === 'compact') writeState(inp, {});
        return null;
    }
    const isEdit = /^(Edit|Write|MultiEdit|NotebookEdit)$/.test(tool), isShell = /^(Bash|PowerShell)$/.test(tool);
    const file = native(ti.file_path || ti.notebook_path || '');
    const abs = file ? path.resolve(cwd, file) : '';
    const root = (abs && rootOf(path.dirname(abs))) || rootOf(cwd) || (process.env.CLAUDE_PROJECT_DIR && rootOf(native(process.env.CLAUDE_PROJECT_DIR)));
    if (!root) return null;
    const rel = abs ? slash(path.relative(root, abs)) : '';

    if (ev === 'PostToolUse' && (tool === 'Read' || isShell)) {
        const shown = JSON.stringify(inp.tool_response ?? '');
        for (const fw of frameworks(root)) {
            const whole = shown.includes(marker(fw)) || shown.includes(JSON.stringify(marker(fw)).slice(1, -1));
            const plain = tool === 'Read' && rel === slash(fw.card) && !inp.tool_response && !(ti.offset > 1) && !ti.limit;
            if (whole && (isShell ? slash(ti.command).includes(path.posix.basename(slash(fw.card))) : rel === slash(fw.card)) || plain) {
                writeState(inp, { ...readState(inp), [key(root, fw)]: fw.version });
            }
        }
        return null;
    }
    if (ev === 'PreToolUse' && isEdit && rel) {
        const text = [ti.content, ti.new_source, ti.old_string, ti.new_string].concat((ti.edits || []).flatMap(e => [e.old_string, e.new_string])).filter(Boolean).join('\n');
        for (const fw of frameworks(root)) if (watched(fw, rel, text) && !hasRead(inp, root, fw)) return mustRead(root, fw, rel);
        return null;
    }
    if (ev === 'PreToolUse' && isShell) {
        const cmd = String(ti.command || '');
        const targets = shellTargets(cmd, cwd, root);
        for (const fw of frameworks(root)) {
            const t = targets.find(r => watched(fw, r, cmd));
            if (t && !hasRead(inp, root, fw)) return mustRead(root, fw, t);
            for (const d of (fw.hooks || {}).deliver || []) {
                if (!new RegExp(d.command).test(cmd)) continue;
                if (d.run) {
                    const r = run(root, d.run, '');
                    if (r && !r.ok && d.block) return deny(`The framework "${fw.title}" check failed, so this delivery is refused. Fix it, or ask the user to accept it.\n${r.text}`);
                    if (r && !r.ok) return tell('PreToolUse', `The framework "${fw.title}" check found problems. Tell the user each one that stays.\n${r.text}`);
                }
                const s = readState(inp), k = key(root, fw) + '#checklist';
                if (s[k] === fw.version) continue;
                writeState(inp, { ...s, [k]: fw.version });
                return tell('PreToolUse', `Framework "${fw.title}", before you report this: go through every Must in ${slash(fw.card)} by its test, look at the real result, and tell the user each rule the work does not meet.`);
            }
        }
        return null;
    }
    if (ev === 'PostToolUse' && isEdit && rel) {
        const fails = [];
        for (const fw of frameworks(root)) {
            for (const c of (fw.hooks || {}).checks || []) {
                if (!hit(c.paths || fw.hooks.watch, rel) || hit(fw.hooks.ignore, rel)) continue;
                const r = run(root, c.run, abs);
                if (r && !r.ok) fails.push(`${fw.title} ${(c.rules || []).join(', ')}: ${r.text}`);
            }
        }
        if (fails.length) return { decision: 'block', reason: 'Framework check failed on ' + rel + '. Fix it now:\n' + fails.join('\n') };
    }
    return null;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    try {
        const out = decide(JSON.parse(fs.readFileSync(0, 'utf8')));
        if (out) process.stdout.write(JSON.stringify(out));
    } catch { /* never block by its own fault */ }
    process.exit(0);
}
