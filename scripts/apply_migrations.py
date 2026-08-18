#!/usr/bin/env python3
"""Compatibility entry point for the safe, idempotent migration runner.

Prefer:
    python -m scripts.run_migrations
"""

from run_migrations import main


if __name__ == "__main__":
    main()
