## Purpose

Run seeded RoboCup testbed matches under versioned TOML profiles, with user-controlled seeds and noise, one run folder per match, ordered team connection, reliable process cleanup and a reproducibility check.

## ADDED Requirements

### Requirement: TOML match profiles
The harness SHALL read match profiles from TOML files. A profile MUST be able to set server parameters, player parameters, noise parameters, match length, and the left and right teams. A profile MAY extend a base profile; values in the extending profile MUST override the base values. The harness MUST reject unknown top-level sections and unknown team names with an error that names the problem.

#### Scenario: Profile extends a base profile
- **WHEN** a profile extends a base profile and sets `server.ball_rand = 0`
- **THEN** the resolved profile has `ball_rand = 0`
- **AND** all other values come from the base profile

#### Scenario: Unknown team is rejected
- **WHEN** a profile names a team that is not in the manifest
- **THEN** the harness stops before it starts any process
- **AND** the error names the unknown team

### Requirement: Profile identity
The harness SHALL compute a profile hash as SHA-256 over a canonical form of the resolved profile. Two profiles that resolve to the same values MUST have the same hash, whatever their file layout, key order or inheritance.

#### Scenario: Equal profiles share a hash
- **WHEN** two profile files resolve to the same values with different key order and inheritance
- **THEN** their profile hashes are equal

#### Scenario: Different values give different hashes
- **WHEN** two resolved profiles differ in any value
- **THEN** their profile hashes differ

### Requirement: Profile presets
The harness SHALL ship the presets `default`, `noise-off` and `short`. `noise-off` MUST set every server noise parameter to 0. `short` MUST give a match of at most 600 cycles for tests.

#### Scenario: Noise-off preset
- **WHEN** a user runs a match with the `noise-off` preset
- **THEN** the server starts with every noise parameter set to 0

### Requirement: User-controlled seeds
The harness SHALL derive each match seed deterministically from a base seed and the match index. It MUST pass the match seed to rcssserver as `server::random_seed`. It MUST pass a per-team seed, derived from the match seed and the side, through `RCSC_RANDOM_SEED`. The derivation MUST give the same values on every platform and Python version.

#### Scenario: Same base seed gives same match seeds
- **WHEN** two runs use the same base seed and the same number of matches
- **THEN** both runs use the same list of match seeds

#### Scenario: Seeds reach every process
- **WHEN** a match starts with match seed S
- **THEN** rcssserver receives `server::random_seed=S`
- **AND** every left-team process receives the left-team seed in `RCSC_RANDOM_SEED`
- **AND** every right-team process receives the right-team seed in `RCSC_RANDOM_SEED`

### Requirement: Batch match execution
The harness SHALL run N matches for a profile and a list of seeds, with a configurable number of parallel workers (default 1). Every match MUST run in synchronous mode with its own port set and its own process group. When a match ends, fails or exceeds its timeout, the harness MUST stop all processes of that match.

#### Scenario: Parallel matches do not collide
- **WHEN** two matches run in parallel
- **THEN** they use different server, coach and online-coach ports

#### Scenario: Timeout stops all processes
- **WHEN** a match exceeds its timeout
- **THEN** the harness stops the server and all team processes of that match
- **AND** it records the match status as `timeout`

#### Scenario: Cancel stops all processes
- **WHEN** the user presses Ctrl-C, or an API caller sets the cancel flag, while matches run
- **THEN** the harness stops the server and all team processes of every running match
- **AND** it records those matches with status `cancelled`

### Requirement: Ordered team connection
The harness SHALL start the right team only after the server log shows all 11 left-team players and, when the profile enables the coach, the left-team coach. It MUST then wait the same way for the right team. If a team does not connect within the connect timeout, the match MUST end with status `error` and a message that names the team and the number of connected players.

#### Scenario: Right team waits for the left team
- **WHEN** the left team's players are still connecting
- **THEN** the harness has not yet started the right team

#### Scenario: Team does not connect
- **WHEN** only 9 players of a team connect within the connect timeout
- **THEN** the match status is `error`
- **AND** the error names the team and says 9 of 11 players connected

### Requirement: No kick-off before all players connect
The harness SHALL set the server's `connect_wait`, `kick_off_wait` and `synch_wait_clients` for every match, so that the server does not step or kick off before all 22 players and every enabled coach are connected. `synch_wait_clients` MUST be 22 plus the number of teams whose coach is enabled. Profiles MUST NOT set these three parameters.

#### Scenario: Server waits for every client
- **WHEN** a match starts with both coaches enabled
- **THEN** the server receives `server::synch_wait_clients=24`

#### Scenario: Profile cannot change the kick-off guard
- **WHEN** a profile sets `server.connect_wait`
- **THEN** the harness rejects the profile and names the reserved parameter

### Requirement: Missed cycles are recorded
The harness SHALL count the server's "Someone missed a cycle" lines for each match and store the count in the run record as `missed_cycles`. If the server gives up waiting for clients, the match status MUST be `error`.

#### Scenario: Missed cycles in the run record
- **WHEN** the server reports 2 missed cycles during a match
- **THEN** the run record has `missed_cycles` = 2

### Requirement: Run folder per match
The harness SHALL write each match into its own run folder. The folder MUST contain the resolved profile, a run record and the compressed game and text logs. The run record MUST hold the profile hash, the match seed, the team seeds, the manifest pins, the match status, the missed-cycle count and the reproducibility status.

#### Scenario: Run folder contents
- **WHEN** a match finishes normally
- **THEN** its run folder contains the resolved profile, the run record and the compressed `.rcg` and `.rcl` logs
- **AND** the run record has status `ok`

### Requirement: Reproducibility check
The harness SHALL provide a check that runs one profile and one seed twice and compares the two `.rcg` files byte for byte. The result MUST be `identical` or `differs`. For `differs`, the result MUST name the first differing cycle and line. If the check skips a known non-match field, it MUST list each skipped field in the result. Matches that were not checked MUST have status `not-checked`.

#### Scenario: Identical replay
- **WHEN** the check runs HELIOS against HELIOS twice with the same profile and seed, and the logs are equal
- **THEN** the result is `identical`

#### Scenario: Divergent replay is explained
- **WHEN** the two logs differ
- **THEN** the result is `differs`
- **AND** it names the first differing cycle and line
