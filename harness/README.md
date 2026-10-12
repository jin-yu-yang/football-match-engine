# matchlab

matchlab builds the RoboCup 2D testbed from pinned sources, runs seeded matches,
and reports paired A/B experiments. It is the measurement tool for the future
match engine.

## System dependencies

- A C++17 compiler, CMake 3.16 or later, autoconf, automake, libtool
- Boost headers, zlib, flex, bison, Git, curl access to GitHub and GitLab
- Python 3.11.4 or later

## Install

    python3 -m venv harness/.venv
    harness/.venv/bin/pip install -e 'harness[dev]'

## Build the testbed

    harness/.venv/bin/matchlab build --jobs 2

The build fetches each component in `testbed/pins.toml`, applies the patches in
`testbed/patches/<component>/`, and builds everything in `.testbed/`. It writes
nothing outside `.testbed/`. The file `.testbed/manifest.json` records the pins,
the patch checksums and the binary paths.

## Run matches

    harness/.venv/bin/matchlab run --profile short --matches 2 --seed 42 --out runs/try

Each match gets its own folder with `profile.json`, `run.json`, the compressed
game logs, `events.csv` (SPADL events from rcg2data) and `metrics.json`.

Profiles are TOML files in `testbed/profiles/`. Presets: `default`, `noise-off`,
`short`. A profile can extend another profile. The profile hash and the seed
identify a result.

## Run an A/B experiment

    harness/.venv/bin/matchlab experiment testbed/experiments/demo-noise.toml

Both arms play the same seeds. The report gives the paired difference in goal
difference (B minus A) with a 95% bootstrap confidence interval, and win, draw
and loss rates with Wilson intervals. Values use the view of the focus team
(the arm profile's left team).

## Reproducibility

    harness/.venv/bin/matchlab check-repro --profile short --seed 42 --out runs/repro-42

The check runs one match twice and compares the game logs byte for byte.
`check-repro --seed` takes a match seed. `run --seed` and an experiment's
`base_seed` are base seeds: the match seeds derive from them.
Every experiment also replays arm A's first seed once and reports the result.

The harness runs the server in synch mode and starts the teams one after the
other: the right team starts only when the left team's 11 players and coach
have connected. A client that answers too slowly makes the server skip it for
one cycle ("Someone missed a cycle"); such a match is not reproducible.
`run.json` and the report count these missed cycles.

Status: **differs** (statistical reproducibility). The same profile and seed
are expected to give the same distribution of results, not the same game log
(see design note D5 of the OpenSpec change `add-match-lab-testbed`; after
archive it is under `openspec/changes/archive/`). The patched server makes the
start-up identical: every client connects at step 0, and the client commands of the
300 steps before kick-off (steps 0 to 299) are the same in both runs. The
first difference is in the commands of step 300, the first step of play. The
game log has no frames before that, so the check reports the first frame,
`(show 1 ...)` at cycle 1. From there on, the order and timing of client
commands and the server's shared random generator still vary, even with all
noise set to 0. Coaches stay on by default; they are not the cause.
The check skips two line prefixes that hold no play data: `(server_param`
(the run's log folder paths) and `(msg ` (a result line with a time stamp).
Exact replay is planned for our own engine.

## Python API

    from matchlab import load_profile, run_matches, run_experiment
    result = run_experiment("testbed/experiments/demo-noise.toml", workers=1)
    print(result.report["paired_goal_difference"])
