---
name: solo-ai-native-sdlc
description: Run Anthropic's AI-Native SDLC playbook (intent.md → spec.md → plan.md → code → ship) scaled down for a solo builder or small team without a review org, CI/CD, or compliance tooling. Use this whenever the user wants to build an app, feature, or small software project with Claude/Claude Code and either mentions "AI-native SDLC", "intent.md"/"spec.md"/"plan.md", asks "what stage are we at", wants a lightweight/solo version of Anthropic's SDLC playbook, or is starting a new solo or small-team build and hasn't yet written down the problem before jumping to code. Also use to figure out which artifact to produce next in an ongoing project that already has some of these files, to keep intent/spec/plan/code in sync when a decision changes mid-build, or to write a follow-up intent.md when something breaks post-launch (Stage 6 maintenance). Do not use for team-scale builds that already have CI/CD, review teams, and compliance/governance needs — point those to the full ai-native-sdlc org playbook instead.
---

# Solo AI-Native SDLC

A scaled-down version of Anthropic's AI-Native SDLC playbook for a solo builder or a very small team (1-3 people) using Claude.ai / Claude Code / Cowork, with no dedicated review org, CI/CD pipeline, or compliance function behind them.

**What's kept:** the artifact chain — `intent.md` → `spec.md` → `plan.md` (per flow) → code + tests → ship — because that chain is what catches misunderstandings in a document instead of in a rebuild. That's the entire value of the playbook; nothing below is optional as a *practice*, only the org-scale tooling around it is.

**What's dropped:** the governance layer built for teams — hooks-as-approval-gates, managed settings, parallel sessions/subagents, continuous eval suites in CI, automated monitoring agents, Claude Tag on-call. These are called out below as **[skip for solo]** so the user knows they exist and can be adopted later, not because they're wrong to use.

## How to use this skill

0. **Always write real files, never leave an artifact only in chat text.** The first time a project is touched in a conversation, establish a project slug (e.g. `gym-checkin-app`) and a docs folder for it — `docs/` if working inside an existing repo, otherwise a working folder such as `<project-slug>/docs/`. Every stage artifact (`intent.md`, `spec.md`, `plan.md`, etc.) gets created there with the file-creation tool, copied to the outputs location, and presented to the user — not just printed in the chat response. This matters most for Stages 1-2, which often run in Claude.ai chat/Projects rather than a repo: without this step the only copy of `intent.md` is the conversation itself, which is easy to lose track of and can't be re-uploaded to a Project's knowledge base. If a later stage in the same conversation needs an earlier artifact, read it back from that folder rather than from memory of the chat.
1. Figure out which stage the project is actually at (ask if unclear — don't assume). The signal is which artifacts already exist:
   - No `intent.md` yet → Stage 1
   - `intent.md` exists, no `spec.md` → Stage 2
   - `spec.md` accepted, no repo/`CLAUDE.md` yet → Stage 3a
   - `CLAUDE.md` exists, no `flows.md` yet → Stage 3b
   - `flows.md` exists, next unplanned flow has no `plan.md` → Stage 3c
   - `plan.md` accepted for a flow, code not yet written or incomplete → Stage 3d
   - Code exists for a flow, untested → Stage 4
   - All flows shipped and tested, ready for real users → Stage 5
   - Already shipped, new issue/need surfaced → Stage 6 (loops back to a new `intent.md`)
2. **Never let the user skip ahead to `plan.md` or code before `spec.md` exists**, and never skip `spec.md` before `intent.md` exists. If they ask to jump straight to code, say so plainly and offer to move fast through the earlier stages rather than skip them outright — a 10-minute intent.md is still worth it.
3. Produce exactly one artifact per turn of the sequence (don't write spec.md and plan.md in the same response) so the user can review and correct before the next stage locks in.
4. Use the templates in `assets/` as the shape for each artifact — adapt field names to the domain, but keep the sections.

---

## The sequence

| Stage | Output artifact | Where it happens |
|---|---|---|
| 1. Plan — capture intent | `intent.md` | Claude.ai Project (or chat) |
| 2. Design — requirements & design | `spec.md` | Claude.ai Project (or chat) |
| 3a. Build — repo context | `CLAUDE.md` | Cursor / Claude Code |
| 3b. Build — identify flows | `flows.md` | Cursor / Claude Code |
| 3c. Build — plan mode | `plan.md` (per flow) | Cursor / Claude Code |
| 3d. Build — implementation | code | Cursor / Claude Code |
| 4. Test — feedback loop | tests + verified output | Cursor / Claude Code |
| 5. Deploy | shipped build | Wherever it runs |
| 6. Maintain | new `intent.md` per issue found | Ongoing |

---

### Stage 1 — Capture intent (`intent.md`)

**Goal:** get the problem down in the user's own words before anyone — including Claude — jumps to a solution.

**How to run it:** ask questions **one at a time**, not as a list. Cover, in roughly this order: what the user can't do today, who's affected, what better looks like, what's explicitly out of scope. Keep going until the idea is concrete enough to write down without guessing. Then write `intent.md` using `assets/intent-template.md`.

**Sample prompt to expect/offer:**
> "I want to brainstorm an intent.md for [what you're building], to solve [the problem in your own words]. Ask me questions one at a time — what I can't do today, who's affected, what better looks like, what's out of scope — until the idea is concrete. Then write it up as intent.md covering: Problem, Proposed outcome, Affected users and systems, Constraints, Open questions."

**Done when:** `intent.md` has been written as an actual file in the project's docs folder and presented to the user (not left as chat text), and — if working in a Claude.ai Project — the user has uploaded it to the Project's knowledge base, and has corrected anything Claude got wrong. Status moves from `draft` to `accepted` only once they've confirmed it.

---

### Stage 2 — Requirements and design (`spec.md`)

**Goal:** turn intent into something buildable. This stage also covers what people often think of as separate "tech stack" and "schema" discussions — fold them into one spec.

**How to run it:** read the accepted `intent.md` and produce a requirements/design spec covering, at minimum: user stories, the data model (entities, states, relationships — be concrete, not abstract), a recommended tech stack sized to a small project maintained mostly with AI assistance, and what's explicitly out of scope for v1. Use `assets/spec-template.md`. **Flag areas of concern clearly** rather than silently picking an answer when something is genuinely ambiguous or risky.

If the user has a starting-point stack in mind, sanity-check the spec against it but don't treat it as gospel — reason about trade-offs and say so if something doesn't fit.

**Sample prompt to expect/offer:**
> "Read the attached intent.md and produce a requirements and design spec for [what you're building]. Cover: user stories, the data model (name the key entities and their states — be concrete), recommended tech stack for a small project maintained mostly with AI assistance, and out-of-scope for v1. Document it fully as spec.md, ready to hand to build. Flag any areas of concern clearly."

**Done when:** `spec.md` has been written as an actual file next to `intent.md` in the docs folder and presented to the user, flagged concerns are resolved, and the user has mentally walked 2-3 real edge-case scenarios through the data model without it breaking. Push them to do this before calling it done — it's the cheapest place to catch a broken data model.

**➡ Handoff point.** Once `spec.md` is accepted, building moves to Cursor/Claude Code (or wherever code actually gets written). This mirrors the playbook's handoff from Design into Build — say so explicitly when this point is reached.

---

### Stage 3 — Build

#### 3a. Repo context (`CLAUDE.md`)

**Goal:** give Claude Code the context a new joiner would need — commands, conventions, architecture, common mistakes. Steps:
1. Create the repo, copy `intent.md` and `spec.md` into `/docs/` inside it.
2. Run `/init` in Claude Code to generate a starting `CLAUDE.md`.
3. Trim it to roughly one page: build/test/lint commands, conventions that matter, things Claude keeps getting wrong.
4. Check it into Git. **Working rule:** when Claude makes the same mistake twice, the fix goes into `CLAUDE.md` — not a one-off correction repeated every session.

**Sample prompt to expect/offer:** `/init` (Claude Code's built-in command), followed by: "Trim this CLAUDE.md to about one page — keep build/test/lint commands and conventions that actually matter, cut the rest."

#### 3b. Identify the flows

**Goal:** write the implementation plan before any code, **per flow** — not for the whole app at once.

**First, identify the flows — don't let the user guess at this alone.** Break the app into vertical slices (end-to-end pieces of user-visible functionality — not layers like "the database" or "the UI"). For each: name, what it does end to end, which role(s) it serves, and why it matters. Then propose a build order — highest-risk or highest-value first, not easiest-first — with reasoning for that order.

**Before presenting the draft, self-check for horizontal layers and fold them in.** A horizontal layer is infrastructure or setup with no direct user-facing outcome on its own — "set up the database," "build authentication," "API setup," "UI component library." None of these let a real person accomplish a real task standalone, so none of them belong as their own flow entry. Review the draft list and, for anything that qualifies: fold it into whichever flow actually needs it first (build exactly what that flow needs, not a speculative full version), note in the flow's description that this happened, and re-check whether the build order still makes sense afterward — a merge can shift what should come first. Do this self-check automatically, every time, before the user ever sees the draft — don't rely on the user to catch and request this afterward.

**Write this as a real file, `docs/flows.md`, and present it** — don't leave it only in the chat response. This becomes the map Stage 3b works through one flow at a time, and later sessions (or a different tool/IDE picking up the same repo) need to be able to read it back rather than re-deriving it from scratch or relying on chat history that may not be available.

**Sample prompt to expect/offer:**
> "Based on docs/intent.md and docs/spec.md, break this app into vertical-slice flows — the smallest end-to-end pieces of user-visible functionality, not layers. For each flow: name, what it does end to end, which user role(s) it serves, and why it matters. Then suggest a build order — highest-risk or highest-value first — and say why. Write this to docs/flows.md."

**Done when:** `docs/flows.md` exists as a real file, and the user has confirmed the flow breakdown and build order before the first plan-mode prompt runs.

#### 3c. Plan mode, per vertical slice

Once flows are identified and ordered, work through them **one at a time** — plan, implement, test, verify, commit, then move to the next flow's plan. Don't write multiple `plan.md` files upfront; each plan should benefit from what the previous flow's build actually revealed.

Interrogate each plan before accepting it — what could break, what's the riskiest step, what did it choose not to do. Save the accepted plan as `plan.md` (or `plans/<flow-name>.md` per slice).

**Sample prompt to expect/offer** (name the flow's actual edge cases from `spec.md` up front — don't leave them for Claude to guess):
> "Read docs/intent.md, docs/spec.md, and docs/flows.md. Give me an implementation plan for the '[flow name]' flow.
>
> Cover:
> - Files that change — new and modified, with a one-line note on what changes in each
> - Order of work — smallest safe increments first, noting dependencies between steps
> - Edge cases this flow must handle: [name the actual ones from spec.md — e.g. partial payment, a resource in an unexpected state, an offline-then-synced action]
> - Riskiest step — what's most likely to break, and how we'd know
> - Tests that prove it — specific cases, not 'add tests'
> - What this deliberately doesn't do — anything adjacent you're rejecting for this slice
>
> Don't write code yet. If anything in intent.md/spec.md is ambiguous for this flow, flag it before planning around an assumption."

**Done when:** `plan.md` for this flow is saved and the user has accepted it, having pushed back on anything that seemed underspecified or too easy to have caught real risk.

**[skip for solo]:** parallel sessions/worktrees and subagents — useful once there are multiple independent flows to build simultaneously; not needed building alone.

#### 3d. Implementation

**Goal:** turn the accepted `plan.md` into working code — this is the actual coding step, easy to treat as implied rather than explicit since it's a short instruction compared to the artifacts around it.

**Sample prompt to expect/offer:**
> "Implement docs/plan.md (or plans/[flow-name].md) for the '[flow name]' flow, exactly as planned. If you hit something the plan didn't account for, stop and flag it rather than improvising silently."

If something unplanned does come up mid-implementation and gets resolved, **update `plan.md` to reflect it** before moving on — this is the same "keep the artifact chain in sync" rule from the top-level rules of thumb, applied at flow scale.

**Done when:** the flow's code matches what `plan.md` describes (or `plan.md` was updated to match a deliberate deviation), and it's ready to move into Stage 4 for that same flow before starting the next flow's plan.

---

### Stage 4 — Test (feedback loop)

**Goal:** Claude checks its own work before the user does — this is the playbook's "feedback loop," not a separate QA phase.

**Set up once, in `CLAUDE.md`:**
```markdown
## Verifying your work
- Test: [test command] (all green; never skip or delete a failing test)
- Build: [build command]
Run these before reporting any task complete, and show the output.
If a test fails, fix the code, not the test.
```

**Per flow:** ask Claude to write test cases covering the real edge cases for that flow (name them explicitly — don't accept "add tests"), then run them and fix anything failing before reporting done.

**Sample prompt to expect/offer:**
> "Write test cases for the [flow name] flow, covering: [name the actual edge cases — e.g. empty input, a resource in an unexpected state, a boundary value]. Then run them and fix anything failing before reporting done."

**[skip for solo]:** continuous evals in CI — that's for catching regressions when a team changes `CLAUDE.md`/skills over time at scale. Manual "does it still work" checks are enough solo.

---

### Stage 5 — Deploy

**Goal:** get it in front of real users fast, even if ugly.

**[skip for solo]:** full CI/CD pipeline, hooks-as-approval-gates, managed settings — these exist to gate production releases across a team with regulatory needs. For a solo/small build, "build it, install/publish it, watch real users use it" is the deploy step.

**Sample prompt to expect/offer:**
> "Build and package this for [target — e.g. TestFlight, a shared link, an install on one machine]. Walk me through installing it on [where the real user will actually use it]."

**Done when:** real users have used it for real tasks and at least one round of "this doesn't match how we actually work" feedback has been collected.

---

### Stage 6 — Maintain

**Goal:** when something breaks or a new need shows up, it becomes a new `intent.md`, not a random patch.

Whenever a problem is reported or spotted, write it up the same way as Stage 1 (Problem / Proposed outcome / Affected users / Constraints) and run it back through the sequence. This keeps the same audit trail going after v1 ships — resist the pull to just patch code without an intent.md, even for "small" fixes, once the fix touches the data model or a user-facing flow.

**Sample prompt to expect/offer:**
> "[Describe what broke or what new need came up.] Write this up as a new intent.md, same format as before, and let's figure out if it needs a spec.md update or just a plan.md for a fix."

**[skip for solo]:** automated monitoring agents, control-band breach detection, Claude Tag on-call — these close the loop autonomously for production systems with real traffic/metrics worth monitoring automatically. Not relevant until usage volume justifies it.

---

## Rules of thumb throughout

- **Always produce a plan before code.** Catches misunderstandings when they're cheap to fix — the single highest-leverage habit in the whole playbook.
- **Keep the artifact chain in sync.** If a decision changes mid-build, update `spec.md`/`plan.md` — don't let code silently drift from the docs.
- **Don't skip Stages 1-2 when it feels slow.** They're what make Stage 3 onward fast instead of a rebuild.
- **The "[skip for solo]" items aren't wrong to use** — they're built for team/regulatory scale. Revisit them if the project grows past a solo/small build or gets other developers involved. If the user describes a team with a review process, CI/CD, or compliance needs already in place, point them to the full org-scale `ai-native-sdlc` playbook instead of this scaled-down version.

## Templates

- `assets/intent-template.md` — Stage 1
- `assets/spec-template.md` — Stage 2
- `assets/flows-template.md` — Stage 3b, flow identification
- `assets/plan-template.md` — Stage 3b, per-flow plan
- `assets/claude-md-verification-snippet.md` — Stage 4 snippet to paste into `CLAUDE.md`
