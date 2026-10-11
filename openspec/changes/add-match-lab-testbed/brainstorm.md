<!--
Raw capture of superpowers:brainstorming output.
The design was agreed in conversation (CLAUDE.md lifecycle step 2) before
/opsx:propose. This file records that decision log. design.md reorganizes it.
-->

# Brainstorm: add-match-lab-testbed

Path: **architectural** (a new subsystem in an empty repo).
Date: 2026-10-11.

## 1. Background

### 1.1 Long-term goal

The project will build an FM-style football match engine and, later, a free
GPLv3 football management game. The engine must be:

- **observable and explainable**: a user clicks a player and sees the
  candidate actions and their scores;
- **testable by users**: users can run benchmark experiments on tactics and
  player attributes and publish engine-balance reports.

The motivation is the attribute imbalance of Football Manager. Community tests
(FM Arena; Bilibili user Charlotte1010202) show that pace and acceleration
change the win rate by about 77 percentage points (pp) from 1 to 18, while
marking, tackling, positioning and decisions stay below the noise floor
(about +/-3 pp in that data). An engine that users can test is the answer.

### 1.2 Path to the engine: testbed, then independent

The RoboCup 2D simulator (`rcssserver`) and the HELIOS and Cyrus teams are the
reference architecture. The plan is:

1. **Testbed phase**: run the RoboCup code as it is (with small patches) and
   build the measurement tools around it.
2. **Independent phase**: build our own C++ engine (2.5D height, per-player
   perception, attribute model). The measurement tools from phase 1 then
   measure the new engine.

This change is the first change of phase 1. The measurement tools live longer
than the testbed.

### 1.3 Facts found during exploration

- **HELIOS has no shared team plan.** Each of the 11 player processes runs
  `ActionChainHolder::update(world())` every cycle from its own world model.
  The search is best-first (`priority_queue`), chain length 4, at most 500
  evaluated states.
- **A RoboCup match is 10 minutes of football**: 6000 cycles x 100 ms. A
  90-minute match is 54,000 cycles. Real-football comparisons must scale per
  minute.
- **Licenses.** rcssserver and librcsc are LGPLv3. helios-base has an MIT
  `LICENSE` and a GPLv3 `COPYING`; 135 source files carry GPLv3 headers
  (including `action_chain_graph.cpp`). Cyrus has 118 GPLv3-headed files.
  CppDNN, rcg2data and rcgamestats are GPLv3.
- **The server seed cannot be set.** In rcssserver 19.0.0,
  `stadium.cpp:182` supports a fixed seed, but the `random_seed` parameter is
  commented out at `serverparam.cpp:962`. The server always seeds from the
  clock.
- **The clients seed randomly.** librcsc seeds `rcsc/random.h:62` from
  `std::random_device`, and `ann/rbf.cpp` and `ann/ngnet.cpp` from `time(0)`.
- **Synch mode is available.** rcssserver has `synch_mode`. librcsc and the
  Cyrus librcsc fork send `(done)` from player, coach and trainer commands.
- **Noise settings already exist**: `ball_rand`, `player_rand`, `kick_rand`
  and the visual noise settings.
- **Short matches are possible** with `half_time` and `nr_normal_halfs`.
- **Log naming**: `game_log_fixed` and `game_log_fixed_name` give fixed log
  names. `game_log_dir` sets the folder. The `.rcg` header contains all
  server parameters.
- **rcg2data** (`hidehisaakiyama/rcg2data`, commit `3097064`, GPLv3, C++,
  about 3,000 lines, needs librcsc) uses SPADL action types. It implements
  Pass, Dribble, Interception, Shot, KeeperSave, Tackle, BallTouch,
  OutOfBounds, OwnGoal and MultiTouch. Cross, set pieces, Foul and Clearance
  are in its enum but are not extracted. It writes CSV.
- **Akiyama and Nakashima, "Soccer Gameplay Data Generation" (RoboCup 2024)**:
  rcgamestats (distributed runs) + rcg2data + 78,000 matches (CC0). This is
  the nearest prior work to this change.
- **R2D-RL (arXiv 2606.18786)**: about 34 cycles/s per instance with RL
  overhead. The testbed is good for building tools, not for studies with
  millions of matches.
- **Local state** (machine: 4 cores, 3 GB RAM):

  | Component | Upstream | Pin | Local changes |
  |---|---|---|---|
  | rcssserver | rcsoccersim/rcssserver | tag `rcssserver-19.0.0` (local copy is a release tarball) | unknown |
  | librcsc | helios-base/librcsc | `65e1393` | build fixes: missing includes; simdjson `static_cast<formatter*>` |
  | helios-base | helios-base/helios-base | `66fd63d` | none |
  | Cyrus team | naderzare/cyrus-soccer-simulation-team | `335497b` | CMake: Boost.System header-only fallback; `HINTS` for librcsc search |
  | Cyrus lib | Cyrus2D/cyrus-soccer-simulation-lib | `6bafd9b` | CMake Boost fallback; missing `#include <algorithm>` |
  | rcg2data | hidehisaakiyama/rcg2data | `3097064` | none; not built |

  All of these use CMake. librcsc is installed in `/usr/local`. Python 3.14 is
  available; pytest is not installed.

## 2. Decision chain

**Q1. What is the first change?**
Options: (a) the testbed harness; (b) our own engine core; (c) the height
system.
**Decision: (a)**, with no height and no new engine. Reason: a measurement
baseline must exist before we build anything that needs balancing.

**Q2. Decision architecture of the future engine.**
Options: A central team brain; B HELIOS-like (each player decides alone);
C hybrid (one shared team plan per team per decision tick + per-player belief
and choice).
**Decision: C.** Not built in this change. Recorded because it shapes later
changes.

**Q3. Seeds and noise.**
**Decision:** the user controls the seed and the noise. A fixed seed must
reproduce a match. "The user can control and change everything."

**Q4. Balance testing.**
**Decision:** balance needs a benchmark test (ground truth by experiment),
not only realism statistics.

**Q5. License.**
**Decision:** GPLv3 for the whole project. We may reuse GPL code (rcg2data,
rcgamestats, HELIOS) directly.

**Q6. Scope of change 1.**
Options: (a) runner + profile/seed/noise + logs + events + per-match metrics;
(b) (a) + A/B experiment report; (c) (b) + StatsBomb realism comparison.
**Decision: (b).** StatsBomb comparison is a separate change (new data
dependency).

**Q7. Harness language.**
Options: C++ (engine language) or Python.
**Decision: Python.** The analysis ecosystem (kloppy, socceraction,
statsbombpy, pandas) is in Python. The engine stays C++.

**Q8. How to make matches reproducible.**
Options: A patch (enable `server::random_seed`, seed the clients, run
`synch_mode`); B statistical reproducibility only.
**Decision: try A** as a spike inside this change. **Fallback: B.** The
harness records the reproducibility status.

**Q9. How the repo holds RoboCup code and patches.**
Options: (i) patch files + pinned build script; (ii) our own forks as git
submodules; (iii) existing builds in `~`, patches outside the repo.
**Decision: (i).** The repo stays small, the sources stay upstream, and
anyone can rebuild the exact testbed.

**Q10. Black-box optimizer ("exploit hunter").**
**Decision:** a later change. This change must give it a callable Python
API: `run_experiment(...)`.

**Q11. Reinforcement learning.**
**Decision:** not in the MVP.

## 3. Agreed design

### 3.1 Scope sentence

A Python harness that runs batches of rcssserver matches between two chosen
RoboCup teams under a versioned profile (server and player parameters, noise,
seeds), extracts SPADL events with rcg2data, computes per-match metrics, and
writes an A/B report with paired seeds; the RoboCup code is built from pinned
commits plus patch files.

**Out:** our own engine, height, UI, StatsBomb comparison, the optimizer, RL,
distributed (multi-host) execution.

### 3.2 Pipeline

```
 profile (TOML) + experiment (TOML: arms, N, base seed)
        |
        v
 runner --> rcssserver (synch_mode, seed) + team L + team R   x N, process pool
        |
        v
 run folder: profile copy, seeds, .rcg/.rcl (compressed)
        |
        v
 rcg2data --> events CSV (SPADL) --> per-match metrics JSON
        |
        v
 A/B report: per-arm stats, paired differences, bootstrap 95% CI,
             profile hashes, seeds, reproducibility status (JSON + Markdown)
```

### 3.3 Build from pins

- A pins file names each component: upstream URL and commit or tag.
- Patch files are grouped by purpose:
  - **build fixes**: the current local diffs, so pinned commits compile with
    the modern toolchain (Boost.System header-only, missing includes,
    simdjson);
  - **seed patches**: enable `server::random_seed`; make librcsc (both copies)
    take a seed.
- The build step clones the pins into a build folder that git ignores,
  applies the patches, and builds with CMake.
- **Each librcsc installs into its own prefix** inside the build folder,
  never into `/usr/local`, because HELIOS and Cyrus link different librcsc
  forks.

### 3.4 Profiles and identity

- Profiles are TOML files (Python 3.14 has `tomllib`).
- A profile holds server parameters, player parameters, noise settings, the
  two teams and match length.
- A "noise off" preset exists.
- **A result is identified by the profile hash plus the seed.** Every output
  records both.

### 3.5 Running

- A local process pool runs matches in parallel. Default parallelism is 1 on
  this machine (3 GB RAM).
- Each match gets its own port set (player, coach, online-coach ports).
- Each match writes into its own run folder.

### 3.6 Metrics (from rcg2data events and the `.rcg`)

Goals, goal difference, shots, passes, pass completion, interceptions,
tackles, touch-based possession share. Only implemented rcg2data events are
used.

### 3.7 A/B experiment

- An experiment has two arms. Each arm is a profile, or a base profile plus
  overrides.
- **Paired seeds**: both arms run the same list of seeds.
- Statistics: mean paired difference in goal difference with a bootstrap 95%
  CI; W/D/L rates per arm with CIs.
- Output: JSON data and a Markdown summary.
- Sequential stopping is a later change.

### 3.8 Python API

`run_experiment(...) -> results`. The CLI calls it now. The optimizer calls
it later.

## 4. Minor assumptions (made during propose; correct them in review)

- Package name `matchlab`. CLI subcommands for build, run, experiment and a
  reproducibility check.
- Client seed transport: an environment variable read by the patched librcsc.
  Each player gets a seed derived from the match seed, the side and the
  uniform number.
- Per-match seeds derive deterministically from the experiment base seed and
  the match index.
- Side swapping (each seed played twice with sides exchanged) is a profile
  option, default off, because of the machine's limits.
- Reproducibility is compared on `.rcg` content written with fixed log names.
- pytest is a development dependency installed in a project virtual
  environment.

## 5. Open questions

| Question | Owner | What it can affect |
|---|---|---|
| Do `synch_mode` + seeds give byte-identical `.rcg`? | Spike in this change | Option A or fallback B; acceptance criterion 4 wording of the result |
| Is Cyrus seeding worth its patch? | User, after the spike | Only whether Cyrus matches replay exactly |
| Does the local rcssserver tarball differ from the `rcssserver-19.0.0` tag? | Build task in this change | Whether rcssserver needs a build-fix patch |

## 6. Acceptance criteria

1. A fresh checkout plus the build step produces working rcssserver, HELIOS,
   Cyrus and rcg2data binaries from the pinned commits.
2. One CLI command runs N matches for a profile. Each match produces logs, an
   events CSV and a metrics JSON.
3. An A/B experiment with paired seeds produces the JSON and Markdown report
   with CIs, profile hashes and seeds.
4. HELIOS vs HELIOS with the same profile and seed gives byte-identical `.rcg`
   files; if not, the harness records the reproducibility status and the docs
   explain the reason.
5. Noise settings are set in the profile, and a "noise off" preset exists.
6. Unit tests pass. A short-match integration test (a few hundred cycles)
   passes end to end.

## 7. Later changes (context only, not scope)

1. StatsBomb realism comparison (SPADL via socceraction, per-minute scaling).
2. Engine core loop (deterministic, C++).
3. Height system (3D ball, jump, header, dive).
4. Decision layer (Option C, decision traces).
5. Attribute model (attribute-to-mechanism map, drills).
6. Black-box optimizer ("exploit hunter").

## 8. Decisions added in the review of the planning artifacts (2026-10-11)

A source check of rcssserver 19.0.0 found these facts:

- In synch mode, cycles before all 22 players connect take microseconds. The
  default `connect_wait` (300 cycles) ends at once, and auto mode kicks off an
  empty match. The harness must set `connect_wait` very high.
- The server waits at most 1250 ms per cycle for client `(done)` messages.
  After that it logs "Someone missed a cycle" and continues. After 20 missed
  cycles in a row it logs "Waiting too long for clients! Exiting".
- No game-log frames are written before kick-off.
- An unknown parameter makes rcssserver exit with code 1 before it opens its
  port.
- The server logs "player (NAME n) connected." and "online coach (NAME)
  connected." with a flush, so the harness can wait on these lines.

**Q12. Coaches.** Options: coach on, with connection gating; coach off.
**Decision: coach on by default, gated.** The harness starts the right team
only after the left team's 11 players and coach appear in the server log, then
waits for the right team the same way. `kick_off_wait` becomes a reserved
value of 300 cycles, so the last coach has time to connect. If the spike still
shows divergence caused by coaches, the default changes to off.

**Q13. Matches with missed cycles.** Options: keep and count; treat as failed.
**Decision: keep and count.** `run.json` holds `missed_cycles`; the report
shows per arm how many matches had missed cycles.

**Q14. Reproducibility proof in experiments.** Options: replay one seed in
every experiment; separate command only.
**Decision: replay one seed.** After both arms, the experiment replays arm A's
first seed (normal sides) once and compares the game logs. The report shows the
result.

**License field.** `GPL-3.0-or-later` (confirmed by the user).

**Corrections to §4 (minor assumptions).** Two assumptions in §4 changed in
design: all players of a team share one seed (D4), not one seed per player;
and `swap_sides` is an experiment option, not a profile option (D9).

**Correction to §3.2 and §3.5.** Matches run in a thread pool, not a process
pool: each match is a set of subprocesses, so threads only wait. A queue of port
slots keeps two running matches from sharing ports (design D7).
