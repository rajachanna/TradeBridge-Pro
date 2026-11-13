"""Fail-closed environment configuration. No live trading flags exist."""
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import os

VENUE_SYMBOLS = {
    "SIM_IBKR": frozenset({"AAPL", "MSFT"}),
    "SIM_MT5": frozenset({"EURUSD", "XAUUSD"}),
    "SIM_CEX": frozenset({"BTCUSDT", "ETHUSDT"}),
}


@dataclass(frozen=True)
class Settings:
    webhook_secret: str = ""
    operator_key: str = ""
    db_path: Path = Path("./data/tradebridge.sqlite")
    initial_cash_usd: Decimal = Decimal("10000")
    max_order_usd: Decimal = Decimal("2500")
    max_symbol_exposure_usd: Decimal = Decimal("5000")
    max_gross_exposure_usd: Decimal = Decimal("12000")
    max_daily_realized_loss_usd: Decimal = Decimal("500")
    max_signal_age_seconds: int = 120
    max_positions: int = 8

    @classmethod
    def from_env(cls) -> "Settings":
        get = os.environ.get
        return cls(
            webhook_secret=get("TB_WEBHOOK_SECRET", ""),
            operator_key=get("TB_OPERATOR_KEY", ""),
            db_path=Path(get("TB_DB_PATH", "./data/tradebridge.sqlite")),
            initial_cash_usd=Decimal(get("TB_INITIAL_CASH_USD", "10000")),
            max_order_usd=Decimal(get("TB_MAX_ORDER_USD", "2500")),
            max_symbol_exposure_usd=Decimal(get("TB_MAX_SYMBOL_EXPOSURE_USD", "5000")),
            max_gross_exposure_usd=Decimal(get("TB_MAX_GROSS_EXPOSURE_USD", "12000")),
            max_daily_realized_loss_usd=Decimal(get("TB_MAX_DAILY_REALIZED_LOSS_USD", "500")),
            max_signal_age_seconds=int(get("TB_MAX_SIGNAL_AGE_SECONDS", "120")),
            max_positions=int(get("TB_MAX_POSITIONS", "8")),
        )

    @staticmethod
    def _valid_secret(value: str) -> bool:
        return len(value) >= 16 and not value.startswith("REPLACE_")

    def validate(self) -> None:
        if not self._valid_secret(self.webhook_secret) or not self._valid_secret(self.operator_key):
            raise ValueError("Set distinct, long TB_WEBHOOK_SECRET and TB_OPERATOR_KEY values.")
        if self.webhook_secret == self.operator_key:
            raise ValueError("Webhook and operator secrets must be different.")
        for number in (
            self.initial_cash_usd,
            self.max_order_usd,
            self.max_symbol_exposure_usd,
            self.max_gross_exposure_usd,
            self.max_daily_realized_loss_usd,
        ):
            if not number.is_finite() or number <= 0:
                raise ValueError("All financial limits must be positive, finite decimals.")
        if self.max_signal_age_seconds <= 0 or self.max_positions <= 0:
            raise ValueError("Signal-age and position-count limits must be positive.")
