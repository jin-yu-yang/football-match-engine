## Purpose

Build the RoboCup 2D testbed (rcssserver, librcsc, HELIOS, the Cyrus team and its librcsc fork, CppDNN, Eigen and rcg2data) from pinned upstream sources plus repository patch files, into an isolated build folder with a manifest.

## ADDED Requirements

### Requirement: Pinned testbed sources
The repository SHALL declare every testbed component in one pins file. Each entry MUST name the upstream URL and one exact reference: a full commit hash, a release tag, or a release tarball with its SHA-256 checksum. The components are rcssserver, librcsc, helios-base, the Cyrus team, the Cyrus librcsc fork, CppDNN, Eigen and rcg2data.

#### Scenario: Every component is pinned
- **WHEN** a developer reads the pins file
- **THEN** each of the eight components has an upstream URL and one exact reference
- **AND** no entry uses a branch name

#### Scenario: Tarball checksum mismatch
- **WHEN** a downloaded tarball does not match the SHA-256 checksum in the pins file
- **THEN** the build stops with an error that names the component

### Requirement: Patches are applied from the repository
The build SHALL apply the patch files stored in the repository for each component, in numeric order, after it checks out the pinned source. Each patch file MUST belong to one group, either build fix or seed, and MUST state its reason in its header. If a patch does not apply cleanly, the build MUST stop with an error that names the patch.

#### Scenario: Patches apply in order
- **WHEN** the build runs for a component that has patch files
- **THEN** it applies them in numeric order to the pinned source

#### Scenario: A patch does not apply
- **WHEN** a patch file does not apply cleanly to the pinned source
- **THEN** the build stops with a non-zero exit status
- **AND** the error message names the component and the patch file

### Requirement: Isolated build output
The build SHALL put sources, build trees and installed files in one build folder that git ignores. It MUST install each librcsc copy into its own prefix. It MUST NOT write outside the build folder.

#### Scenario: Two librcsc copies stay separate
- **WHEN** the build completes
- **THEN** the HELIOS librcsc and the Cyrus librcsc fork are installed in two different prefixes inside the build folder
- **AND** the HELIOS team binary links the HELIOS librcsc
- **AND** the Cyrus team binary links the Cyrus librcsc fork

#### Scenario: Nothing is written outside the build folder
- **WHEN** the build completes
- **THEN** no file outside the build folder was created or changed by the build

### Requirement: One-command build from a fresh checkout
The harness SHALL provide one command that fetches, patches and builds all testbed components from a fresh checkout. When it succeeds, it MUST write a manifest that records each component's pin, the checksum of each applied patch and the paths of the built binaries and team start scripts.

#### Scenario: Fresh build succeeds
- **WHEN** a developer runs the build command in a fresh checkout on a machine with the documented system dependencies
- **THEN** rcssserver, the HELIOS team, the Cyrus team and rcg2data are built
- **AND** the manifest lists their pins, patch checksums and binary paths

#### Scenario: Runner uses only manifest paths
- **WHEN** the runner needs a testbed binary
- **THEN** it takes the path from the manifest
- **AND** it fails with a clear error if the manifest is missing

### Requirement: Seed patches keep upstream behaviour when no seed is given
The seed patches SHALL change behaviour only when a seed is given. rcssserver MUST accept `server::random_seed`. A value of 0 or more MUST seed the simulator random number generators. librcsc and the Cyrus librcsc fork MUST seed their random number generators from the environment variable `RCSC_RANDOM_SEED` when it is set. When no seed is given, all components MUST behave as upstream.

#### Scenario: Server seed is accepted
- **WHEN** rcssserver starts with `server::random_seed=42`
- **THEN** it reports that it uses the given seed 42

#### Scenario: No seed keeps upstream behaviour
- **WHEN** rcssserver starts without `server::random_seed` and the clients start without `RCSC_RANDOM_SEED`
- **THEN** they seed from the clock or the system random device, as upstream does
