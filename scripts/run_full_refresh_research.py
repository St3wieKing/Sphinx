#!/usr/bin/env python3
"""Convenience wrapper for the holdout-safe refresh research CLI."""

from __future__ import annotations

import sys

from sphinx_bot.cli import main


if __name__ == "__main__":
    arguments = ["refresh-research", *sys.argv[1:]]
    if "--data" not in arguments:
        arguments.extend(["--data", "artifacts/data/nq_2m.csv"])
    raise SystemExit(main(arguments))
