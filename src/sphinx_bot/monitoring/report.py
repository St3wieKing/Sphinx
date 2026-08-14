"""Human-readable end-of-day paper reports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from ..models import Decision, Trade


def write_daily_reports(
    directory: str | Path,
    trades: Sequence[Trade],
    decisions: Sequence[Decision],
) -> tuple[Path, ...]:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    by_day: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        by_day[trade.exit_time.date().isoformat()].append(trade)
    signal_details = {
        decision.signal_id: decision.details
        for decision in decisions
        if decision.signal_id and decision.event == "entry_checklist_passed"
    }
    paths: list[Path] = []
    for day, day_trades in sorted(by_day.items()):
        net = sum(trade.net_pnl for trade in day_trades)
        lines = [
            f"# Paper Trading Report — {day}",
            "",
            "> Simulation only. This report is not evidence of live profitability.",
            "",
            f"- Trades: **{len(day_trades)}**",
            f"- Net simulated P&L after modeled costs: **${net:,.2f}**",
            "",
        ]
        for number, trade in enumerate(day_trades, start=1):
            details = signal_details.get(trade.signal_id, {})
            passed = details.get("passed_conditions", []) if isinstance(details, dict) else []
            evidence = details.get("evidence", {}) if isinstance(details, dict) else {}
            lines.extend(
                [
                    f"## Trade {number}: `{trade.signal_id}`",
                    "",
                    "- Market: NQ (configured paper instrument)",
                    f"- Direction: {trade.direction.value}",
                    f"- Entry / exit: {trade.entry_price:.2f} / {trade.average_exit_price:.2f}",
                    f"- Quantity: {trade.quantity}",
                    f"- Gross chart P&L: ${trade.gross_pnl:,.2f}",
                    f"- Execution costs + fees: ${trade.costs:,.2f}",
                    f"- Net P&L: ${trade.net_pnl:,.2f}",
                    f"- Outcome: {trade.exit_reason.value}",
                    f"- MAE / MFE: {trade.mae_points:.2f} / {trade.mfe_points:.2f} points",
                    "",
                    "### Entry checklist",
                    "",
                ]
            )
            lines.extend(f"- {item}" for item in passed)
            if not passed:
                lines.append("- See hash-chained audit log for the complete decision record.")
            lines.extend(["", "### Evidence labels", ""])
            if isinstance(evidence, dict):
                lines.extend(f"- **{key}:** {value}" for key, value in evidence.items())
            lines.append("")
        path = destination / f"{day}.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths.append(path)
    return tuple(paths)
