## Why

We will build a football match engine that users can test, because Football Manager's engine is unbalanced and its users cannot measure it openly. Before we build an engine, we need tools that measure one. The RoboCup 2D simulator and the HELIOS and Cyrus teams already play full matches, so they are our testbed. We can only run those matches by hand now, and a fixed seed does not reproduce a match. This change adds a harness that builds the testbed from pinned sources, runs batches of matches under a declared profile and seed, and reports A/B experiments with confidence intervals. The same tools will later measure our own engine.

## What Changes

- Add a pinned, patched build of the testbed: rcssserver 19.0.0 (release tarball), librcsc, helios-base, the Cyrus team, its librcsc fork and its header dependencies (CppDNN, Eigen 3.4.0), and rcg2data. Pins and patch files live in the repo. The sources stay upstream.
- Add build-fix patches so the pinned commits compile with the current toolchain.
- Add seed patches: enable `server::random_seed` in rcssserver, and let both librcsc copies take a seed. This is a spike. If byte-identical replay fails, the harness records why (fallback: statistical reproducibility).
- Add a Python package and CLI (`matchlab`) that:
  - reads TOML profiles (server and player parameters, noise, teams, match length) and identifies each result by profile hash plus seed;
  - runs N matches in a local thread pool (the matches themselves are subprocesses), with one port set and one run folder per match;
  - extracts SPADL events with rcg2data and computes per-match metrics;
  - runs paired-seed A/B experiments and writes JSON and Markdown reports with bootstrap 95% confidence intervals;
  - checks whether a profile and seed reproduce the same `.rcg`, and in every experiment replays arm A's first seed and reports the result;
  - starts the teams one after the other on the server's connect lines, counts the cycles the server reports as missed, and stops all processes on timeout or Ctrl-C.
- Add a "noise off" profile preset.
- Add a `run_experiment(...)` Python API, which a later optimizer change will call.

## Capabilities

### New Capabilities

- `testbed-build`: build the RoboCup testbed components from pinned upstream commits plus repo patch files, into an isolated build folder.
- `match-runner`: run matches under a TOML profile with a user-controlled seed and noise, store each match in its own run folder, and report whether a match is reproducible.
- `match-metrics`: extract SPADL events from match logs with rcg2data and compute per-match metrics.
- `benchmark-experiments`: run paired-seed A/B experiments over profiles and report per-arm statistics and paired differences with confidence intervals.

### Modified Capabilities

None. `openspec/specs/` is empty.

## Impact

- **New code**: a Python package and its tests; a pins file; patch files for rcssserver, librcsc, the Cyrus team and the Cyrus librcsc fork; TOML profiles.
- **Repo hygiene**: the build folder and run outputs are added to `.gitignore`.
- **External dependencies**: network access to seven upstream Git repositories, the rcssserver release tarball, and RapidJSON (which the Cyrus CMake build fetches at a pinned commit); a C++ toolchain, CMake, autotools (autoconf, automake, libtool), Boost headers, zlib, flex and bison; Python 3.14; pytest as a development dependency.
- **Upstream code changes**: our patches change rcssserver and librcsc behaviour only when a seed is given. Without a seed, behaviour stays upstream behaviour.
- **License**: the project is GPLv3 (a root `LICENSE` file is added). Reused components are GPLv3, LGPLv3, or MPL-2.0 (Eigen), all compatible.
- **Machine limits**: one match runs 25 processes. On the current machine (4 cores, 3 GB RAM) the default parallelism is 1, so demo experiments use a small N.
- **Not affected**: there is no engine code yet. Nothing outside this repo changes.
