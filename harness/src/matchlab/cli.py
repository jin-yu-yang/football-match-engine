"""Command-line interface: matchlab build | run | experiment | check-repro."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import paths
from .build import BuildContext, BuildError, build_all
from .experiment import ExperimentError, run_experiment
from .manifest import Manifest, ManifestError, load_manifest
from .patches import PatchError
from .pins import COMPONENTS, PinError, load_pins
from .ports import PortInUseError
from .profile import Profile, ProfileError, load_profile
from .repro import ReproError, check_reproducibility
from .runner import run_matches
from .seeds import match_seeds


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def _positive_float(text: str) -> float:
    value = float(text)
    if not value > 0:  # also rejects nan
        raise argparse.ArgumentTypeError("must be greater than 0")
    return value


def _cmd_build(args: argparse.Namespace) -> int:
    ctx = BuildContext(repo=paths.repo_root(), work=paths.work_dir(), jobs=args.jobs)
    manifest = build_all(ctx, load_pins(paths.testbed_dir() / "pins.toml"), only=args.only)
    print(f"Testbed built. Manifest: {paths.manifest_path()}")
    for name, team in sorted(manifest.teams.items()):
        print(f"  team {name}: {team.start}")
    return 0


def _profile_for_testbed(ref: str) -> tuple[Profile, Manifest]:
    load_profile(ref)  # report profile errors before touching the testbed
    manifest = load_manifest()
    return load_profile(ref, known_teams=manifest.teams.keys()), manifest


def _cmd_run(args: argparse.Namespace) -> int:
    profile, manifest = _profile_for_testbed(args.profile)
    results = run_matches(profile, match_seeds(args.seed, args.matches), out_dir=args.out, manifest=manifest,
                          workers=args.workers, timeout_s=args.timeout, swap_sides=args.swap_sides)
    for r in results:
        gd = r.metrics["sides"]["left"]["goal_difference"] if r.metrics else "n/a"
        print(f"{r.run_dir.name}: {r.status} (seed {r.match_seed}, left goal difference {gd}, "
              f"missed cycles {r.missed_cycles})")
    return 0 if all(r.status == "ok" for r in results) else 1


def _cmd_experiment(args: argparse.Namespace) -> int:
    result = run_experiment(args.file, out_dir=args.out, workers=args.workers)
    paired = result.report["paired_goal_difference"]
    repro = result.report["reproducibility"]
    print(f"Paired goal difference (B minus A): {paired['mean_difference']} "
          f"95% CI {paired['ci95']} over {paired['pairs']} pairs")
    print(f"Reproducibility ({repro['checked_run']} replayed): {repro['status']}")
    print(f"Report: {result.out_dir / 'report.md'}")
    return 0


def _cmd_check_repro(args: argparse.Namespace) -> int:
    profile, manifest = _profile_for_testbed(args.profile)
    result = check_reproducibility(profile, args.seed, args.out, manifest, timeout_s=args.timeout)
    print(f"Reproducibility: {result.status}")
    if result.first_difference:
        d = result.first_difference
        print(f"First difference at line {d['line']} (cycle {d['cycle']}):\n  a: {d['a']}\n  b: {d['b']}")
    if result.skipped:
        print(f"Skipped line prefixes: {', '.join(result.skipped)}")
    return 0 if result.status == "identical" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matchlab", description="Build the RoboCup testbed and run experiments.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="fetch, patch and build the pinned testbed into .testbed/")
    build.add_argument("--jobs", type=_positive_int, default=2, help="parallel compile jobs (default 2; 3 GB RAM)")
    build.add_argument("--only", nargs="+", choices=COMPONENTS, help="rebuild only these components")
    build.set_defaults(handler=_cmd_build)

    run = sub.add_parser("run", help="run N matches for one profile")
    run.add_argument("--profile", required=True, help="preset name or path to a profile TOML file")
    run.add_argument("--matches", type=_positive_int, default=1)
    run.add_argument("--seed", type=int, required=True, help="base seed; match seeds derive from it")
    run.add_argument("--out", type=Path, required=True, help="output folder for the run folders")
    run.add_argument("--workers", type=_positive_int, default=1)
    run.add_argument("--timeout", type=_positive_float, default=3600.0, help="seconds per match")
    run.add_argument("--swap-sides", action="store_true", help="also play each seed with the teams exchanged")
    run.set_defaults(handler=_cmd_run)

    exp = sub.add_parser("experiment", help="run a paired A/B experiment from a TOML file")
    exp.add_argument("file", type=Path)
    exp.add_argument("--out", type=Path, default=None, help="output folder (default runs/<name>)")
    exp.add_argument("--workers", type=_positive_int, default=1)
    exp.set_defaults(handler=_cmd_experiment)

    rep = sub.add_parser("check-repro", help="run one match twice and compare the game logs")
    rep.add_argument("--profile", required=True)
    rep.add_argument("--seed", type=int, required=True, help="the match seed")
    rep.add_argument("--out", type=Path, required=True)
    rep.add_argument("--timeout", type=_positive_float, default=3600.0)
    rep.set_defaults(handler=_cmd_check_repro)
    return parser


ERRORS: tuple[type[Exception], ...] = (PinError, PatchError, BuildError, ManifestError, ProfileError,
                                       ExperimentError, ReproError, PortInUseError, FileExistsError)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # run_matches has already stopped every running match before the interrupt reaches here.
        print("cancelled: all match processes were stopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
