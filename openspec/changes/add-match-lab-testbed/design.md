## Context

The project will build an FM-style match engine that users can observe and
test, and later a free GPLv3 management game. The first phase uses the RoboCup
2D simulator as a **testbed**: we run existing RoboCup teams and build the
measurement tools. Our own C++ engine comes in later changes, and the same
tools will measure it.

**Current state.** The repo holds only `CLAUDE.md` and the OpenSpec setup.
`openspec/specs/` is empty. The RoboCup code exists only as local builds in
the user's home folder. Those builds compile only because of uncommitted
build fixes:

| Component | Upstream | Pin | Build system | Uncommitted local fixes |
|---|---|---|---|---|
| rcssserver | `rcsoccersim/rcssserver` | release tarball `rcssserver-19.0.0.tar.gz`, SHA-256 `08abeef0...2aea` | autotools | unknown |
| librcsc | `helios-base/librcsc` | `65e1393` | autotools (`--disable-unit-test`) | missing includes; simdjson `static_cast<formatter*>` |
| helios-base | `helios-base/helios-base` | `66fd63d` | autotools (`--with-librcsc`) | none |
| Cyrus librcsc fork | `Cyrus2D/cyrus-soccer-simulation-lib` | `6bafd9b` | CMake | Boost.System fallback; `#include <algorithm>` |
| CppDNN | `Cyrus2D/CppDNN` | `8cb5a55` | headers copied | none |
| Eigen | `gitlab.com/libeigen/eigen` | tag `3.4.0` | headers copied | none |
| Cyrus team | `naderzare/cyrus-soccer-simulation-team` | `335497b` | CMake (fetches RapidJSON at a pinned commit) | Boost.System fallback; `HINTS` for the librcsc search; CppDNN and Eigen search; new `vendor/patch_rapidjson.sh` for GCC 15 |
| rcg2data | `hidehisaakiyama/rcg2data` | `3097064` | CMake | none (not built) |

The machine is aarch64 with GCC 15.2 and Boost 1.90. Boost 1.90 has no
compiled Boost.System library. That is why the CMake files of rcssserver,
librcsc and helios-base fail here, and why the local builds of these three
used autotools. A librcsc build is also installed in `/usr/local`; CMake
`find_library(... PATHS ...)` finds it before any `PATHS` entry.

Checked during planning: rcg2data builds with `-DLIBRCSC_LIB` and
`-DLIBRCSC_INCLUDE_DIR` against librcsc 20 (no Boost dependency), writes its
binary to `build/src/rcg2data`, and writes `<log>.event.csv` next to its
input. The six build-fix patches made from the local diffs apply cleanly to
fresh clones of the pins. The HELIOS player has no RPATH, so its start
script's `LD_LIBRARY_PATH` selects the librcsc.

**Facts that shape the design.**

- A match cannot be reproduced now:
  - rcssserver seeds from the clock. The `random_seed` parameter exists in
    code (`stadium.cpp:182`) but its registration is commented out
    (`serverparam.cpp:962`).
  - librcsc seeds from `std::random_device` (`rcsc/random.h:62`) and from
    `time(0)` (`ann/rbf.cpp`, `ann/ngnet.cpp`).
  - Player commands arrive over UDP in real time.
- rcssserver has `synch_mode`, and both librcsc copies send `(done)`.
- rcssserver already has noise parameters (`ball_rand`, `player_rand`,
  `kick_rand`, visual noise), short-match parameters (`half_time`,
  `nr_normal_halfs`), port parameters (`port`, `coach_port`,
  `olcoach_port`) and log parameters (`game_log_dir`, `game_log_fixed`,
  `game_log_fixed_name`, compression).
- rcg2data reads a `.rcg` (also gzipped) and writes `<basename>.event.csv`
  with the columns `Type, Side1, Unum1, Time1, Mode1, X1, Y1, Side2, Unum2,
  Time2, X2, Y2, Success`. It emits `Pass, Dribble, Shoot, Interception,
  Tackle, Foul, KeeperSave, BallTouch, OutOfBounds, OwnGoal, MultiTouch`.
- A RoboCup match is 6000 cycles (10 minutes of football).

**Constraints.**

- License: the project is GPLv3. Reused code is GPLv3 or LGPLv3.
- Machine: 4 cores and 3 GB RAM. One match runs about 25 processes.
- The harness is Python 3.14 (standard library first). The future engine is
  C++.
- Writing style for docs: simplified technical English.

**Stakeholders.** The project owner (the user) and, later, game users who run
benchmark experiments.

## Goals / Non-Goals

**Goals:**

- Build every testbed component from pinned upstream sources plus repo patch
  files, on a fresh checkout, with one command.
- Run N matches between two teams under a declared TOML profile, with a
  user-controlled seed and noise.
- Make a match reproducible from profile plus seed, or record exactly why it
  is not.
- Extract SPADL events and compute per-match metrics.
- Run paired-seed A/B experiments and report differences with confidence
  intervals.
- Expose a Python API that a later optimizer change can call.

**Non-Goals:**

- Our own engine, the height system, the decision layer, the attribute model.
- Any UI or visualization beyond the existing `rcssmonitor`.
- Comparison with StatsBomb or other real-football data.
- The black-box optimizer, reinforcement learning, sequential stopping.
- Execution across several hosts.
- New event types in rcg2data.

## Decisions

### D1: Build the testbed from pins plus patch files

- **Choice**:
  - A pins file lists each component: a URL plus a full commit hash, a
    tag, or a release tarball with its SHA-256.
  - Patch files live in the repo, grouped per component and ordered by
    number.
  - A build command fetches each pin into an ignored build folder, applies
    the patches with `git apply`, and builds each component with the build
    system that works on this toolchain: autotools for rcssserver, librcsc
    and helios-base; CMake for the Cyrus librcsc fork, the Cyrus team and
    rcg2data. CppDNN and Eigen are header copies.
  - CMake builds get `LIBRCSC_LIB` and `LIBRCSC_INCLUDE_DIR` set directly,
    so `find_library` never picks the `/usr/local` librcsc.
  - Everything installs into prefixes inside the build folder.
  - The build writes a manifest (JSON) with the pins, patch checksums and
    binary paths. The runner reads binary paths only from this manifest.
- **Reason**: the repo stays small and the GPL sources stay upstream.
  Anyone can rebuild the exact testbed. Patches are easy to review in a PR.
- **Alternatives considered**: our own forks as git submodules (upgrades are
  harder to review; patches hide in fork history); use the existing builds
  in `~` (not reproducible on another machine).

### D2: One install prefix per librcsc copy

- **Choice**: install HELIOS librcsc and the Cyrus librcsc fork into
  separate prefixes. Build each team against its own prefix and run it with
  its own library path. Never install into `/usr/local`.
- **Reason**: the two forks share a library name and headers. One shared
  prefix would make one team link the wrong library.
- **Alternative considered**: one system install of librcsc (the Cyrus build
  breaks or silently links the HELIOS librcsc).

### D3: Two patch groups, build fixes and seed patches

- **Choice**:
  - Build-fix patches reproduce the current local diffs, so the pins compile
    with the current toolchain.
  - Seed patches:
    1. rcssserver: register `server::random_seed` again. With a value of 0
       or more, the server, `srand`, `srandom` and `DefaultRNG` use it. The
       seed of the heterogeneous player types follows it when
       `player::random_seed` is not set.
    2. Both librcsc copies: when the environment variable
       `RCSC_RANDOM_SEED` is set, `rcsc/random.h`, `ann/rbf.cpp` and
       `ann/ngnet.cpp` seed from it, and not from `random_device` or the
       clock.
  - Without a seed, all behaviour stays upstream behaviour.
- **Reason**: build fixes and behaviour changes are separate concerns.
  Reviewers can see that the seed patches are the only behaviour change. An
  environment variable reaches every process that a team start script
  launches, without a change to the start scripts.
- **Alternative considered**: a new command-line option in every client
  (needs start-script changes in two teams and more patch surface).

### D4: Seed derivation

- **Choice**:
  - An experiment has a base seed. Match `i` gets
    `match_seed = derive(base_seed, i)`.
  - The server gets `match_seed`.
  - Each team gets `derive(match_seed, side)` through `RCSC_RANDOM_SEED`.
  - `derive` is a fixed hash (SHA-256 of the inputs, truncated to a 31-bit
    non-negative integer).
  - All 11 players of a team share the team seed.
- **Reason**: the derivation is stable across Python versions and platforms.
  Paired A/B arms use the same seed list. Players do not need different
  seeds for determinism.
- **Alternative considered**: Python `random` with a seed (its output can
  change between Python versions).

### D5: Synchronous mode, fixed log names, byte comparison

- **Choice**:
  - Every harness match runs with `server::synch_mode=true`,
    `server::auto_mode=true`, `server::game_log_fixed=true` and a fixed log
    name.
  - Every match also gets `server::connect_wait=100000000` and
    `server::kick_off_wait=300`. In synch mode, cycles before all 22 players
    connect take microseconds, so the default `connect_wait` (300 cycles)
    would end at once and auto mode would kick off an empty match. After the
    22nd player, 300 cycles give the last coach time to connect.
  - The server waits at most 1250 ms per cycle for each client. A slower
    client makes it log "Someone missed a cycle" and continue, which breaks
    reproducibility. The harness counts these lines into `run.json`
    (`missed_cycles`). Such a match still counts in experiments (user
    decision), and the report shows the counts. "Waiting too long for
    clients! Exiting" makes the match status `error`.
  - Every experiment replays arm A's first seed (normal sides) once after
    both arms finish, compares the two game logs, and puts the result in the
    report (user decision). The `check-repro` command does the same for one
    profile and seed.
  - The reproducibility check runs the same profile and seed twice and
    compares the two `.rcg` files byte for byte.
  - If they differ, the check reports the first differing cycle and line.
  - The status is stored in the run record as `identical`, `differs`, or
    `not-checked`.
  - If a difference comes only from a known non-match field (for example a
    header timestamp), the check may skip that field. Each skipped field is
    listed in the report.
- **Reason**: synch mode removes real-time UDP timing from the result. A
  byte comparison is the strictest test that is easy to explain.
- **Alternative considered**: compare only final scores or metrics (hides
  divergence).
- **Fallback (approved)**: if the spike shows that identical replay is not
  possible, the harness still runs. It records `differs` with the reason,
  and reproducibility becomes statistical (same profile, same distribution).
  The docs explain the reason.
- **Spike result (Task 8)**: DIFFERS: class (b), first cycle 1, missed cycles
  0/0 (coaches on) and 0/0 (coaches off, `-C`), coach-off result also
  DIFFERS (first show line at cycle 1 again). Server seed was applied
  (`Using given Simulator Random Seed: 737161366`) and all 22 players and
  both coaches connected in every run. Header lines 3-23 (playmode, params,
  player types) are identical; two non-match fields differ and could be
  skipped: `(server_param` (holds the per-run `game_log_dir`/`text_log_dir`
  paths) and the `(msg N 1 "(result <timestamp> ...` line. After normalizing
  them the logs still diverge from the first `(show 1 ...` line: player
  body/neck angles and command counters (the `(c ...` field) differ before any
  play, so the difference comes from player behaviour before kick-off, not
  from the coaches. Proposed `SKIP_PREFIXES`: `("(server_param", "(msg ")`
  only if the `identical` path is kept; the check still reports `differs`.

### D6: TOML profiles and profile identity

- **Choice**:
  - A profile is a TOML file with: `server` parameters, `player` parameters,
    `match` (halves, half length), and `teams.left` and `teams.right` (a
    team name from the manifest plus options). Noise parameters are server
    parameters. The harness lists them in one constant (`NOISE_PARAMS`), so
    the `noise-off` preset and users can find them. Quantize steps are not
    noise parameters: the server divides by them.
  - Parameters that the harness controls (ports, synch and auto mode,
    `connect_wait`, `kick_off_wait`, seed, log names and folders,
    `game_log_version` (fixed at 6, the ULG6 text format that the parsers
    read), match length) are reserved. A profile that sets one is rejected.
  - rcssserver itself rejects unknown parameter names: it prints an error
    and exits with code 1 before it opens its port. The harness reports this
    with the end of `server.log`.
  - The default profile ends draws after normal time
    (`nr_extra_halfs = 0`, `penalty_shoot_outs = false`). The upstream
    defaults add extra time and penalties, which make matches longer than
    6000 cycles.
  - Profiles may `extends` a base profile. An experiment arm may give
    overrides.
  - The **profile hash** is SHA-256 of the fully resolved profile in a
    canonical form (sorted keys, normalized numbers).
  - Every run folder stores the resolved profile, its hash, the seed and the
    manifest pins.
  - Presets: `default` (upstream server values), `noise-off` (all noise
    parameters 0) and `short` (a few hundred cycles, for tests).
- **Reason**: TOML is readable, and Python 3.14 reads it with `tomllib`
  without a dependency. Hashing the resolved form makes two equal configs
  share a hash, however they were written.
- **Alternatives considered**: YAML (needs a dependency; implicit typing);
  rcssserver `.conf` files (no inheritance; no team section).

### D7: Runner with one process group, one port set and one folder per match

- **Choice**:
  - A match is: start `rcssserver` with the profile parameters, its port set
    and its log folder; start the left team through its start script with
    `-p` and `-P` set to the match ports and `RCSC_RANDOM_SEED` set; wait
    until `server.log` shows its 11 players ("player (NAME n) connected.")
    and, when `coach = true`, its coach ("online coach (NAME) connected.");
    then do the same for the right team. The server flushes these lines.
    The connect timeout is 60 s per team. Coaches are on by default (user
    decision); if the spike shows divergence caused by coaches, the default
    changes to off.
  - The runner waits for the server to exit. In auto mode the server kicks
    off `kick_off_wait` cycles after the 22nd player connects, and exits
    `game_over_wait` cycles after time-over. A timeout guards against stalls.
  - Each match runs in its own process group: the server starts a new
    process group, and the team start scripts join it. The start scripts
    launch players in the background and exit, so the runner kills the
    whole group at the end, on error, on timeout and on cancel.
  - A cancel flag (a `threading.Event`) stops running matches. Ctrl-C in the
    CLI sets it, so no match keeps running in a worker thread. Ctrl-C in the
    main thread (for example during `check-repro`) also gives `cancelled`.
  - The run record keeps both `profile_hash` (the arm's profile) and
    `played_profile_hash` (the profile as played; different in swapped
    matches).
  - The server runs with `HOME` set to a folder inside the run folder.
    rcssserver reads and writes `~/.rcssserver/`, so a user's own server
    config cannot change a harness match.
  - Ports come from a base port plus a stride times the worker slot.
  - A run folder holds: `profile.json` (the resolved profile in canonical
    form; the standard library cannot write TOML), `run.json` (hash, seed,
    pins, status, timings, `missed_cycles`), the compressed `.rcg` and
    `.rcl`, the events CSV and `metrics.json`.
  - Matches run in a thread pool (`concurrent.futures.ThreadPoolExecutor`),
    because the work happens in subprocesses. The default parallelism is 1.
    A queue of port slots makes sure that two running matches never share a
    slot.
- **Reason**: process groups make cleanup reliable when start scripts spawn
  background players. Port slots allow parallel matches without collisions.
- **Alternative considered**: launch each player binary directly (copies
  start-script logic for two teams).

### D8: Metrics from rcg2data events and the `.rcg`

- **Choice**: run `rcg2data` on each `.rcg`. Python then computes per side:
  - goals (from the final `team` record in the `.rcg`) and goal difference;
  - shots (`Shoot`);
  - passes (`Pass`) and pass completion (successful passes / passes);
  - interceptions (`Interception`, counted for `Side2`, the side that won
    the ball) and tackles (`Tackle`, counted for `Side1`);
  - fouls, from `foul_*_l` / `foul_*_r` play modes in the `.rcg`. rcg2data
    defines a `Foul` type but never emits it;
  - an event-based possession share: the side's share of `Pass`, `Dribble`
    and `Shoot` events.

  rcg2data writes sides as `left` / `right` / `neutral` and success as
  `true` / `false`. Experiment reports use the view of the **focus team**
  (the arm profile's left team), also when sides are swapped.

  The metrics JSON has a schema version.
- **Reason**: these metrics use only the events that rcg2data implements.
  The possession share is a proxy and is named as one.
- **Alternative considered**: write our own event extractor (duplicates
  rcg2data; GPLv3 lets us reuse it).

### D9: Paired-seed A/B experiments with bootstrap confidence intervals

- **Choice**:
  - An experiment TOML names two arms (each a profile plus optional
    overrides), the number of matches N, the base seed, and an optional
    `swap_sides` flag (default off).
  - Both arms run the same N match seeds.
  - The primary measure is goal difference from the focus team's view. The
    report gives the mean per arm, the mean paired difference (B minus A)
    and a 95% percentile bootstrap CI for it. The bootstrap uses a fixed
    resample count and a fixed seed, so the report is reproducible.
  - W/D/L rates per arm have Wilson 95% CIs.
  - Secondary metrics get per-arm means.
  - Per arm, the report also shows how many matches had missed cycles.
  - Output: `report.json` and `report.md`, plus the arm profile hashes, the
    seed list and the result of the experiment's replay check (D5).
- **Reason**: pairing removes seed-to-seed variance shared by both arms.
  Goal difference has more statistical power than the win rate. A bootstrap
  needs no distribution assumptions and uses only the standard library.
- **Alternatives considered**: an unpaired t-test (wastes the pairing);
  win rate as the primary measure (lower power).

### D10: Package layout and API

- **Choice**:
  - Python package `matchlab` in `harness/`, with modules for config
    (profiles), testbed (pins, patching, build, manifest), runner, metrics,
    experiment, report and the CLI.
  - CLI subcommands: `build`, `run`, `experiment`, `check-repro`.
  - Public API: `run_experiment(experiment, *, workers=1) -> ExperimentResult`
    and `run_matches(profile, seeds, *, out_dir, workers=1, cancel=None) -> list[MatchResult]`.
  - `run_matches` checks the profile's teams against the manifest before it
    starts any process.
  - Testbed data (pins, patches, presets) lives in `testbed/`. The build
    folder `.testbed/` and the run output folder `runs/` are git-ignored.
  - pytest runs in a project virtual environment.
- **Reason**: small modules with one purpose each. The optimizer change will
  import the API, not the CLI.
- **Alternative considered**: one script (hard to test; no API).

## Risks / Trade-offs

- **[Risk] Synch mode plus seeds still does not give identical logs** (for
  example HELIOS uses wall-clock timing inside a cycle, or the server's
  message order varies). → **Mitigation:** the spike task comes early. The
  fallback in D5 keeps the harness useful, and the user decides about
  further patches.
- **[Risk] The `.rcg` contains run-specific fields** (time stamps, version
  strings). → **Mitigation:** D5 allows a listed set of skipped fields. Each
  one is reported.
- **[Risk] The pinned commits do not build with the current toolchain** in
  ways the local diffs did not show. → **Mitigation:** the build-fix patch
  group exists for this. Each new fix is a numbered patch with a reason line.
- **[Risk] The rcssserver tarball differs from the git tag.** →
  **Mitigation:** the build task compares the two before writing patches.
- **[Risk] Orphan processes after a crash or a timeout** hold ports and RAM.
  → **Mitigation:** process groups, a per-match timeout and cleanup in a
  `finally` block. A port check runs before each match.
- **[Risk] A coach connects after kick-off in one run and before it in
  another.** → **Mitigation:** connection gating per team and a reserved
  `kick_off_wait` of 300 cycles. The spike and every experiment's replay
  check detect any remaining divergence; then the coach default changes to
  off.
  Evidence before apply (2026-10-11): one real short HELIOS vs HELIOS match,
  run through the plan's harness code with the user's local builds (no seed
  patch), had both coaches connect before the kick-off countdown started,
  ran all 600 cycles in 27 s with 0 missed cycles, and left no processes.
- **[Risk] A loaded machine makes clients miss cycles** (1250 ms limit), so
  a match is not reproducible. → **Mitigation:** `missed_cycles` in every
  run record and in the report; default parallelism 1.
- **[Risk] Ctrl-C leaves matches running in worker threads.** →
  **Mitigation:** a cancel flag checked while the runner waits; process
  groups are killed in `finally`.
- **[Risk] 3 GB RAM limits parallelism and statistical power.** →
  **Mitigation:** default parallelism 1. The demo experiment uses short
  matches and a small N. The report always shows CI widths, so weak results
  look weak.
- **[Trade-off] The event-based possession share is a proxy.** Accepted:
  rcg2data gives no ball-control timeline. A later change can compute
  possession from the `.rcg`.
- **[Trade-off] All players of a team share one seed.** Accepted:
  determinism needs fixed seeds, not distinct seeds. Client randomness has
  little effect on play.
- **[Trade-off] Cyrus seeding is best effort.** Accepted: HELIOS vs HELIOS
  is enough to prove reproducibility. Cyrus uses the same mechanism if its
  patch applies cleanly.

## Migration Plan

N/A — this change adds new files only. There is no deployed system, data or
API to migrate. Rollback is a revert of the change commits. The local builds
in `~` stay untouched; the harness never uses them.

## Open Questions

| Question | Owner | What it can affect |
|---|---|---|
| Do synch mode and seeds give byte-identical `.rcg` files for HELIOS vs HELIOS? | Spike done: DIFFERS, class (b), first cycle 1, 0 missed cycles, coaches on and off alike (see D5); user decides identical path or fallback B | D5 status `identical` or the fallback |
| Is Cyrus seeding worth extra patches if its patch does not apply cleanly? | Patch written in Task 4: the same patch as for librcsc applies to the pinned Cyrus librcsc fork. Resolved in Task 7: the built Cyrus fork gives equal first draws with `RCSC_RANDOM_SEED=7` (same value as the HELIOS librcsc) and differing draws without it, so no extra patches are needed | Whether Cyrus matches replay exactly |
| Does the local rcssserver tarball differ from tag `rcssserver-19.0.0`? | Resolved in Task 4: no source differences; the release tarball (SHA-256 `08abeef0...2aea`) matches the local build tree except for generated files (`player_command_parser.*`, `player_command_tok.cpp`, build outputs), so rcssserver needs no build-fix patch | Whether rcssserver needs a build-fix patch |
| Do coaches connect before kick-off in every run? | Spike done: coaches connected in every run (2 connects per run); the coach-off run differs too, so coaches are not the cause; no change of the coach default is indicated (user decision Q12) | Coach default stays on, or changes to off (user decision Q12) |
