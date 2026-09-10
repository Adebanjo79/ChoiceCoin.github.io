from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    paper_trading: bool = True
    starting_capital_usd: float = 68.0
    binance_api_key: str = ""
    binance_api_secret: str = ""

    # Net edge after ~0.1% taker fee per leg (~30 bps for 3-leg triangle).
    min_edge_bps: float = 8.0
    max_position_usd: float = 25.0

    scan_symbols: str = Field(
        default=(
            "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,"
            "DOTUSDT,LINKUSDT,POLUSDT,LTCUSDT,ATOMUSDT,UNIUSDT,NEARUSDT,APTUSDT,"
            "ARBUSDT,OPUSDT,SUIUSDT,INJUSDT,TIAUSDT,SEIUSDT,WLDUSDT,PEPEUSDT,SHIBUSDT,"
            "ETHBTC,BNBBTC,SOLBTC,XRPBTC,ADABTC,DOGEBTC,AVAXBTC,DOTBTC,LINKBTC,LTCBTC,"
            "ATOMBTC,UNIBTC,NEARBTC,APTBTC,ARBBTC,OPBTC,SUIBTC,INJBTC,TIABTC,"
            "BNBETH,SOLETH,XRPETH,ADAETH,AVAXETH,DOTETH,LINKETH"
        )
    )

    host: str = "0.0.0.0"
    port: int = 8765
    log_level: str = "INFO"

    # Public market-data endpoints (vision mirrors work in more regions than api.binance.com)
    binance_rest_base: str = "https://data-api.binance.vision"
    binance_ws_base: str = "wss://data-stream.binance.vision"

    # Conservative fee model used for edge math (taker).
    taker_fee_bps: float = 10.0

    @property
    def symbols(self) -> List[str]:
        return [s.strip().upper() for s in self.scan_symbols.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
