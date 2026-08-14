"""Dependency-free paper signal and research dashboard server."""

from __future__ import annotations

import hmac
import json
import math
import mimetypes
import os
import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..config import StrategyConfig, load_config
from ..data.csv_feed import read_bars
from ..data.split import chronological_split
from ..models import Decision
from ..monitoring.audit import AuditLogger
from ..research.backtest import BacktestEngine
from ..research.synthetic import generate_synthetic_bars

STATIC_ROOT = Path(__file__).with_name("static")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PINE_PATH = REPOSITORY_ROOT / "tradingview" / "sphinx_signal_indicator.pine"
if not PINE_PATH.exists():
    PINE_PATH = STATIC_ROOT / "sphinx_signal_indicator.pine"


def _thin(values: Sequence[Any], maximum: int) -> list[Any]:
    if len(values) <= maximum:
        return list(values)
    step = max(1, len(values) // maximum)
    thinned = list(values[::step])
    if thinned[-1] != values[-1]:
        thinned.append(values[-1])
    return thinned


def _metric_subset(metrics: dict[str, object]) -> dict[str, object]:
    keys = (
        "trade_count",
        "win_rate",
        "profit_factor",
        "expectancy_per_trade",
        "gross_pnl_before_costs",
        "total_costs",
        "net_pnl_after_costs",
        "maximum_drawdown",
        "maximum_consecutive_losses",
        "average_mae_points",
        "average_mfe_points",
        "by_entry_hour",
        "by_direction",
        "by_regime",
    )
    return {key: metrics.get(key) for key in keys}


def _decision_plan(decision: Decision) -> dict[str, Any] | None:
    if decision.event != "entry_checklist_passed" or not decision.accepted:
        return None
    details = dict(decision.details)
    details["timestamp"] = decision.timestamp.isoformat()
    details["signal_id"] = decision.signal_id
    return details


class DashboardService:
    def __init__(
        self,
        nq_data: str | Path | None = None,
        mnq_data: str | Path | None = None,
        deep_report: str | Path | None = None,
        webhook_log: str | Path | None = None,
    ) -> None:
        self.started_at = datetime.now().astimezone().isoformat()
        self.webhook_token = os.environ.get("SPHINX_WEBHOOK_TOKEN", "")
        self.webhook_events: list[dict[str, Any]] = []
        self.webhook_lock = Lock()
        default_log = Path("artifacts/webhooks/tradingview-alerts.jsonl")
        self.webhook_audit = AuditLogger(webhook_log or default_log)
        nq_config = load_config(REPOSITORY_ROOT / "config" / "baseline.json")
        mnq_config = load_config(REPOSITORY_ROOT / "config" / "mnq.json")
        self.instruments = {
            "NQ": self._load_instrument(nq_config, nq_data),
            "MNQ": self._load_instrument(mnq_config, mnq_data),
        }
        self.deep_report = None
        if deep_report:
            self.deep_report = json.loads(Path(deep_report).read_text(encoding="utf-8"))

    def _load_instrument(
        self, config: StrategyConfig, data_path: str | Path | None
    ) -> dict[str, Any]:
        if data_path:
            bars = read_bars(
                data_path,
                symbol=config.instrument.symbol,
                interval_seconds=config.timeframes.execution_seconds,
            )
            # Respect the locked final holdout: the signal desk replays only the
            # development and validation partitions and never exposes holdout
            # trades or metrics, matching the deep research suite.
            split = chronological_split(
                bars,
                config.research.development_fraction,
                config.research.validation_fraction,
                config.research.holdout_fraction,
                config.research.minimum_bars_per_partition,
            )
            bars = list(split.development) + list(split.validation)
            mode = "USER_PROVIDED_REPLAY_DEV_AND_VALIDATION_ONLY"
            source = str(Path(data_path).resolve())
            holdout_excluded = len(split.holdout)
        else:
            base = generate_synthetic_bars(days=15, seed=44)
            bars = [replace(bar, symbol=config.instrument.symbol) for bar in base]
            mode = "SYNTHETIC_ENGINEERING_DEMO"
            source = "deterministic synthetic fixture — not market data"
            holdout_excluded = 0
        result = BacktestEngine(config).run(bars)
        plans = [plan for decision in result.decisions if (plan := _decision_plan(decision))]
        latest = plans[-1] if plans else None
        latest_timestamp = (
            datetime.fromisoformat(latest["timestamp"]) if latest else bars[-1].timestamp
        )
        age_bars = int(
            (bars[-1].timestamp - latest_timestamp).total_seconds()
            / config.timeframes.execution_seconds
        )
        fresh = latest is not None and 0 <= age_bars <= 2
        # Both historical strategy candidates failed the documented research
        # acceptance gates. Keep displaying their diagnostics, but never present
        # a rejected research event as an actionable paper signal.
        action = "WAIT"
        strategy_status = "RESEARCH_SUSPENDED_NO_VALIDATED_EDGE"

        chart_center = latest_timestamp if latest else bars[-1].timestamp
        center_index = min(
            range(len(bars)),
            key=lambda index: abs((bars[index].timestamp - chart_center).total_seconds()),
        )
        start = max(0, center_index - 55)
        end = min(len(bars), center_index + 55)
        chart_bars = bars[start:end]
        chart_start = chart_bars[0].timestamp
        chart_end = chart_bars[-1].timestamp
        chart_signals = [
            plan
            for plan in plans
            if chart_start <= datetime.fromisoformat(plan["timestamp"]) <= chart_end
        ]
        chart_trades = [
            trade.to_dict()
            for trade in result.trades
            if chart_start <= trade.entry_time <= chart_end
        ]
        recent_signals = list(reversed(plans[-12:]))
        equity = _thin(result.equity_curve, 240)
        return {
            "symbol": config.instrument.symbol,
            "data_mode": mode,
            "data_source": source,
            "holdout_bars_excluded": holdout_excluded,
            "as_of": bars[-1].timestamp.isoformat(),
            "bar_count": len(bars),
            "first_bar": bars[0].timestamp.isoformat(),
            "action": action,
            "strategy_status": strategy_status,
            "fresh": fresh,
            "signal_age_bars": age_bars if latest else None,
            "latest_signal": latest,
            "recent_signals": recent_signals,
            "metrics": _metric_subset(result.metrics),
            "config": {
                "fingerprint": config.fingerprint,
                "session": f"{config.session.start}–{config.session.end} {config.session.timezone}",
                "execution_timeframe": f"{config.timeframes.execution_seconds // 60}m",
                "tick_size": config.instrument.tick_size,
                "point_value": config.instrument.point_value,
                "risk_per_trade_pct": config.risk.risk_per_trade_pct,
                "daily_loss_limit_pct": config.risk.daily_loss_limit_pct,
                "weekly_loss_limit_pct": config.risk.weekly_loss_limit_pct,
                "fixed_stop_ticks": config.setup.fixed_stop_ticks,
                "paper_only": config.paper_only,
            },
            "candles": [bar.to_dict() for bar in chart_bars],
            "chart_signals": chart_signals,
            "chart_trades": chart_trades,
            "equity": [
                {"timestamp": timestamp.isoformat(), "value": value} for timestamp, value in equity
            ],
            "warnings": [
                "AUTOMATED SIGNALS SUSPENDED: no tested strategy passed the research gates.",
                "Displayed setups are rejected mechanical research events, not recommendations.",
                "Dashboard uses completed bars and does not route live orders.",
                "Synthetic demo P&L is not evidence."
                if mode.startswith("SYNTHETIC")
                else "Verify data provenance and rollover before interpretation.",
            ],
        }

    def accept_tradingview_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.webhook_token:
            raise RuntimeError(
                "TradingView webhook intake is disabled until SPHINX_WEBHOOK_TOKEN is set"
            )
        side = str(payload.get("side", "")).upper()
        ticker = str(payload.get("ticker", "")).upper()
        if side not in {"LONG", "SHORT"}:
            raise ValueError("side must be LONG or SHORT")
        symbol = "MNQ" if "MNQ" in ticker else "NQ" if "NQ" in ticker else ""
        if not symbol:
            raise ValueError("ticker must identify NQ or MNQ")
        prices: dict[str, float] = {}
        for key in ("entry", "stop", "tp1", "tp2"):
            try:
                prices[key] = float(payload[key])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be numeric") from exc
            if not math.isfinite(prices[key]) or prices[key] <= 0:
                raise ValueError(f"{key} must be finite and positive")
        ordering_valid = (
            prices["stop"] < prices["entry"] < prices["tp1"] <= prices["tp2"]
            if side == "LONG"
            else prices["stop"] > prices["entry"] > prices["tp1"] >= prices["tp2"]
        )
        if not ordering_valid:
            raise ValueError("entry, stop, and target ordering is invalid")
        event = {
            "received_at": datetime.now(UTC).isoformat(),
            "system": "sphinx",
            "mode": "paper",
            "source": "tradingview",
            "symbol": symbol,
            "ticker": ticker,
            "side": side,
            **prices,
            "status": "RECEIVED_NOT_ROUTED",
        }
        with self.webhook_lock:
            record = self.webhook_audit.write("tradingview_paper_alert", event)
            event["audit_hash"] = record["record_hash"]
            self.webhook_events.append(event)
            self.webhook_events = self.webhook_events[-200:]
        return event

    def webhook_status(self) -> dict[str, Any]:
        with self.webhook_lock:
            return {
                "enabled": bool(self.webhook_token),
                "mode": "RECEIVE_ONLY_NO_ORDER_ROUTING",
                "received_this_run": len(self.webhook_events),
                "latest": self.webhook_events[-1] if self.webhook_events else None,
            }

    def overview(self) -> dict[str, Any]:
        return {
            "name": "Sphinx Signal Desk",
            "mode": "PAPER / RESEARCH ONLY",
            "started_at": self.started_at,
            "instruments": {
                symbol: {
                    key: payload[key]
                    for key in (
                        "symbol",
                        "data_mode",
                        "as_of",
                        "action",
                        "strategy_status",
                        "holdout_bars_excluded",
                        "fresh",
                        "latest_signal",
                        "metrics",
                        "config",
                    )
                }
                for symbol, payload in self.instruments.items()
            },
            "deep_report": self.deep_report,
            "holdout_status": "LOCKED",
            "webhook": self.webhook_status(),
        }

    def instrument(self, symbol: str) -> dict[str, Any]:
        try:
            return self.instruments[symbol.upper()]
        except KeyError as exc:
            raise ValueError(f"unsupported instrument: {symbol}") from exc


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "SphinxDashboard/1.0"

    @property
    def service(self) -> DashboardService:
        return self.server.service  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                self._json({"status": "ok", "mode": "paper_only"})
                return
            if parsed.path == "/api/overview":
                self._json(self.service.overview())
                return
            if parsed.path == "/api/webhooks":
                self._json(self.service.webhook_status())
                return
            if parsed.path.startswith("/api/instrument/"):
                symbol = parsed.path.rsplit("/", 1)[-1]
                self._json(self.service.instrument(symbol))
                return
            if parsed.path == "/api/pine":
                self._json(
                    {
                        "filename": PINE_PATH.name,
                        "code": PINE_PATH.read_text(encoding="utf-8"),
                    }
                )
                return
            self._static(parsed.path)
        except (ValueError, FileNotFoundError) as exc:
            self._json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 — defensive HTTP boundary
            self._json(
                {"error": f"dashboard request failed: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/webhook/tradingview":
            self._json({"error": "unknown endpoint"}, status=HTTPStatus.NOT_FOUND)
            return
        if not self.service.webhook_token:
            self._json(
                {"error": "webhook intake disabled"},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        provided = parse_qs(parsed.query).get("token", [""])[0]
        if not hmac.compare_digest(provided, self.service.webhook_token):
            self._json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65_536:
                raise ValueError("JSON body must be between 1 and 65536 bytes")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise TypeError("JSON payload must be an object")
            event = self.service.accept_tradingview_alert(payload)
            self._json(event, status=HTTPStatus.ACCEPTED)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self._json({"error": str(exc)}, status=HTTPStatus.SERVICE_UNAVAILABLE)

    def _static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        target = (STATIC_ROOT / relative).resolve()
        if STATIC_ROOT.resolve() not in target.parents and target != STATIC_ROOT.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.is_file():
            # Client-side routes fall back to the app shell.
            target = STATIC_ROOT / "index.html"
        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        message = re.sub(r"token=[^& ]+", "token=REDACTED", format % args)
        print(f"[dashboard] {self.address_string()} — {message}")


def serve_dashboard(
    host: str = "0.0.0.0",
    port: int = 8000,
    *,
    nq_data: str | Path | None = None,
    mnq_data: str | Path | None = None,
    deep_report: str | Path | None = None,
    webhook_log: str | Path | None = None,
) -> None:
    service = DashboardService(
        nq_data=nq_data,
        mnq_data=mnq_data,
        deep_report=deep_report,
        webhook_log=webhook_log,
    )
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    server.service = service  # type: ignore[attr-defined]
    print(f"Sphinx Signal Desk listening on http://{host}:{port} — PAPER/RESEARCH ONLY")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
