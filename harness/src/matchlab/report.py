"""Experiment reports: JSON data and a Markdown summary (no time stamps, so reports are reproducible)."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .experiment import ArmResult, Experiment
from .runner import MatchResult
from .stats import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, bootstrap_mean_ci, mean, wilson_interval

REPORT_SCHEMA = 1
OTHER_METRICS = ("shots", "passes", "pass_completion", "interceptions", "tackles", "fouls",
                 "event_possession_share")


def focus_view(result: MatchResult) -> dict | None:
    """Values from the view of the focus team (the arm profile's left team)."""
    if result.status != "ok" or result.metrics is None:
        return None
    focus, other = ("right", "left") if result.swapped else ("left", "right")
    sides = result.metrics["sides"]
    view = {"goal_difference": sides[focus]["goals"] - sides[other]["goals"]}
    view.update({key: sides[focus][key] for key in OTHER_METRICS})
    return view


def _rate(k: int, n: int) -> dict:
    return {"count": k, "rate": k / n if n else None, "ci95": wilson_interval(k, n)}


def _arm(arm: ArmResult) -> dict:
    views = [v for v in (focus_view(m) for m in arm.matches) if v is not None]
    gd = [v["goal_difference"] for v in views]
    n = len(views)
    return {
        "profile": arm.profile,
        "profile_hash": arm.profile_hash,
        "matches": len(arm.matches),
        "ok": n,
        "failed": dict(sorted(Counter(m.status for m in arm.matches if m.status != "ok").items())),
        "missed_cycles": {"matches": sum(1 for m in arm.matches if m.missed_cycles > 0),
                          "total": sum(m.missed_cycles for m in arm.matches)},
        "goal_difference_mean": mean(gd),
        "win": _rate(sum(1 for x in gd if x > 0), n),
        "draw": _rate(sum(1 for x in gd if x == 0), n),
        "loss": _rate(sum(1 for x in gd if x < 0), n),
        "metrics_mean": {key: mean([v[key] for v in views if v[key] is not None]) for key in OTHER_METRICS},
    }


def build_report(experiment: Experiment, seeds: list[int], arms: dict[str, ArmResult],
                 reproducibility: dict) -> dict:
    by_key = {key: {(m.index, m.swapped): focus_view(m) for m in arm.matches} for key, arm in arms.items()}
    keys = sorted(set(by_key["A"]) | set(by_key["B"]))
    diffs = [by_key["B"][k]["goal_difference"] - by_key["A"][k]["goal_difference"]
             for k in keys if by_key["A"].get(k) is not None and by_key["B"].get(k) is not None]
    return {
        "schema": REPORT_SCHEMA,
        "experiment": experiment.name,
        "base_seed": experiment.base_seed,
        "seeds": list(seeds),
        "swap_sides": experiment.swap_sides,
        "matches_per_arm": len(seeds) * (2 if experiment.swap_sides else 1),
        "focus_team": "the arm profile's left team (also in swapped matches)",
        "arms": {key: _arm(arms[key]) for key in sorted(arms)},
        "paired_goal_difference": {
            "direction": "B minus A",
            "pairs": len(diffs),
            "excluded": len(keys) - len(diffs),
            "mean_difference": mean(diffs),
            "ci95": bootstrap_mean_ci(diffs),
            "method": f"percentile bootstrap, {BOOTSTRAP_RESAMPLES} resamples, seed {BOOTSTRAP_SEED}",
        },
        "reproducibility": dict(reproducibility),
    }


def _num(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _ci(ci) -> str:
    return "n/a" if ci is None else f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def _rate_text(rate: dict) -> str:
    return f"{_num(rate['rate'])} {_ci(rate['ci95'])}"


DIFFERS_NOTE = ("- Note: the replay differs. In the testbed, reproducibility is statistical: the same profile and "
                "seed give the same distribution of results, not the same game log (design D5).")


def _code(text: str) -> str:
    """Wrap text as Markdown inline code, with a fence longer than any backtick run inside it."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def render_markdown(report: dict) -> str:
    paired = report["paired_goal_difference"]
    repro = report["reproducibility"]
    lines = [
        f"# Experiment report: {report['experiment']}",
        "",
        f"- Matches per arm: {report['matches_per_arm']} (swap sides: {'yes' if report['swap_sides'] else 'no'})",
        f"- Base seed: {report['base_seed']}",
        f"- All values use the view of the focus team: {report['focus_team']}.",
        "",
        "## Paired goal difference (B minus A)",
        "",
        f"- Pairs used: {paired['pairs']} (excluded: {paired['excluded']})",
        f"- Mean difference: {_num(paired['mean_difference'])}",
        f"- 95% confidence interval: {_ci(paired['ci95'])} ({paired['method']})",
        "",
        "## Arms",
        "",
        "| Arm | Profile | Hash | OK / total | Missed cycles (matches) | Mean goal difference "
        "| Win (95% CI) | Draw (95% CI) | Loss (95% CI) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key, arm in report["arms"].items():
        lines.append(
            f"| {key} | {arm['profile']} | `{arm['profile_hash']}` | {arm['ok']} / {arm['matches']} | "
            f"{arm['missed_cycles']['matches']} | {_num(arm['goal_difference_mean'])} | {_rate_text(arm['win'])} | "
            f"{_rate_text(arm['draw'])} | {_rate_text(arm['loss'])} |")
    lines += ["", "## Other metrics (mean per match)", "",
              "| Metric | " + " | ".join(report["arms"]) + " |",
              "|---|" + "---|" * len(report["arms"])]
    for metric in OTHER_METRICS:
        lines.append(f"| {metric} | " + " | ".join(_num(a["metrics_mean"][metric]) for a in report["arms"].values())
                     + " |")
    failed = {k: a["failed"] for k, a in report["arms"].items() if a["failed"]}
    lines += ["", "## Failed matches", ""]
    lines += [f"- Arm {k}: " + ", ".join(f"{s}: {c}" for s, c in v.items()) for k, v in failed.items()] or ["- None"]
    lines += ["", "## Reproducibility", "",
              f"- Replayed run: {repro['checked_run']}",
              f"- Result: {repro['status']}"]
    if repro.get("reason"):
        lines.append(f"- Reason: {repro['reason']}")
    if repro["status"] == "differs":
        lines.append(DIFFERS_NOTE)
    if repro.get("first_difference"):
        d = repro["first_difference"]
        cycle = "n/a" if d["cycle"] is None else d["cycle"]
        lines.append(f"- First difference: line {d['line']}, cycle {cycle}")
        if d.get("offset") is not None:
            lines.append(f"- Byte offset: {d['offset']}")
        lines.append(f"- Run a: {_code(d['a'])}")
        lines.append(f"- Run b: {_code(d['b'])}")
    if repro.get("skipped_prefixes"):
        lines.append(f"- Skipped line prefixes: {', '.join(repro['skipped_prefixes'])}")
    lines += ["", "## Seeds", "", ", ".join(str(s) for s in report["seeds"]), ""]
    return "\n".join(lines)


def write_report(out_dir: Path, report: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (out_dir / "report.md").write_text(render_markdown(report))
