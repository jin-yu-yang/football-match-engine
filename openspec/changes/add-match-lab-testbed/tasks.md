## 1. Repository scaffold

- [x] 1.1 Add `.testbed/`, `runs/` and the Python virtual environment folder to `.gitignore`
- [x] 1.2 Create the `harness/` Python package `matchlab` (`pyproject.toml`, `src/matchlab/__init__.py`, `tests/`) with pytest as a development dependency, and confirm `pytest` runs an empty suite in a project virtual environment
- [x] 1.3 Create the `testbed/` folder layout: `pins.toml`, `patches/<component>/`, `profiles/`
- [x] 1.4 Add the GPLv3 text as the root `LICENSE` file

## 2. Pinned testbed build (testbed-build)

- [x] 2.1 Write `testbed/pins.toml` with the URL and exact reference of rcssserver (release tarball + SHA-256), librcsc, helios-base, the Cyrus librcsc fork, CppDNN, Eigen (`3.4.0`), the Cyrus team and rcg2data; add a loader with tests that reject branch names and missing fields
- [x] 2.2 Check that the rcssserver release tarball matches the pinned SHA-256 and that its `src/` equals the local `~/rcssserver-19.0.0/src` (except build output); record the result (needed patch or none)
- [x] 2.3 Capture the local build fixes as numbered build-fix patch files with reason headers: librcsc (includes, simdjson), Cyrus team (CMake Boost fallback, librcsc `HINTS`, CppDNN and Eigen search, RapidJSON patch script), Cyrus librcsc fork (CMake Boost fallback, `<algorithm>`)
- [x] 2.4 Implement patch application in numeric order with `git apply`, stopping with an error that names the component and patch; test with a temporary git repository
- [x] 2.5 Implement the build command: fetch each pin into `.testbed/src/`, apply patches, build rcssserver, librcsc and helios-base with autotools and the Cyrus librcsc fork, Cyrus team and rcg2data with CMake, copy CppDNN and Eigen headers, install each librcsc copy into its own prefix, and pass the matching librcsc paths to every dependent build
- [x] 2.6 Write the manifest (pins, patch checksums, binary and start-script paths) and a loader that fails clearly when the manifest is missing
- [x] 2.7 Run the full build once, in the background, in the apply worktree (a fresh checkout), with build-fix and seed patches in place; confirm that each team binary links its own librcsc (`ldd`) and that nothing outside `.testbed/` changed

## 3. Seed patches and reproducibility spike

- [x] 3.1 Add the rcssserver seed patch that registers `server::random_seed` again; confirm that the server prints the given seed
- [x] 3.2 Add the librcsc seed patch (`RCSC_RANDOM_SEED` for `random.h`, `ann/rbf.cpp`, `ann/ngnet.cpp`) and the same patch for the Cyrus librcsc fork if it applies; record the Cyrus outcome
- [x] 3.3 Confirm that without a seed, the server and clients still seed from the clock or random device
- [x] 3.4 Spike: run HELIOS vs HELIOS twice with a short match, synch mode, fixed log name and the same seeds; compare the `.rcg` files byte for byte and record the result, the first difference if any, and any non-match fields to skip
- [x] 3.5 Decide with the user: `identical` path, or fallback B (statistical reproducibility); record the decision in `design.md` Open Questions
- [x] 3.6 Bounded follow-up approved by the user: add the rcssserver `synch_wait_clients` hold patch, rebuild, and run a second spike; record the result (still differs: fallback B, hold patch kept)

## 4. Profiles (match-runner)

- [x] 4.1 Implement the TOML profile loader with `extends`, overrides and validation of top-level sections and team names (tests first)
- [x] 4.2 Implement the canonical form and SHA-256 profile hash; test equal-values-equal-hash and different-values-different-hash
- [x] 4.3 Add the `default`, `noise-off` and `short` presets; test that `noise-off` zeroes every server noise parameter and `short` is at most 600 cycles
- [x] 4.4 Implement the mapping from a resolved profile to rcssserver command-line parameters and team start options

## 5. Match runner (match-runner)

- [x] 5.1 Implement the deterministic seed derivation (SHA-256, 31-bit) for match seeds and per-side team seeds; test with fixed expected values
- [x] 5.2 Implement port-slot allocation and a free-port check before each match
- [x] 5.3 Implement single-match execution: start the server with the reserved `connect_wait` and `kick_off_wait`; start the left team, wait until its 11 players (and coach) appear in the server log, then do the same for the right team; wait for the server to exit; stop the process group on finish, error, timeout or cancel; count missed cycles
- [x] 5.4 Implement the run folder and run record (resolved profile, hash, seeds, pins, status, timings, reproducibility status) and log compression
- [x] 5.5 Implement `run_matches` with a thread pool and port-slot queue (default 1 worker) and a cancel flag that Ctrl-C sets
- [x] 5.6 Implement the reproducibility check (run twice, byte compare, report first differing cycle and line, list skipped fields)

## 6. Match metrics (match-metrics)

- [x] 6.1 Implement the rcg2data call and failure recording; the events CSV goes into the run folder
- [x] 6.2 Implement the final-score parser for `.rcg` files and the events CSV parser
- [x] 6.3 Implement per-side metrics (goals, goal difference, shots, passes, pass completion with null for no passes, interceptions by `Side2`, tackles, fouls from play modes, `event_possession_share`) and the versioned metrics JSON; test with a fixture log and a hand-made events CSV

## 7. Benchmark experiments (benchmark-experiments)

- [ ] 7.1 Implement the experiment TOML loader (two arms, overrides, N, base seed, `swap_sides`)
- [ ] 7.2 Implement paired execution of both arms with the same seeds, including `swap_sides`, and exclusion of failed pairs
- [x] 7.3 Implement the statistics: per-arm means, Wilson 95% intervals for W/D/L, mean paired goal-difference delta with a seeded 95% percentile bootstrap; test against known values
- [ ] 7.4 Implement `report.json` and `report.md`; test that the same results give identical reports
- [ ] 7.5 Implement `run_experiment` returning the result object
- [ ] 7.6 After both arms, replay arm A's first seed and put the reproducibility result in the report; report missed-cycle counts per arm

## 8. CLI and end-to-end checks

- [ ] 8.1 Implement the CLI subcommands `build`, `run`, `experiment` and `check-repro` on top of the API
- [ ] 8.2 Add an integration test (marked, skipped when the manifest is missing) that runs a `short` HELIOS vs HELIOS match end to end and checks the run folder, events CSV and metrics JSON
- [ ] 8.3 Run a demo A/B experiment (`default` vs `noise-off`, short matches, small N) and check the report contents
- [ ] 8.4 Write `harness/README.md` in simplified technical English: system dependencies, build, run, experiment, reproducibility status and its reason
