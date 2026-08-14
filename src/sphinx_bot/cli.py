"""Command-line interface for validation, research, stress, and paper replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .data.csv_feed import inspect_data, read_bars
from .data.importers import (
    PUBLIC_DATASETS,
    download_public_dataset,
    normalize_external_data,
)
from .data.split import chronological_split
from .execution.paper_trader import PaperTrader
from .monitoring.audit import AuditLogger, json_safe, verify_chain
from .research.backtest import BacktestEngine
from .research.deep import DeepResearchSuite, paired_instrument_summary
from .research.experiments import ExperimentLedger
from .research.monte_carlo import MonteCarloConfig, run_monte_carlo
from .research.refresh import run_refresh_research
from .research.stress import run_execution_scenarios
from .research.synthetic import generate_synthetic_bars, write_bars_csv
from .web.server import serve_dashboard


def _write_json(path: str | Path, value: object) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return destination


def _load_partition(args: argparse.Namespace):
    config = load_config(args.config)
    bars = read_bars(
        args.data,
        symbol=config.instrument.symbol,
        interval_seconds=config.timeframes.execution_seconds,
    )
    split = chronological_split(
        bars,
        config.research.development_fraction,
        config.research.validation_fraction,
        config.research.holdout_fraction,
        config.research.minimum_bars_per_partition,
    )
    selected = split.get(
        args.partition,
        strategy_frozen=config.research.strategy_frozen,
        allow_holdout=getattr(args, "allow_holdout", False),
    )
    return config, selected


def command_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(json.dumps({"valid": True, "fingerprint": config.fingerprint}, indent=2))
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    bars = read_bars(
        args.data,
        symbol=config.instrument.symbol,
        interval_seconds=config.timeframes.execution_seconds,
        strict_interval=False,
    )
    report = inspect_data(
        bars,
        expected_interval_seconds=config.timeframes.execution_seconds,
        max_gap_seconds=config.execution.max_data_gap_seconds,
    )
    print(json.dumps(json_safe(report), indent=2, sort_keys=True))
    return 0 if report.valid else 2


def command_generate_demo(args: argparse.Namespace) -> int:
    bars = generate_synthetic_bars(args.days, args.seed)
    path = write_bars_csv(args.output, bars)
    print(f"Wrote {len(bars)} synthetic engineering-only bars to {path}")
    return 0


def command_backtest(args: argparse.Namespace) -> int:
    config, bars = _load_partition(args)
    output = Path(args.output)
    audit = AuditLogger(output.with_suffix(output.suffix + ".audit.jsonl"))
    secondary = None
    if args.secondary_data:
        secondary_bars = read_bars(
            args.secondary_data,
            symbol="ES",
            interval_seconds=config.timeframes.execution_seconds,
        )
        secondary = {bar.timestamp: bar for bar in secondary_bars}
    result = BacktestEngine(config, audit).run(bars, secondary_bars=secondary)
    _write_json(output, result.to_dict())
    print(
        json.dumps(
            {
                "partition": args.partition,
                "bars": len(bars),
                "trades": len(result.trades),
                "net_pnl": result.metrics["net_pnl_after_costs"],
                "output": str(output),
                "warning": "Historical simulation is not a profitability claim.",
            },
            indent=2,
        )
    )
    return 0


def command_stress(args: argparse.Namespace) -> int:
    config, bars = _load_partition(args)
    results = run_execution_scenarios(config, bars)
    summary = {
        name: {
            "config_fingerprint": result.config_fingerprint,
            "metrics": result.metrics,
            "kill_switches": result.kill_switches,
        }
        for name, result in results.items()
    }
    _write_json(args.output, summary)
    print(json.dumps({"output": args.output, "scenarios": list(summary)}, indent=2))
    return 0


def command_monte_carlo(args: argparse.Namespace) -> int:
    config, bars = _load_partition(args)
    backtest = BacktestEngine(config).run(bars)
    if not backtest.trades:
        raise ValueError("selected partition produced no trades; Monte Carlo is undefined")
    mc = run_monte_carlo(
        backtest.trades,
        initial_equity=config.risk.initial_equity,
        tick_size=config.instrument.tick_size,
        point_value=config.instrument.point_value,
        config=MonteCarloConfig(
            simulations=args.simulations,
            missed_trade_probability=args.missed_trade_probability,
            extra_slippage_ticks_max=args.extra_slippage_ticks,
            cost_multiplier=args.cost_multiplier,
            ruin_drawdown_fraction=args.ruin_drawdown,
            seed=config.research.random_seed,
        ),
    )
    payload = {
        "backtest_metrics": backtest.metrics,
        "monte_carlo": mc.to_dict(),
        "warning": "Resampled historical outcomes are not forecasts or guarantees.",
    }
    _write_json(args.output, payload)
    print(json.dumps({"output": args.output, "simulations": args.simulations}, indent=2))
    return 0


def command_paper(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    bars = read_bars(
        args.data,
        symbol=config.instrument.symbol,
        interval_seconds=config.timeframes.execution_seconds,
    )
    trader = PaperTrader(config, args.output_directory)
    result = trader.replay(bars)
    print(
        json.dumps(
            {
                "mode": "PAPER_REPLAY_ONLY",
                "run_directory": str(trader.run_directory),
                "trades": len(result.trades),
                "net_simulated_pnl": result.metrics["net_pnl_after_costs"],
            },
            indent=2,
        )
    )
    return 0


def command_verify_audit(args: argparse.Namespace) -> int:
    valid, count, error = verify_chain(args.audit)
    print(json.dumps({"valid": valid, "records": count, "error": error}, indent=2))
    return 0 if valid else 2


def command_experiment(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ledger = ExperimentLedger(args.ledger)
    parameters = json.loads(args.parameters)
    ledger.append(
        experiment_id=args.id,
        hypothesis=args.hypothesis,
        parameters_changed=parameters,
        reason=args.reason,
        config_fingerprint=config.fingerprint,
        decision=args.decision,
        strategy_frozen_before_holdout=config.research.strategy_frozen,
        notes=args.notes,
    )
    print(json.dumps({"recorded": args.id, "ledger": args.ledger}, indent=2))
    return 0


def command_download_data(args: argparse.Namespace) -> int:
    manifest = download_public_dataset(args.dataset, args.destination)
    print(json.dumps(json_safe(manifest), indent=2, sort_keys=True))
    return 0


def command_normalize_data(args: argparse.Namespace) -> int:
    manifest = normalize_external_data(
        args.source,
        args.output,
        symbol=args.symbol,
        source_timezone=args.source_timezone,
        source_interval_seconds=args.source_interval_seconds,
        target_interval_seconds=120,
        provenance={"operator_note": args.provenance_note},
    )
    print(json.dumps(json_safe(manifest), indent=2, sort_keys=True))
    return 0


def command_deep_backtest(args: argparse.Namespace) -> int:
    inputs = {"NQ": args.nq_data, "MNQ": args.mnq_data}
    if not any(inputs.values()):
        raise ValueError("provide --nq-data and/or --mnq-data")
    config_paths = {
        "NQ": Path(args.nq_config),
        "MNQ": Path(args.mnq_config),
    }
    reports: dict[str, dict[str, object]] = {}
    for symbol, data_path in inputs.items():
        if not data_path:
            continue
        config = load_config(config_paths[symbol])
        bars = read_bars(
            data_path,
            symbol=symbol,
            interval_seconds=config.timeframes.execution_seconds,
        )
        reports[symbol] = DeepResearchSuite(
            config,
            bootstrap_simulations=args.bootstrap_simulations,
        ).run(bars)
    payload = {
        "status": "RESEARCH_ONLY_NO_PROFITABILITY_CLAIM",
        "reports": reports,
        "paired_summary": paired_instrument_summary(reports),
        "holdout_opened": False,
    }
    _write_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": args.output,
                "instruments": list(reports),
                "holdout_opened": False,
                "warning": "Review validation, sensitivity and stress evidence; no automatic winner is selected.",
            },
            indent=2,
        )
    )
    return 0


def command_refresh_research(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    bars = read_bars(
        args.data,
        symbol=config.instrument.symbol,
        interval_seconds=config.timeframes.execution_seconds,
    )
    split = chronological_split(
        bars,
        config.research.development_fraction,
        config.research.validation_fraction,
        config.research.holdout_fraction,
        config.research.minimum_bars_per_partition,
    )
    report = run_refresh_research(
        list(split.development), list(split.validation), config
    )
    report["dataset"] = {
        "total_bars": len(bars),
        "development_bars": len(split.development),
        "validation_bars": len(split.validation),
        "holdout_bars_excluded": len(split.holdout),
        "first_timestamp": bars[0].timestamp.isoformat(),
        "last_timestamp": bars[-1].timestamp.isoformat(),
        "config_fingerprint": config.fingerprint,
    }
    _write_json(args.output, report)
    print(
        json.dumps(
            {
                "output": args.output,
                "development_events": report["protocol"]["development_events"],
                "validation_events": report["protocol"]["validation_events"],
                "holdout_opened": False,
                "selected_strategy": "NONE",
            },
            indent=2,
        )
    )
    return 0


def command_dashboard(args: argparse.Namespace) -> int:
    serve_dashboard(
        host=args.host,
        port=args.port,
        nq_data=args.nq_data,
        mnq_data=args.mnq_data,
        deep_report=args.deep_report,
        webhook_log=args.webhook_log,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sphinx",
        description="Evidence-labelled trading research platform (signals suspended)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-config")
    validate.add_argument("--config", default="config/baseline.json")
    validate.set_defaults(function=command_validate)

    inspect = subparsers.add_parser("inspect-data")
    inspect.add_argument("--config", default="config/baseline.json")
    inspect.add_argument("--data", required=True)
    inspect.set_defaults(function=command_inspect)

    demo = subparsers.add_parser("generate-demo")
    demo.add_argument("--output", default="artifacts/synthetic.csv")
    demo.add_argument("--days", type=int, default=15)
    demo.add_argument("--seed", type=int, default=44)
    demo.set_defaults(function=command_generate_demo)

    def add_research_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--config", default="config/baseline.json")
        command.add_argument("--data", required=True)
        command.add_argument(
            "--partition", choices=("development", "validation", "holdout"), default="development"
        )
        command.add_argument("--allow-holdout", action="store_true")

    backtest = subparsers.add_parser("backtest")
    add_research_arguments(backtest)
    backtest.add_argument("--secondary-data", help="synchronized ES CSV for optional SMT context")
    backtest.add_argument("--output", default="artifacts/backtest.json")
    backtest.set_defaults(function=command_backtest)

    stress = subparsers.add_parser("stress")
    add_research_arguments(stress)
    stress.add_argument("--output", default="artifacts/stress.json")
    stress.set_defaults(function=command_stress)

    monte = subparsers.add_parser("monte-carlo")
    add_research_arguments(monte)
    monte.add_argument("--simulations", type=int, default=2000)
    monte.add_argument("--missed-trade-probability", type=float, default=0.10)
    monte.add_argument("--extra-slippage-ticks", type=float, default=2.0)
    monte.add_argument("--cost-multiplier", type=float, default=1.25)
    monte.add_argument("--ruin-drawdown", type=float, default=0.20)
    monte.add_argument("--output", default="artifacts/monte_carlo.json")
    monte.set_defaults(function=command_monte_carlo)

    paper = subparsers.add_parser("paper")
    paper.add_argument("--config", default="config/baseline.json")
    paper.add_argument("--data", required=True, help="completed-bar CSV replay feed")
    paper.add_argument("--output-directory", default="artifacts")
    paper.set_defaults(function=command_paper)

    audit = subparsers.add_parser("verify-audit")
    audit.add_argument("--audit", required=True)
    audit.set_defaults(function=command_verify_audit)

    experiment = subparsers.add_parser("record-experiment")
    experiment.add_argument("--config", default="config/baseline.json")
    experiment.add_argument("--ledger", default="research/experiments.jsonl")
    experiment.add_argument("--id", required=True)
    experiment.add_argument("--hypothesis", required=True)
    experiment.add_argument("--reason", required=True)
    experiment.add_argument("--parameters", default="{}", help="JSON object")
    experiment.add_argument("--decision", default="pending")
    experiment.add_argument("--notes", default="")
    experiment.set_defaults(function=command_experiment)

    download = subparsers.add_parser("download-research-data")
    download.add_argument("--dataset", choices=tuple(PUBLIC_DATASETS), required=True)
    download.add_argument("--destination", default="artifacts/external-data")
    download.set_defaults(function=command_download_data)

    normalize = subparsers.add_parser("normalize-data")
    normalize.add_argument("--source", required=True)
    normalize.add_argument("--output", required=True)
    normalize.add_argument("--symbol", choices=("NQ", "MNQ"), required=True)
    normalize.add_argument("--source-timezone", default="America/New_York")
    normalize.add_argument("--source-interval-seconds", type=int, default=60)
    normalize.add_argument("--provenance-note", default="")
    normalize.set_defaults(function=command_normalize_data)

    deep = subparsers.add_parser("deep-backtest")
    deep.add_argument("--nq-data")
    deep.add_argument("--mnq-data")
    deep.add_argument("--nq-config", default="config/baseline.json")
    deep.add_argument("--mnq-config", default="config/mnq.json")
    deep.add_argument("--bootstrap-simulations", type=int, default=2000)
    deep.add_argument("--output", default="artifacts/deep_research.json")
    deep.set_defaults(function=command_deep_backtest)

    refresh = subparsers.add_parser("refresh-research")
    refresh.add_argument("--config", default="config/baseline.json")
    refresh.add_argument("--data", required=True)
    refresh.add_argument("--output", default="artifacts/full_refresh_research.json")
    refresh.set_defaults(function=command_refresh_research)

    dashboard = subparsers.add_parser("dashboard")
    dashboard.add_argument("--host", default="0.0.0.0")
    dashboard.add_argument("--port", type=int, default=8000)
    dashboard.add_argument("--nq-data")
    dashboard.add_argument("--mnq-data")
    dashboard.add_argument("--deep-report")
    dashboard.add_argument("--webhook-log", default="artifacts/webhooks/tradingview-alerts.jsonl")
    dashboard.set_defaults(function=command_dashboard)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.function(args))
    except (ValueError, TypeError, PermissionError, FileNotFoundError, ConnectionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
