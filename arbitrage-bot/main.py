#!/usr/bin/env python3
"""Run the multi-market Binance arbitrage scanner + paper trader."""

from __future__ import annotations

import uvicorn

from config import get_settings
from src.api.server import create_app


def main() -> None:
    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
