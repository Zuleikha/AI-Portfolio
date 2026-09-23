# CLAUDE.md — Banking Knowledge Agent

A production-style, source-backed AI support agent (RAG + MCP tools + LLM) for a
synthetic banking technology platform — built to demonstrate production AI engineering.

This file is the **sole authority** for how work is done in this repository.
It replaces `prompt.md` and `ccp.txt` (archived, unchanged, in `docs/legacy/`).

| What | Where |
|---|---|
| Permanent rules (this file) | `CLAUDE.md` |
| Project definition + Stage 1–15 detail | `docs/PROJECT_PLAN.md` |
| Current progress and recorded decisions | `docs/HANDOVER.md` |
| Architecture, reasoning, decision records | `docs/architecture-guide.html` |

---

## 1. Session start and recovery

Before doing any development work:

1. Read `docs/HANDOVER.md` — the checkpoint at the top first, then only the sections
   the current task needs.
2. Run `git status` and `git log --oneline -3`; compare with the handover.
3. Determine exactly which stage was last completed and approved.
4. Read **only the current stage's section** of `docs/PROJECT_PLAN.md` — once per
   stage, not on every turn, and never the whole file.
5. Do not repeat completed work. Do not skip unfinished work.
6. Do not start a new stage until the previous stage has been approved.

Never assume a previous Claude Code session completed work unless the actual
repository confirms it.

---

## 2. Development workflow

Work strictly **one stage at a time**.

### For every stage

1. Implement the stage.
2. Run all relevant tests; verify the implementation works.
3. Update `docs/HANDOVER.md`.
4. Report, in the format in §6.
5. **STOP.** Wait for explicit approval.

### After approval

1. Re-check the implementation and re-run the relevant tests.
2. Check `git status` and review all changes.
3. Check for secrets and unwanted files.
4. Verify there are no accidental nested project directories.
5. Update `docs/HANDOVER.md`.
6. Create a clear Git commit for the approved stage.
7. Push to the GitHub remote and verify the push succeeded.
8. Report: stage completed, commit hash, commit message, branch, push result.
9. Only then begin the next stage — and STOP again after it is implemented and tested.

### Approval cycle

```
IMPLEMENT → TEST → UPDATE HANDOVER → SHOW ME → STOP → APPROVAL
→ VERIFY → COMMIT → PUSH → VERIFY PUSH → NEXT STAGE
```

- Never skip the approval step.
- **The only thing that lifts a stop is the literal word `APPROVED`.**
- Never commit an unapproved stage.
- Never push an unapproved stage.

### Tooling

Always run checks through the project venv — never bare `python` or `pip`:

```
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy
```

### Parallel sub-agents

Default for every stage: **single cohesive build, no sub-agents.**

Only use parallel sub-agents for a stage below, only when the user explicitly asks
for it at that stage's kickoff, and only after the shared contract (data models,
protocol/interface, naming) is written and frozen by the main session first — then
one sub-agent per independent unit, dispatched in a single batch, with the main
session integrating afterward. This is the method Stage 6 used; see
`docs/HANDOVER.md` §6.E for the worked example and the integration cost it
recorded.

| Stage | Good fit? | Why |
|---|---|---|
| 6 — MCP Tools | ✅ Yes (used) | Six independent tools, no shared state until registration |
| 7 — Agent Decision and Tool Selection | ❌ No | Decision logic is shared state across `policy.py`, `models.py`, `agent.py`, `prompts.py` |
| 8 — Conversation Context | ❌ No | Single cohesive concern |
| 9 — Web Interface | ❌ No | Single cohesive concern |
| 10 — Observability | ✅ Yes | Independent instrumentation points across modules |
| 11 — Testing and Evaluation | ✅ Yes | Independent test/evaluation areas |
| 12 — Containerisation | ❌ No | Single cohesive concern, mostly configuration |
| 13 — Security and Production Readiness | ✅ Yes | Independent audit areas (auth, secrets, input validation, prompt injection, MCP security, data privacy, rate limiting, LLM/tool failure handling, logging, dependency security) |
| 14 — Production Architecture | ✅ Yes | Independent documentation domains (scaling, vector DB, LLM provider abstraction, MCP architecture, service boundaries, deployment, failure modes, HA) |
| 15 — Final Engineering Review | ❌ No | One reviewer must see the whole system to judge consistency |

Never default into sub-agents without being asked, even for a stage marked ✅.

#### When a stage uses parallel sub-agents

1. Break the stage into independent units before starting any agent.
2. Each sub-agent owns one unit and does not touch shared files until integration.
3. After all sub-agents finish, run one integration pass: resolve conflicts, dedupe
   code, run the full test suite.
4. Record the sub-agent split in `docs/architecture-guide.html` as a normal
   architecture decision (what was split, why, how integration went).
5. Add one line to `README.md` noting the stage used parallel sub-agent development.

---

## 3. Handover file — `docs/HANDOVER.md`

The recovery point for future sessions. Never rely on conversation history as the
only record of project progress.

### Update it only when

- a stage is **completed** or **approved** (including its commit hash and push result);
- a **design decision** is made;
- a **blocker** is identified;
- the **session is ending**.

Do not update it for every small change.

### Decision rule

A decision is not recorded until it is written into `docs/HANDOVER.md`. A decision
agreed in conversation but not yet written down does not count. If a decision is made
mid-stage, before implementation begins, write it down immediately — do not wait for
stage completion.

### It must contain

| Section | Contents |
|---|---|
| Current Stage | Stage number, name, status, last completed step, next step |
| Current Work | Implemented, in progress, unfinished |
| Architecture | Current architecture, components, important design decisions |
| Files | Important files and their purpose |
| Testing | Tests run, results, commands used |
| Problems and Decisions | Known issues, blockers, assumptions, decisions |
| Git | Branch, latest commit, commit message, push status |
| Next Action | The exact next action to take |

Never put secrets, API keys, passwords or credentials in the handover file.

---

## 4. Architecture guide — `docs/architecture-guide.html`

A personal technical reference for understanding and remembering the system. It is
**not** the application's user-facing interface.

- Keep it updated whenever the architecture changes.
- **Decision rule.** A decision is not recorded until it is written into
  `docs/architecture-guide.html`. This applies to every design decision from Stage 3
  onward — including a decision presented to the user as options with a
  recommendation, and whichever option they choose. Record it **at the time it is
  made**, in the same *what / why / what was rejected* form as previous entries
  (§20 decision records), not only in the stage-end summary. Do not wait to be
  reminded.
- **Readability.** For each section, answer: what it does, why it exists, what
  problem it solves, what would go wrong or be missing without it, and how it
  connects to the previous and next stage. State the technical term first, then
  explain it in plain English — do not assume prior knowledge of the specific
  technology, even where general software engineering knowledge is fine to assume.
  Define a term in full the first time it appears in a section; after that, a short
  reminder is enough, not a full re-explanation every time it reappears. Self-check
  before adding a section: could someone who understands software engineering but
  not this specific technology read it and understand what's happening and why? If
  not, improve it before adding it. Reuse the existing `.note` style; no new CSS or
  classes. (This absorbs `docs/legacy/improve.md`'s "FUTURE CHANGES" rule, now archived.
  Its one-time plain-English rewrite of the older text is done for §1–§7 and continues
  from §8.)
- **Accuracy.** Check every claim against the code before writing it — names, counts,
  defaults, versions, the order of steps. Re-run free, offline demos instead of copying old
  output. Diagrams may be changed when they no longer match the architecture; confirm the
  real order in the code first.
- **Status markers.** When a stage is committed, update the header pill, the footer, the
  §1 stage table and the §1 diagram ticks in the same change.
- **One editor at a time.** Before editing the guide, run `git status`. If another stage's
  work is uncommitted, do not edit the guide: the edits would clash or be swept into that
  stage's commit. Readability-only edits go in their own `docs(guide)` commit.

---

## 4a. README — `README.md`

- **Structure is fixed.** `README.md` follows the structure defined in `README.md` itself as
  of Stage 9 — concise, table/diagram-driven, no stage narrative: title and description,
  synthetic-data callout, Status, Architecture, Technology Stack, Requirements, Setup, Run,
  Test, one short section per major subsystem (mini diagram + tight bullets, not a
  walkthrough), Configuration, Repository Structure, Engineering Focus, Licence.
- **End of every stage:** update only the sections that changed — Status, the relevant
  subsystem section, Configuration, Repository Structure (and the test count under Test).
  A new major subsystem gets one new short section in the same style.
- **Not a changelog.** Do not let `README.md` grow with stage history or detailed reasoning —
  that stays in `docs/HANDOVER.md` and `docs/architecture-guide.html`.
- Check every number and claim against the code before writing it, as for the guide (§4).

---

## 5. Git rules

Never commit:

- `.env`
- API keys, passwords, tokens, credentials, generated secrets
- sensitive local databases

Always check `.gitignore`. When a new local working file appears, ignore it rather
than remembering to skip it.

The repository root is `banking-knowledge-agent`. Never create
`banking-knowledge-agent/banking-knowledge-agent`. Never create a real `.env`
containing secrets.

Before every commit, list the exact file set with `git add -An` (dry run) — `git
status` collapses untracked directories and can hide what is really being staged.

After every approved stage:

1. Verify files.
2. Verify tests.
3. Verify Git status.
4. Check for secrets.
5. Update `HANDOVER.md`.
6. Commit.
7. Push.
8. Verify the push.
9. Report the commit hash and push result.

---

## 6. Reporting format — the only one

Use this at the end of every stage, and whenever reporting progress:

```
STAGE COMPLETE — Stage <n>: <name>

What changed
- files created / changed / removed, one line each

Tests
- command(s) run → result (e.g. 891 passed · ruff clean · mypy clean)

Needs your decision
- anything blocking or requiring approval, or "Nothing — awaiting approval"
```

Then STOP and wait. Do not continue automatically.

---

## 7. Context and token efficiency

- **Do not reread or restate** `CLAUDE.md` or `docs/HANDOVER.md` content that is
  already in context. Reread only if the file changed.
- **Do not repeat requirements back** to the user.
- **No lengthy explanations** unless asked. Short, structured, bullets and tables.
- **Inspect only files relevant** to the current task. Use targeted reads and search
  rather than whole-file reads of large files.
- **Do not reproduce** large files, logs or full diffs in responses — summarise, and
  quote only the lines that matter.
- Read `docs/PROJECT_PLAN.md` only for the current stage, once per stage.
- **Report only:** what changed, test result, and anything that needs a decision.
- Before ending a session, run `/usage` and note the session's total cost/tokens
  in the closing message (it resets on `/clear`, so this is the only look at it).

---

## 8. When unsure

Stop and ask **one** question. Don't guess and don't go out of scope. Ask before big
or hard-to-reverse changes.
