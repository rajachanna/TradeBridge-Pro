"""External alert contract. Never treat alert price as an exchange quote."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=1)
    signal_id: str = Field(min_length=4, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    timestamp: datetime
    venue: Literal["SIM_IBKR", "SIM_MT5", "SIM_CEX"]
    symbol: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9._-]+$")
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    price: Decimal
    strategy: str = Field(default="manual", min_length=1, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("quantity", "price")
    @classmethod
    def positive_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("Quantity and price must be positive, finite values.")
        return value

    @field_validator("timestamp")
    @classmethod
    def tz_required(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timestamp must contain UTC offset.")
        return value
