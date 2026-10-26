---
name: git-sync-check
description: Assess whether a local git repository is fully in sync with its GitHub (or other) remote, without making any changes, commits, or pushes. Reports uncommitted changes, staged-but-uncommitted changes, untracked files, unpushed commits, and commits on the remote that haven't been pulled locally, each with a plain-language description of what actually changed. Use this whenever the user asks "is this repo in sync", "are we up to date with GitHub", "do I have uncommitted/unpushed changes", "what's the git status of this project", wants a pre-push or pre-handoff sanity check, or is about to close out work and wants to confirm nothing is left dangling. Trigger this even if the user doesn't say "skill" or name a specific git command — any request for a read-only audit of a repo's sync state against its remote should use this skill.
---

# Git Sync Check

## Why this exists

"Is everything committed and pushed?" sounds like a one-line `git status`, but a
trustworthy answer needs more: staged vs. unstaged changes are different things,
untracked files might be gitignored noise or might be real uncommitted work, and
a repo can look clean while still holding commits the remote has never seen (or
vice versa — the remote can be ahead of local). This skill runs the full set of
checks needed to answer confidently, and reports findings in a way someone can
act on without having to go re-run the commands themselves.

This is a **read-only assessment**. Never run `git add`, `git commit`, `git push`,
`git pull`, `git merge`, `git rebase`, `git stash`, or anything else that changes
repo state, working tree contents, or the index. If the user wants those actions
taken, do the assessment first, report it, and then ask before touching anything.

## Which repo to check

If the user names a path, `cd` there (or pass `-C <path>` to git). Otherwise,
check whether the current working directory is inside a git repo
(`git rev-parse --is-inside-work-tree`). If it isn't, say so and ask which
repo/folder they mean rather than guessing.

If the repo has no configured remote, or `git fetch` fails (no network, no
credentials, remote renamed, etc.), don't fail silently — report that the
fetch didn't succeed and that the comparison against the remote is therefore
based on stale/last-known data, then continue with whatever local checks are
still possible.

## Steps

1. **Sync remote-tracking refs.** Run `git fetch` so the comparison against the
   remote reflects reality, not a stale cache. Then gather the baseline facts:
   `git status`, the current branch (`git rev-parse --abbrev-ref HEAD` or the
   branch line from `git status`), and the latest local commit (`git log -1`).

2. **Uncommitted changes.** Look at two separate buckets, since they mean
   different things to someone reviewing this:
   - Modified tracked files not yet staged: `git diff --stat` for an overview,
     then `git diff` (or `git diff <file>` per file) to see what actually changed.
   - Staged-but-uncommitted changes: `git diff --staged --stat`, then
     `git diff --staged` for the detail.
   A file can appear in both buckets (partially staged) — note that rather than
   picking one bucket arbitrarily.

3. **Untracked files.** `git status --porcelain` (or `git ls-files --others
   --exclude-standard`) lists untracked files with gitignored ones already
   excluded — no need to manually cross-reference `.gitignore`. For each one,
   a quick look (file type, size, or a peek at contents for text files) is
   enough to describe what it looks like rather than just naming it.

4. **Unpushed commits.** Once you know the current branch and that it has an
   upstream, `git log origin/<branch>..HEAD` (or `git log @{u}..HEAD`) shows
   commits that exist locally but not on the remote. If the branch has no
   upstream configured at all, say so explicitly — that's a distinct situation
   from "clean and pushed" and from "N commits ahead."

5. **Behind the remote.** `git log HEAD..origin/<branch>` (or `@{u}..HEAD`
   reversed) shows commits the remote has that local hasn't pulled. This is
   easy to skip since it's not something `git status` prominently surfaces
   before a fetch — don't skip it. Report exact commit count and, if it's a
   handful, the commit summaries.

6. **Describe changes concretely, not just by filename.** For every pending
   item — modified file, staged file, or untracked file — give a short,
   specific description of *what* changed (e.g. "added a `retry_count` field
   to the request payload", "removed the deprecated `/v1/legacy` route", "new
   file: a 2MB CSV export, looks like sample data") rather than just listing
   the path. Skim the diff or file contents to write this; don't guess from
   the filename alone.

## Report format

The opening line is a fixed template, not a paraphrase target — reuse it
**word-for-word** (only filling in `<branch>`), rather than restating the same
idea in your own words like "Yes, fully in sync." The exact wording matters
here because whoever is reading this may be scanning quickly, or even
grepping/parsing the response, and relies on the phrasing being consistent
every single time this skill runs.

**If everything is clean and synced, the first line must be exactly:**

> Fully up to date — working directory clean, no untracked files, no unpushed
> commits, and in sync with `origin/<branch>`.

Right after that line, include the branch name and the latest commit (hash +
subject) as confirmation.

**If anything is pending, the first line must be exactly:**

> Changes pending — see breakdown below.

...then group findings under whichever of these categories actually apply
(omit empty categories rather than listing them as "none"):

- **Uncommitted changes** (modified tracked files, staged changes) — file
  path + what changed, per file.
- **Untracked files** — file path + a short description of what it is.
- **Unpushed commits** — count, plus hash + subject line for each (or a
  summary if there are many).
- **Behind remote** — count of commits on the remote not yet pulled locally,
  plus subject lines if there are just a few.

Close with a short note on what this means practically (e.g. "nothing is lost,
but these 3 files need to be committed before this matches what's on GitHub")
rather than leaving the user to interpret the raw list themselves.

## Common pitfalls

- Don't rely on a cached view of the remote — always `git fetch` first, or the
  "unpushed"/"behind" checks compare against stale data.
- `git diff` with no arguments only shows unstaged changes — it will miss
  staged changes entirely. Check both.
- A file that's both modified-and-staged plus further modified afterward will
  show up differently in `git diff` vs `git diff --staged`; call this out
  rather than merging it into one bucket.
- `git status --porcelain` already respects `.gitignore` for the untracked
  list — there's no need to separately grep `.gitignore`, and doing so risks
  double-counting or missing nested `.gitignore` files.
- If the current branch has no upstream, `origin/<branch>` and `@{u}` won't
  resolve — check for an upstream before running the unpushed/behind
  comparisons, and report "no upstream configured" instead of erroring out.
