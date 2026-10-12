# Verification Report

> Produced after apply, to confirm that the implementation agrees with the
> specs, design and tasks. The `openspec-verify-change` skill is not
> installed, so the controller ran the schema's checks directly (CLAUDE.md
> lifecycle step 6).

**Change**: `add-match-lab-testbed`
**Verified at**: `2026-10-12`
**Verifier**: Claude Opus 5.5 (controller session), in worktree `.claude/worktrees/add-match-lab-testbed`

**PRECHECK**: 48 commits since `origin/main` (merge base `3306b63`); 42 of 42 tasks checked. Both are above 0, so verification proceeds.

---

## 1. Structural Validation (`openspec validate --all --json`)

- [x] Every item returns `"valid": true`

**Result**:

```text
totals: items 1, passed 1, failed 0
change add-match-lab-testbed: valid, no issues
spec: 0 items (openspec/specs/ is still empty before archive)
```

| Item | Type | Issues |
|---|---|---|
| — | — | — |

---

## 2. Task Completion (`tasks.md`)

- [x] Every `- [ ]` is now `- [x]` (42 of 42, including 3.6 and 9.1-9.2, which were added during apply)

| Task | Reason not done | Blocks archive |
|---|---|---|
| — | — | — |

---

## 3. Delta Spec Sync State

`openspec/specs/` holds no capability yet (first change of the project).

| Capability | Sync state | Note |
|---|---|---|
| testbed-build | ✗ Needs sync | archive creates it |
| match-runner | ✗ Needs sync | archive creates it |
| match-metrics | ✗ Needs sync | archive creates it; updated after the final review (user decision: no shots/tackles/pass completion; `ball_retention` proxy) |
| benchmark-experiments | ✗ Needs sync | archive creates it |

Sync happens in lifecycle step 8 (`/opsx:archive`), after `main` is merged into the branch. `/opsx:sync` was not used.

---

## 4. Design / Specs Coherence Spot Check

| Sample | Design | Specs | Gap |
|---|---|---|---|
| Pins and patches | D1, D2, D3 (pins with commit/tag/tarball + SHA-256; ordered patch groups; separate librcsc prefixes; seed patches keep upstream behaviour) | testbed-build: all requirements | none |
| Reproducibility | D5 (synch mode; `connect_wait`, `kick_off_wait`, `synch_wait_clients`; byte comparison with skipped `(server_param` / `(msg ` prefixes; fallback B decided) | match-runner: Reproducibility check; No kick-off before all players connect; Missed cycles are recorded | none |
| Runner | D7 (ordered team connection on server log lines, process groups, `HOME` isolation, cancel flag, thread pool + port slots) | match-runner: Batch match execution (incl. cancel scenario); Ordered team connection; Run folder per match | none |
| Metrics | D8 (goals, goal difference, fouls from the log; passes, interceptions by `Side2`, `ball_retention`, possession share from events; no shots/tackles/pass completion) | match-metrics: all requirements (updated after the final review) | none |
| Experiments | D9 (paired seeds, focus team, Wilson + bootstrap, missed-cycle counts, replay of arm A's first seed) | benchmark-experiments: all requirements | none |

**Drift warnings** (non-blocking):

- `plan.md` Task 13 and Task 16 still show the schema-1 metrics (shots, tackles, pass completion). The plan is the historical execution record; the user decision after the final review (brainstorm Q15, design D8, the spec) supersedes it, and tasks 9.1-9.2 record the change.
- `testbed/patches/librcsc/0004-build-fix-...` is numbered after the seed patch `0003`, so "seed patches are numbered after the build-fix patches" (plan Task 4) does not hold for librcsc. All patches apply in order (proven by the Task 6 build), so this is cosmetic.
- The design's component table describes the user's local trees before apply. A "Patch set after apply" table was added during this verification (12 patch files, including the three header-only Boost.System fixes found by the real build).

---

## 5. Implementation Signal

- [x] No unstaged or untracked files in the worktree (`git status --short` is empty)
- [ ] All related commits are pushed. Not yet: the push happens in lifecycle step 9, after retrospective and archive.

**Commit range**: `135b8bb..HEAD` (planning commit to the end of apply; the merge base with `origin/main` is `3306b63`).

**Test evidence (run during this verification)**:

```text
harness/.venv/bin/pytest harness/tests -q
136 passed in 97.61s
```

This includes the 2 integration tests that run real HELIOS vs HELIOS matches on the built testbed. Apply also recorded:
- a real HELIOS vs Cyrus short match: status ok, extraction ok, 0 missed cycles;
- the demo experiment: paired goal difference 0.25, 95% CI [0.0, 0.75], 4 pairs, replay `differs` (fallback B), 0 missed cycles.

---

## 6. Front-Door Routing Leak Detector (warning, non-blocking)

```bash
ls docs/superpowers/specs/*.md 2>/dev/null
```

- [x] No files

| File | Captured in the change | Action |
|---|---|---|
| — | — | — |

---

## 7. Deferred Manual Dogfood vs Automated Test Equivalence

`plan.md` has no `[~]` deferred rows. The manual checks of the plan were run during apply: the full build (Task 6), the seed checks (Task 7), the spikes (Task 8 and 8b), the demo experiment (Task 18) and the HELIOS vs Cyrus match (final fix wave). This section is empty by rule.

| Deferred dogfood (plan §) | Equivalent automated test | Coverage assessment | Real gap? |
|---|---|---|---|
| — | — | — | — |

---

## Overall Decision

- [ ] ✅ PASS
- [x] ⚠️ PASS WITH WARNINGS: the drift warnings in §4 are cosmetic or historical. The branch is not pushed yet, which is expected at this step.
- [ ] ❌ FAIL

**Next step**: write `retrospective.md` (lifecycle step 7), including the summary of the apply ledger's rulings, parked findings and deferred minor findings. Then merge `main` into the branch and archive (step 8), then push and open the PR (step 9).
