## ADDED Requirements

### Requirement: Experiment definition
The harness SHALL read an experiment from a TOML file. The file MUST name two arms (A and B), the number of matches N and a base seed. Each arm MUST be a profile, optionally with overrides. It MAY set `swap_sides`, which defaults to false.

#### Scenario: Arm with overrides
- **WHEN** arm B is the `default` profile with the override `server.player_rand = 0`
- **THEN** arm B's resolved profile equals `default` except for `player_rand`
- **AND** arm B's profile hash differs from the `default` hash

### Requirement: Paired seeds
Both arms of an experiment SHALL run the same list of N match seeds. When `swap_sides` is true, each seed MUST also run with the left and right teams exchanged, in both arms.

#### Scenario: Arms share seeds
- **WHEN** an experiment with N = 10 runs
- **THEN** arm A and arm B each run 10 matches
- **AND** the two arms use the same 10 match seeds

### Requirement: Experiment report
The harness SHALL write an experiment report as JSON and as Markdown. The report MUST include both arms' profile hashes, the seed list, the per-arm statistics, the paired difference, the count of failed, timed-out or cancelled matches per arm, the number of matches with missed cycles per arm, and the result of the experiment's reproducibility check.

#### Scenario: Report contents
- **WHEN** an experiment finishes
- **THEN** `report.json` and `report.md` exist in the experiment folder
- **AND** both contain the arm profile hashes, the seed list, the paired difference and its confidence interval

### Requirement: Experiment statistics
All per-match values in the report SHALL be taken from the view of the focus team, which is the arm profile's left team, also in matches with swapped sides. For each arm, the report MUST give the mean goal difference, the win, draw and loss rates with Wilson 95% confidence intervals, and the means of the other metrics. For the two arms together, it MUST give the mean paired difference in goal difference (B minus A) with a 95% percentile bootstrap confidence interval.

#### Scenario: Per-arm rates have intervals
- **WHEN** an arm has 7 wins, 2 draws and 1 loss in 10 matches
- **THEN** the report gives a win rate of 0.7 with its Wilson 95% interval

### Requirement: Deterministic report
The bootstrap SHALL use a fixed resample count and a fixed seed. The same match results MUST always give the same report.

#### Scenario: Report is reproducible from results
- **WHEN** the report is generated twice from the same match results
- **THEN** the two reports are identical

#### Scenario: Failed matches are excluded from pairs
- **WHEN** a match fails in one arm for seed S
- **THEN** the pair for seed S is excluded from the paired difference
- **AND** the report shows how many pairs were excluded

### Requirement: Python experiment API
The harness SHALL expose `run_experiment` and `run_matches` as a Python API. The CLI MUST use the same functions. `run_experiment` MUST return the experiment result as a Python object that holds the per-match metrics and the report values.

#### Scenario: API and CLI agree
- **WHEN** the same experiment runs once through the CLI and once through `run_experiment`, with results that replay identically
- **THEN** both produce the same report values

### Requirement: Experiment reproducibility check
After both arms finish, the harness SHALL replay arm A's first match (the first seed, normal sides) once and compare the two game logs byte for byte. The report MUST show the result: `identical`, `differs` with the first differing line and cycle, or `not-checked` with the reason when the original match or the replay did not finish.

#### Scenario: Replay is identical
- **WHEN** an experiment finishes and the replay of arm A's first match gives the same game log
- **THEN** the report's reproducibility result is `identical`

#### Scenario: Original match failed
- **WHEN** arm A's first match ended with status `error` or `timeout`
- **THEN** the report's reproducibility result is `not-checked`
- **AND** the report gives the reason
