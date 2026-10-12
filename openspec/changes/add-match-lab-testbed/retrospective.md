# Retrospective: add-match-lab-testbed

> Written: 2026-10-12 (after verify passed with warnings)
> Commit range: `135b8bb..0fc1c3d` (planning commit to the verify commit; archive commit follows)
> Worktree: `.claude/worktrees/add-match-lab-testbed` (branch `add-match-lab-testbed`)

---

## 0. Evidence

- **Commit range**: `135b8bb..0fc1c3d` (49 commits after the planning commit: 26 code/patch/test commits by implementer subagents, 23 change-artifact and checkbox commits by the controller)
- **Diff size**: +5,255 / −63 lines across 70 files; `harness/`, `testbed/`, `LICENSE`, `.gitignore` alone: +4,955 lines across 63 files
- **Tasks done**: 42/42 (`grep -cE '^\s*- \[x\]' tasks.md` → 42), including 3.6 and 9.1–9.2 added during apply
- **Active hours**: apply, review and fix waves about 2.3 h of commit time (00:24–02:41 UTC, 2026-10-12), plus the full build (~11 min) and real-match runs; planning and pre-apply checks on 2026-10-11 not counted
- **Subagent dispatches**: 45 fresh dispatches (21 implementers incl. Task 8b, one noise-off spike runner and the final fix wave; 17 task reviews; 6 scoped re-reviews; 1 final whole-branch review on Opus) plus 5 implementer resumes for fix rounds
- **New external dependencies**:
  - Python: `pytest>=8` (MIT, development only), `setuptools>=77` (MIT, build backend); no runtime dependencies
  - Pinned testbed sources (built, not vendored): rcssserver 19.0.0 (LGPL-3.0), librcsc `65e1393` (LGPL-3.0), helios-base `66fd63d` (GPL-3.0 files under an MIT root), Cyrus librcsc fork `6bafd9b` (LGPL-3.0), Cyrus team `335497b` (GPL-3.0 files under an MIT root), CppDNN `8cb5a55` (GPL-3.0), Eigen 3.4.0 (MPL-2.0), rcg2data `3097064` (GPL-3.0); RapidJSON (MIT) is fetched by the Cyrus CMake build at a pinned commit
- **Bugs encountered post-merge**: none (not merged yet)
- **OpenSpec validate state at archive**: pass at verify (`openspec validate --all`: 1 item, 0 failures); re-run at archive
- **Test coverage signal**: pytest 136 passed (134 unit + 2 integration on the real testbed), run during verify; plus a real HELIOS vs Cyrus match and the demo experiment during apply

Commit chain (time order, grouped):

```
135b8bb docs(change): plan add-match-lab-testbed
7c599bc..327e774  scaffold, pins, patch application (Tasks 1-3)
2a054a6           build-fix and seed patches (Task 4)
cceee5d..c1207f9  build command, manifest, CLI build, 3 Boost build-fix patches (Tasks 5-6)
948cf92           seed checks recorded (Task 7)
f437e0e..57fa095  spike 1, hold patch + spike 2 (Tasks 8, 8b)
aa982e6           fallback B and the hold recorded in the change
baee35a..93fa606  profiles, seeds/ports, single match, rcg/repro, metrics, run_matches (+ fix rounds)
72b5784..cd3c055  statistics, experiments/reports, CLI (+ fix rounds)
306fdaa..6bcb346  integration tests, demo experiment, README (+ wording fix)
cfdfa30..eb089b3  metric decision (spec) and the final-review fix wave
0fc1c3d           docs(change): verify add-match-lab-testbed
<archive commit follows in lifecycle step 8>
```

---

## 1. Wins

- **Pre-apply execution of the plan paid off.** Before apply, every plan code block was extracted into a scratch project (100 tests passed) and one real match was run through the plan's code. This found the synch-mode empty-kick-off problem (`connect_wait`), the coach race, the `setuptools>=77` need and others before any implementer saw them (design D5/D7; conversation record before `135b8bb`).
- **Pinned, patched build works from a fresh checkout.** One full build in the worktree took about 10.7 min and passed the isolation checks: each team links its own librcsc, and nothing was written outside `.testbed/` (Task 6, `3b6e6b2..c1207f9`).
- **Evidence-driven, bounded spike.** `.rcl` analysis found the cause of divergence (connect timing → pre-kick-off step counts: first connect 20 vs 21, kick-off 364 vs 366). One bounded patch (`57fa095`) made all 7,270 commands of steps 0–299 byte-identical. A noise-off third spike showed the remaining cause is not server noise. The user decided fallback B on evidence, not guesswork (design D5).
- **The review loop caught real defects.**
  - Relative run folders broke rcg2data and the server (Task 13, `1d03ecb`).
  - One failing job left other matches running for up to an hour (Task 14, `93fa606`).
  - "differs" results were unreadable (Task 16, `c1d5c9e`).
  - CLI tracebacks (Task 17, `cd3c055`).
  - Three meaningless metrics (final review → `c498196`).
- **Robust process lifecycle.** Process groups, the cancel flag and Ctrl-C handling are tested with real child processes and real UDP ports (`test_match.py`, `test_runner.py`). Every real run left no processes behind.
- **End-to-end evidence.** The demo experiment ran (paired goal difference 0.25, 95% CI [0.0, 0.75], 0 missed cycles), and a real HELIOS vs Cyrus match ran (status ok, schema-2 metrics).

## 2. Misses

- 🟡 [painful | evidence: final review; `cfdfa30`, `c498196`] **The metrics spec assumed rcg2data behaviour from its enum, not its output.** `Shoot` is emitted only for goals, `Tackle` never, and intercepted passes are `Interception` rows. So shots, tackles and pass completion were meaningless. This was caught only by the final review, although the Task 13 reviewer had real event counts in hand. It needed a spec change and a user decision late in the cycle.
- 🟡 [painful | evidence: Tasks 13, 14, 16, 17 fix rounds] **The plan code was verified on happy paths only.** The scratch run before apply did not cover relative paths, a job error in a parallel batch, a "differs" report, or CLI error exits. Four fix rounds came from that gap.
- 🟡 [painful | evidence: `42c59a3`, `4176573`, `c1207f9`] **The plan assumed the local build recipes were complete.** Boost 1.90 ships no compiled Boost.System, and the autotools `AX_BOOST_SYSTEM` macro aborted in three components, which needed three unplanned build-fix patches. Three full rebuilds were needed, because `--only` requires an existing manifest.
- 🟡 [painful | evidence: design D5] **The user's goal "a fixed seed reproduces a match" is not met in the testbed** (fallback B). The cost was Task 8, Task 8b and a third spike. The decision rule was agreed in advance, so the cost was bounded.
- 📌 [nit | evidence: controller tool errors] **The worktree isolation guard refused compound git commands**, inline `VAR=value` commands and even Python heredocs whose text contained the word "git". Many retries; implementers worked around it with script files.
- 📌 [nit | evidence: Task 13] **The Task 13 implementer did not write its report file**; the controller copied the hand-back into it.
- 📌 [nit | evidence: Task 18 re-review] **A cheap-model re-reviewer misread the `.rcl` `time,stoppage` field as the cycle** and reported a false contradiction. The controller disproved it with a byte comparison (parked with a ruling).
- 📌 [nit | evidence: Task 7] **Server checks run from the worktree root left six stray `.rcg`/`.rcl` files** (removed by the controller).
- 📌 [nit | evidence: every implementer report] **The plan's Global Constraints fixed the commit trailer to "Claude Opus 5.5"**, which conflicts with each subagent's own attribution. Every implementer flagged it. A controller ruling settled it, but the constraints file was never updated.
- 📌 [nit | evidence: conversation] **The controller claimed "no remote" at the end of apply without checking.** The user corrected it (`origin` exists).
- 📌 [nit | evidence: `testbed/patches/librcsc/`] **librcsc `0004` (build fix) is numbered after the seed patch `0003`**, against the plan's numbering rule (cosmetic; the patches apply in order).

## 3. Plan deviations

| Plan task | What changed | Why |
|-----------|--------------|-----|
| 4 / 7 | Seed patches were written in Task 4 against the check clones; Task 7 became checks only | Build once instead of twice (pre-apply plan revision) |
| 6 | Three extra build-fix patches (rcssserver 0002, librcsc 0004, helios-base 0001) | Boost 1.90 has no compiled Boost.System; the autotools check aborted |
| 8 | Stopped for the user; spike result DIFFERS from cycle 1 | Plan checkpoint; user decision |
| 8b (new, tasks 3.6) | rcssserver `synch_wait_clients` hold patch + second spike; a third noise-off spike | User-approved bounded attempt at exact replay |
| 9, 11, 12, 18 | `synch_wait_clients` reserved and set to 22 + coaches; `SKIP_PREFIXES = ("(server_param", "(msg ")`; integration test and README for fallback B | Fallback B decision; the hold patch was kept |
| 11 / 13 | `run_dir` resolved to an absolute path in `run_single_match` and `extract_and_measure` | Relative run folders broke rcg2data and the server |
| 14 | Any job exception sets the cancel flag (also inside the job) | Other matches kept running after a failure; results were lost |
| 16 | "differs" note, `cycle n/a`, excerpts around the first differing byte, arm-key validation, OSError in the replay check | Fallback B makes "differs" the normal result |
| 17 | `ReproError` (exit 2); positive int/float argparse types | Tracebacks instead of `error:` messages |
| 18 | README wording on where replays diverge | Imprecise plan text |
| 9.1 (new) | Metrics schema 2: shots, tackles, pass completion removed; `ball_retention` added | rcg2data emits only a subset of events (user decision) |
| 9.2 (new) | Final fix wave: closed `/proc` handles, fake-server race, Python ≥3.11.4, README D5 pointer, stale manifest, finite timeouts, seed range, replay after extraction failure, build cancel message; one HELIOS vs Cyrus match | Final whole-branch review |
| Global | Commit trailers name the writing model; `requires-python >=3.11.4` | Accurate attribution; `tarfile` `filter="data"` needs 3.11.4 |

## 4. Skill / workflow compliance

| Skill                                            | Used |
|--------------------------------------------------|------|
| superpowers:brainstorming                        | ✓ (at propose, for `brainstorm.md`; the design itself was agreed in conversation as CLAUDE.md step 2 asks) |
| superpowers:writing-plans                        | ✓ (`plan.md`, revised twice before apply) |
| superpowers:using-git-worktrees                  | ✓ (worktree on the change branch via `git worktree add`, entered with the native tool's `path` mode, because the native create mode branches from `origin/<default>`) |
| superpowers:subagent-driven-development          | ✓ (ledger, briefs, per-task reviews, fix rounds, final review, one fix wave) |
| (transitive) superpowers:test-driven-development | ✓ (RED/GREEN evidence in every code task report; checks-only tasks 4, 6, 7, 8 had no TDD by design) |
| (transitive) superpowers:requesting-code-review  | ✓ (17 task reviews, 6 re-reviews, 1 final review) |
| superpowers:finishing-a-development-branch       | pending — lifecycle step 9 runs after archive, as CLAUDE.md orders |

Also: the schema's verify step names `openspec-verify-change`, which is not installed; CLAUDE.md anticipates this, and the checks were run directly (`verify.md`).

### Deliberately Skipped Skills

None. `finishing-a-development-branch` is not skipped; it is the next lifecycle step after archive.

## 5. Surprises

- **rcssserver keeps stepping in synch mode before clients connect**, as fast as connected clients answer. Pre-kick-off step counts therefore depend on wall-clock timing.
- **Even with the hold patch and all noise at 0, matches diverge at the kick-off step.** The order and timing of command arrival and the shared server RNG matter more than noise parameters.
- **rcg2data's enum promises more than its analyzer emits** (Shoot only at goals, no Tackle, no Foul, no failed Pass).
- **The user's local trees built with Boost 1.90 although the pinned sources do not.** The local builds must have had an unrecorded fix or configuration; the uncommitted diffs did not show it.
- **A short match (600 cycles) takes only about 27 s** in synch mode; the demo experiment took minutes, not the half hour estimated.
- **The worktree guard inspects the text of whole commands**, including heredoc bodies, for the word "git".

## 6. Promote candidates → long-term learning

- [ ] 🟡 **Check an external tool's real output before writing a spec on it, not its enum or documentation** → **Promote to memory** (type: feedback)
  > **Why**: the match-metrics spec assumed rcg2data emits `Shoot`, `Tackle` and failed `Pass` rows; it does not, and the defect surfaced only in the final review (`cfdfa30`).
  > **How to apply**: during brainstorm/propose, when a requirement depends on a third-party tool's output, run the tool on one real input and record the observed event/field set in design.md before writing the requirement.

- [ ] 🟡 **When the plan's code is pre-verified, also exercise failure and relative-path cases** → **Promote to memory** (type: feedback)
  > **Why**: the scratch run before apply passed 100 tests but missed relative run folders, batch error handling, the "differs" report and CLI error exits — four fix rounds.
  > **How to apply**: in the pre-apply plan check, add one relative-path call, one forced failure per external process, and one non-happy result per report renderer.

- [ ] 🟡 **Implementer and reviewer rules for worktree-isolated sessions: plain single git calls; script files for env-var commands; never put the word "git" in heredoc text** → **Promote to project CLAUDE.md** (a "Working in the apply worktree" note) or memory (type: reference)
  > **Why**: the guard refused many controller and implementer commands; the workarounds were rediscovered several times.
  > **How to apply**: include the rule in the shared implementer/reviewer rules file at the start of every apply.

- [ ] 📌 **Plans should not fix the commit trailer to one model when subagents write the commits** → **Promote to schema** (`superpowers-bridge` plan template / writing-plans Global Constraints guidance)
  > **Why**: every implementer flagged the conflict between the plan constraint and its own attribution.
  > **How to apply**: Global Constraints say "end each commit with the Co-Authored-By trailer of the model that wrote it".

- [ ] 📌 **Use a mid-tier model for re-reviews that judge data or log formats** → **Promote to memory** (type: feedback)
  > **Why**: a Haiku re-reviewer misread `time,stoppage` in `.rcl` files and produced a false finding.
  > **How to apply**: cheap tier only for re-reviews of pure code or doc diffs; mid tier when the finding depends on reading real data.

- [x] 📌 **Run `git remote -v` before claiming there is no remote** → **Promoted to memory** (`check-git-remote-before-claiming`)
  > **Why**: the controller repeated a stale "no remote" note; the user corrected it.
  > **How to apply**: whenever a step depends on remote state (push, PR), check it in that turn.

- [ ] 📌 **Run rcssserver checks from an ignored folder or pass `game_log_dir`** → **One-off** (recorded here)
  > **Why**: server checks from the worktree root left stray logs; the harness itself always sets `game_log_dir`.

### Follow-up changes (from the final review and this cycle)

- Shot and tackle detection (for example our own rcg2data patch), then reinstate those metrics.
- Interleave experiment arms per seed (A0, B0, A1, B1, …) so machine load over time does not confound pairs.
- Record patch checksums in `run.json` next to the pins.
- An integration test for HELIOS vs Cyrus (marked `testbed`).
- Exact replay in our own engine (fallback B leaves it there).
- StatsBomb realism comparison; the black-box optimizer (planned later changes).

---

## Appendix A. Apply ledger summary

The apply ledger (`.superpowers/sdd/plan/progress.md`, ignored scratch) is deleted with the worktree in step 9. This appendix keeps every ruling, parked finding and deferred minor finding it recorded.

### Rulings (in order; cost if wrong)

1. Stop after Task 8 for the user's spike decisions, although subagent-driven development says not to pause. Cost: one wait for the user.
2. If the worktree guard refused read-only `git -C ~/<repo> diff`, build the patches by copying files into clean clones (not needed in the end). Cost: patches differing from the local diffs, caught by apply checks.
3. Model choice: cheap model for tasks whose plan held complete code; standard model for build, match and review work; Opus for the final review. Cost: extra turns or a weaker check.
4. Build with `--jobs 2` despite about 1 GB free RAM. Cost: an out-of-memory compile (none happened).
5. Commit trailers name the model that wrote each commit, not the plan's fixed "Opus 5.5"; `7c599bc` keeps the Opus trailer. Cost: trailers differ from the plan text.
6. Accept the three extra Boost build-fix patches within the plan's build-fix mechanism. Cost: documentation drift (fixed at verify).
7. Keep the `synch_wait_clients` hold patch; the harness sets it to 22 + enabled coaches (reserved). Cost: one more patch and parameter to maintain.
8. `SKIP_PREFIXES = ("(server_param", "(msg ")` under fallback B. Cost: a config difference visible only in `server_param` would be skipped (the profile hash still records it).
9. Resolve run folders to absolute paths in `run_single_match` and `extract_and_measure` (Task 13). Cost: none.
10. Any job exception sets the cancel flag before re-raising (Task 14). Cost: one failing slot stops the batch (intended).
11. Show "differs" clearly; validate arm keys; catch OSError in the replay check; center excerpts on the first differing byte (Task 16). Cost: small extra code.
12. Reword the README to state exactly where replays diverge (Task 18). Cost: none.
13. Raise `requires-python` to `>=3.11.4` against the plan's `>=3.11`. Cost: excludes Python 3.11.0–3.11.3.
14. Extend the final fix wave to the stale manifest, finite timeouts, seed range and meaning, replay after an extraction failure, and the build cancel message. Cost: small extra code.
15. Keep the ledger until this retrospective was written (CLAUDE.md step 7), instead of deleting it after the final review. Cost: none.

### Parked findings

- Task 18 re-review: the claim that the demo logs contradict "commands of steps 0–299 identical, first difference at step 300". Ruling: the re-reviewer misread the `.rcl` `time,stoppage` field; all 7,270 command lines of steps 0,0–0,299 are byte-identical between `runs/demo-noise/A/0000-normal` and `repro-A-0000`, and step 0,300 differs. README and design D5 stand.

### Deferred minor findings, fixed later in this cycle

- `ports.is_bound` left `/proc` files open (final wave B); fake-server coach race (C); Python floor vs `tarfile` filter (D); README D5 pointer (E); stale manifest after a failed build (H); nan/inf timeouts (I); unbounded `--seed` (F); repro excerpt limited to the first 200 characters (Task 16 round); design table drift (verify).

### Deferred minor findings, still open (candidates for later changes)

- **Task 1**: unused `Path` import in `test_paths.py` (plan-mandated); `test_repo_root_contains_pins` not hermetic if `MATCHLAB_ROOT` is set.
- **Task 2**: `load_pins` does not wrap `TOMLDecodeError`/OSError; non-string values raise `TypeError`; `$` regex accepts a trailing newline; untested branches.
- **Task 3**: relative patch paths would fail (latent; the build passes absolute paths); locale encoding for headers; no rollback after a partial apply; untested branches; redundant sort.
- **Task 4**: `seed_from_env_or` uses `strtoul`, which accepts a sign (the harness passes only valid seeds).
- **Task 5**: a partial rebuild of librcsc does not rebuild dependents; download/extract errors not wrapped with the component name; partial download cached; thin `build_all` tests; `load_manifest` does not map OSError or non-object JSON; manifest path duplicated; unused import in `test_manifest.py`.
- **Task 6**: `librcsc/0004` and `helios-base/0001` are byte-identical (a later change must edit both); `--jobs` help mentions "3 GB RAM"; the outside-write check was not re-verifiable by the reviewer.
- **Task 7**: long design-table cell for the Cyrus row.
- **Task 8b**: the hold has no timeout of its own (bounded by the harness connect timeout); no effect outside synch mode; the hold loop's receive polls shuffle the shared RNG (not a regression).
- **Task 9**: `_match`/`_teams` do not type-check tables; an extra team side is not named; default name truncation drops the side suffix for long team ids; NaN/inf in match values accepted.
- **Task 10**: `wait_until_bound` process-exit branch untested; `test_slots_do_not_overlap` name overstates; port 16410 assumed free.
- **Task 11**: the timeout clock starts after connection (up to ~4 min extra); cancel not checked during `starter.wait(60)`; `killpg` after reap (PID reuse, negligible); second Ctrl-C or SIGTERM to the harness not handled; a `write_record` failure in `finally` masks the original error.
- **Task 12**: `skipped` lists configured prefixes, not used ones; the cycle is approximate for non-show lines; `compress_logs` is not atomic; untested failure paths.
- **Task 13**: an old `match.event.csv` is not removed first (cannot happen with fresh run folders); OSError for a missing rcg2data binary not caught.
- **Task 14**: the parallel-collision test does not prove overlap; Ctrl-C not tested with a real signal; second Ctrl-C during shutdown; cancel not honoured during extraction; timing-sensitive cancel test.
- **Task 15**: float off-by-one in the low percentile index at non-default levels; the determinism test compares two runs in one process; `resamples=0` and `k > n` unvalidated.
- **Task 16**: lazy `report` import could move under `TYPE_CHECKING`; no `swap_sides` or relative `out_dir` test through `run_experiment`; an empty excerpt renders as two backticks; reason text not asserted in the OSError test.
- **Task 17**: thin CLI tests (`run` happy path and exit 1, `check-repro` identical exit 0, `ExperimentError` exit 2); a test depends on the `short` preset.
- **Task 18**: the integration reproducibility test passes on both outcomes (fallback B, plan-mandated).
- **Final review**: Ctrl-C during extraction marks a finished match `extraction-failed`, not `cancelled`; `is_bound` returns False on any OSError (affects only the error message); `plan.md` still shows the schema-1 metrics (historical).
