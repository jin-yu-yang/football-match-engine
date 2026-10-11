## ADDED Requirements

### Requirement: SPADL event extraction
The harness SHALL run rcg2data on the game log of each finished match. It MUST store the resulting events CSV in the match run folder. If rcg2data fails, the harness MUST record the failure in the run record and MUST NOT write metrics for that match.

#### Scenario: Events are extracted
- **WHEN** a match finishes with status `ok`
- **THEN** the run folder contains an events CSV with the columns `Type, Side1, Unum1, Time1, Mode1, X1, Y1, Side2, Unum2, Time2, X2, Y2, Success`

#### Scenario: Extraction fails
- **WHEN** rcg2data exits with an error
- **THEN** the run record shows an extraction failure
- **AND** the run folder has no metrics file

### Requirement: Per-match metrics
The harness SHALL compute per-match metrics for each side and write them as JSON with a schema version. Goals, goal difference and fouls MUST come from the game log. Shots, passes, pass completion, interceptions, tackles and the possession share MUST come from the events CSV.

#### Scenario: Fouls come from play modes
- **WHEN** the game log contains the play modes `foul_charge_l` and `foul_push_r`
- **THEN** the left side has 1 foul and the right side has 1 foul

### Requirement: Event counting rules
The harness SHALL count `Shoot` rows as shots, `Pass` rows as passes, and `Tackle` rows as tackles, each for the side in `Side1`. It MUST count `Interception` rows for the side in `Side2`, which won the ball. Pass completion MUST be successful passes divided by passes.

#### Scenario: Interception goes to the winning side
- **WHEN** an `Interception` row has `Side1` = `left` and `Side2` = `right`
- **THEN** the right side's interception count increases by 1

#### Scenario: Metrics from a known log
- **WHEN** the harness computes metrics for a fixture game log and its events CSV
- **THEN** the goals equal the final score in the log
- **AND** the pass count equals the number of `Pass` rows for that side
- **AND** pass completion equals successful `Pass` rows divided by all `Pass` rows for that side

#### Scenario: No passes
- **WHEN** a side has no `Pass` events
- **THEN** its pass completion is recorded as null, not as zero or an error

### Requirement: Possession share is labelled as a proxy
The metrics JSON SHALL name the possession measure `event_possession_share`. The two sides' values MUST add up to 1 when at least one counted event exists.

#### Scenario: Shares add up
- **WHEN** a match has at least one `Pass`, `Dribble` or `Shoot` event
- **THEN** the left and right `event_possession_share` values add up to 1
