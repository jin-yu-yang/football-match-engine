"""Command-line interface: matchlab build | run | experiment | check-repro."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import paths
from .build import BuildContext, BuildError, build_all
from .manifest import ManifestError
from .patches import PatchError
from .pins import COMPONENTS, PinError, load_pins


def _cmd_build(args: argparse.Namespace) -> int:
    ctx = BuildContext(repo=paths.repo_root(), work=paths.work_dir(), jobs=args.jobs)
    manifest = build_all(ctx, load_pins(paths.testbed_dir() / "pins.toml"), only=args.only)
    print(f"Testbed built. Manifest: {paths.manifest_path()}")
    for name, team in sorted(manifest.teams.items()):
        print(f"  team {name}: {team.start}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matchlab", description="Build the RoboCup testbed and run experiments.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="fetch, patch and build the pinned testbed into .testbed/")
    build.add_argument("--jobs", type=int, default=2, help="parallel compile jobs (default 2; 3 GB RAM)")
    build.add_argument("--only", nargs="+", choices=COMPONENTS, help="rebuild only these components")
    build.set_defaults(handler=_cmd_build)
    return parser


ERRORS: tuple[type[Exception], ...] = (PinError, PatchError, BuildError, ManifestError)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
