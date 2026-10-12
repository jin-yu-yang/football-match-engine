# CLAUDE.md

This is a football (soccer) match engine inspired by the 2D RoboCup Soccer Simulator (`rcssserver`) and HELIOS base team (`helios-base`).

## Specs: where the source of truth lives

- **Canonical specs live in `openspec/specs/<capability>/spec.md`.** They describe the system's current, testable behaviour, one folder per capability.
- **Canonical specs start with the first change.** Nothing is back-filled. Each change proposes delta specs (`ADDED` / `MODIFIED` / `REMOVED`) for only the slice it touches, and archiving the change merges those deltas into `openspec/specs/`. The specs fill in as the work does.
- **Capabilities are named by feature area, in the words the team already uses.** Create a capability folder only when a change first needs it. Do not design the whole taxonomy up front.
- **Do not write specs for code you are not changing.** Such specs become large and stale, and nobody trusts them.
- **Do not write documents under** `docs/superpowers/specs/` or `docs/superpowers/plans/`.

### Authority order

When sources disagree, use this order:

1. Explicit user instructions for the current task
2. The active OpenSpec change artifacts, for the scope of that change
3. Canonical specifications under `openspec/specs/`
4. Current code and tests as implementation evidence

Code or tests that disagree with a canonical specification indicate possible specification drift or an implementation defect. Do not silently change either side to match the other; surface the conflict.

If no canonical spec covers an area yet, the current code and tests are the reference for that area.

## Workflow routing (read at session start)

This repo uses [`superpowers-bridge`](https://github.com/JiangWay/openspec-schemas/tree/main/superpowers-bridge) to connect OpenSpec and Superpowers. It is the default schema (`openspec/config.yaml`). The schema is in `openspec/schemas/superpowers-bridge/`. Its README has the full rationale.

The schema's instructions and this file both describe the workflow. If they disagree, follow this file.

### 1. Decide: change or direct PR

Open a change for:
- a new capability;
- a change to behavior or to a contract;
- an architecture change;
- a change to the protocol or message format between the server and its clients;
- a change to server parameters, player parameters, formations, or other values that change match behavior;
- an upgrade of `rcssserver`, `helios-base` or `librcsc`;
- a cross-system integration;
- a breaking change.

Use a direct PR only when the work keeps the intended behavior and is one of these:
- a bug fix with no contract change;
- a test backfill;
- a linter or build-tool tweak;
- a non-breaking upgrade of any other dependency;
- a typo or documentation update;
- a config value tweak that does not change match behavior, for example a log path or a port number.

If you are not sure, ask the user.

### 2. Lifecycle of a change

Do the steps in this order. The schema's apply instruction also lists verify, retrospective, archive and finish steps. Do them as steps 6 to 9 below, not as part of apply.

1. **Explore (optional).** Run `/opsx:explore`.
2. **Brainstorm in the conversation.** Follow the method of `superpowers:brainstorming`: ask questions, compare alternatives, and get the user's approval of the design. Do not invoke the skill in this step, and do not write files. Propose invokes the skill in step 3. Continue until all 5 promotion criteria hold (section 6). Then ask: "Ready to `/opsx:propose`?" Wait for the user to agree. Never start propose without that agreement.
3. **Propose.** Run `/opsx:propose <change-name>`. It creates `openspec/changes/<change-name>/` and every artifact that apply needs, in this order: `brainstorm.md`; `proposal.md` and `design.md`; `specs/<capability>/spec.md`; `tasks.md`; `plan.md`.
   - `brainstorm.md` records the design that the user agreed to in step 2. Do not ask again about decisions settled in step 2.
   - The schema runs `superpowers:brainstorming` for `brainstorm.md` and `superpowers:writing-plans` for `plan.md`. Both write into the change folder (section 7). If a skill tries to write outside the change folder, or to start another skill before its turn, stop it. Continue in the artifact order above.
   - Propose can stop to ask the user a question. Answer it, then continue.
   - Propose never starts apply.
4. **Complete the planning artifacts.** If propose stops before `plan.md` is done:
   - Run `openspec status --change "<change-name>" --json` to find the next ready artifact.
   - Run `openspec instructions <artifact> --change "<change-name>" --json` to get its rules and template.
   - Write the artifact. Repeat until `plan.md` is done.

   Then ask the user to review the planning artifacts. Do not start apply until the user agrees.

   When the user agrees, commit the change folder. Commit it on a branch, not on `main`. If the current branch is `main`, create a branch first. Apply creates its worktree from this commit, so the commit must contain `plan.md`.
5. **Apply.** Run `/opsx:apply <change-name>`. It creates a git worktree and runs `plan.md` with subagent-driven development. It checks off `tasks.md`. Do steps 6 to 9 in the same worktree.
6. **Verify.** `openspec status` shows `verify` as ready once `plan.md` exists. Do not write it before apply is complete.
   - Get the rules with `openspec instructions verify --change "<change-name>" --json`.
   - Follow its PRECHECK and all of its checks. The `openspec-verify-change` skill is not installed, so do its checks directly.
   - Write `verify.md`. If a blocking check fails, fix the problem and verify again.
7. **Retrospective.** Get the rules with `openspec instructions retrospective --change "<change-name>" --json`. Write `retrospective.md`. Include the summary of the ledger findings (section 7, last bullet).
8. **Archive.** Merge `main` into the change branch, so that archive merges the delta specs into the latest `openspec/specs/`. If the merge has conflicts in `openspec/specs/`, stop and show them to the user. Then run `/opsx:archive <change-name>`. It merges the delta specs into `openspec/specs/` and moves the folder to `openspec/changes/archive/YYYY-MM-DD-<change-name>/`.
9. **Finish.** Use `superpowers:finishing-a-development-branch`. When it offers choices, choose to push the branch and create a PR, unless the user asks for a different choice. Open the PR last, so that it contains the complete archived change.
   - The skill keeps the worktree while the PR is open. Fix PR feedback in that worktree. If a fix adds a ruling or finding, add it to the archived `retrospective.md`.
   - After the PR merges, remove the worktree: `git worktree remove .worktrees/<change-name>`.

### 3. Resume a change

At the start of a session, or when the user is in the middle of a change:
1. Run `git worktree list`. If the change has a worktree, run all the commands below in that worktree. After apply starts, the main checkout does not show the current state of the change.
2. Run `openspec list` to find active changes.
3. Run `openspec status --change "<change-name>" --json`.
4. Read the change's artifacts. If apply has started, read its ledger too (section 7).
5. Judge whether apply is complete from the `tasks.md` checkboxes and the commits on the change branch. Do not judge it from `openspec status`.
6. Continue from the first lifecycle step that is not complete. Do not create a new change for the same work.

### 4. Commands

This project installs six OpenSpec commands: `/opsx:propose`, `/opsx:explore`, `/opsx:apply`, `/opsx:update`, `/opsx:sync` and `/opsx:archive`.

Use `/opsx:sync` and `/opsx:update` only when the user asks (but you may suggest `/opsx:update` in some cases). `/opsx:sync` merges delta specs into `openspec/specs/` before archive, which conflicts with step 8.

The bridge README uses four commands that are not installed. Use these replacements:

| README command   | Use instead |
|------------------|-------------|
| `/opsx:new`      | `/opsx:propose` |
| `/opsx:ff`       | `/opsx:propose` |
| `/opsx:continue` | `openspec status` and `openspec instructions` (lifecycle steps 4 and 7) |
| `/opsx:verify`   | `openspec instructions verify` (lifecycle step 6) |

Do not run `openspec config profile`. It changes each developer's global OpenSpec config.

### 5. Change names and scope

- Name a change in kebab-case, starting with a verb, for example `add-offside-trap-tactic`. Do not add a date. Archive adds it.
- One change has one clear result. If an architecture change is too large, split it into several changes.
- Write delta specs only for the capabilities that the change touches.

### 6. Promotion criteria (verbal brainstorm → propose)

All 5 must hold before you suggest propose. If one is missing, continue to brainstorm.

If the user asks to propose before all 5 hold, tell the user which criteria are missing. Then do what the user decides.

1. **Scope is fixed.** One sentence states what is in the change and what is out.
2. **Major design choices are made.** You compared the alternatives and chose one. Each open question has an owner and a statement of what it can affect.
3. **Dependencies on other systems are known.** Mark each dependency as ready, mockable, or unknown.
4. **Acceptance criteria are clear.** You can state concrete pass conditions: the deliverables of the change, plus the build and test checks that cover what it touches.
5. **The conversation converges.** The last turns confirm decisions. They do not add new alternatives.

### 7. Where the output goes

Durable output goes into the change folder, `openspec/changes/<change-name>/`. That includes the brainstorm and the plan.

- The `superpowers:brainstorming` and `superpowers:writing-plans` skills default to `docs/superpowers/`. In a change, redirect them to `brainstorm.md` and `plan.md`.

Working notes from apply are scratch:
- Subagent-driven development keeps its ledger (`progress.md`), task briefs, reports and review packages in `.superpowers/sdd/plan/` inside the change's worktree. The folder is named after `plan.md`. `.superpowers/` must be in `.gitignore`.
- Never commit these files. Never copy them into the change folder or `docs/superpowers/`.
- Every change's plan file is named `plan.md`, so all changes share the folder name `plan`. Run apply for one change per worktree. If the ledger's first line names another change's `plan.md`, stop and ask the user.
- The ledger is deleted when the worktree is removed (step 9). In step 7, write a summary in `retrospective.md` of every ruling, parked finding and deferred minor finding that the ledger records. Do not copy the ledger files.

## Project rules