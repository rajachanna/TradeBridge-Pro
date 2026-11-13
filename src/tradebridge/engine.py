"""SQLite-backed, atomic, multi-venue PAPER route simulator.

SIM_IBKR, SIM_MT5, SIM_CEX are in-process mock venue identifiers.
There is no TWS/MetaTrader/exchange connection, and no actual order is sent.
"""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .config import Settings, VENUE_SYMBOLS
from .models import Signal


class RiskViolation(Exception):
    """A simulation-only pre-trade risk or control check rejected an alert."""


class SignalConflict(Exception):
    """The same signal_id was reused for different economic instructions."""


def usd(value: str) -> Decimal:
    return Decimal(value)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def signal_hash(alert: Signal) -> str:
    payload = {
        "venue": alert.venue, "symbol": alert.symbol, "side": alert.side,
        "quantity": str(alert.quantity.normalize()), "price": str(alert.price.normalize()),
        "strategy": alert.strategy,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PaperRouter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.validate()
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS controls (
                    id INTEGER PRIMARY KEY CHECK(id=1), halted INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS balances (
                    venue TEXT PRIMARY KEY, cash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions (
                    venue TEXT NOT NULL, symbol TEXT NOT NULL, quantity TEXT NOT NULL,
                    avg_cost TEXT NOT NULL, last_alert_price TEXT NOT NULL,
                    PRIMARY KEY(venue, symbol)
                );
                CREATE TABLE IF NOT EXISTS orders (
                    signal_id TEXT PRIMARY KEY,
                    payload_hash TEXT NOT NULL,
                    venue TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    quantity TEXT NOT NULL, price TEXT NOT NULL,
                    notional TEXT NOT NULL, realized_pnl TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                    type TEXT NOT NULL, signal_id TEXT, message TEXT NOT NULL
                );
            """)
            db.execute("INSERT OR IGNORE INTO controls(id, halted) VALUES(1,0)")
            for venue in VENUE_SYMBOLS:
                db.execute(
                    "INSERT OR IGNORE INTO balances(venue,cash) VALUES(?,?)",
                    (venue, str(settings.initial_cash_usd)),
                )

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.settings.db_path), timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=20000")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _event(self, event_type: str, signal_id: str | None, message: str):
        with self._db() as db:
            db.execute(
                "INSERT INTO events(created_at,type,signal_id,message) VALUES(?,?,?,?)",
                (utc_now(), event_type, signal_id, message),
            )

    def _daily_realized(self, db: sqlite3.Connection) -> Decimal:
        day = datetime.now(timezone.utc).date().isoformat()
        return sum(
            (usd(r["realized_pnl"]) for r in db.execute(
                "SELECT realized_pnl FROM orders WHERE substr(created_at,1,10)=?", (day,)
            )), Decimal("0"),
        )

    def execute(self, alert: Signal) -> dict:
        fingerprint = signal_hash(alert)
        db = self._db()
        try:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM orders WHERE signal_id=?", (alert.signal_id,)
            ).fetchone()
            if previous:
                if previous["payload_hash"] != fingerprint:
                    raise SignalConflict("Signal ID already used with different order instructions.")
                db.execute("ROLLBACK")
                return {"status": "DUPLICATE", "signal_id": alert.signal_id, "mode": "SIMULATED"}

            if db.execute("SELECT halted FROM controls WHERE id=1").fetchone()["halted"]:
                raise RiskViolation("Operator emergency halt is active.")
            if alert.symbol not in VENUE_SYMBOLS[alert.venue]:
                raise RiskViolation("Symbol is not supported on the selected simulated venue.")

            notional = alert.quantity * alert.price
            if notional > self.settings.max_order_usd:
                raise RiskViolation("Maximum order notional exceeded.")

            cash = usd(db.execute(
                "SELECT cash FROM balances WHERE venue=?", (alert.venue,)
            ).fetchone()["cash"])
            positions = db.execute("SELECT * FROM positions").fetchall()
            existing = next(
                (p for p in positions if p["venue"] == alert.venue and p["symbol"] == alert.symbol),
                None,
            )
            held = usd(existing["quantity"]) if existing else Decimal("0")
            avg = usd(existing["avg_cost"]) if existing else Decimal("0")
            realized = Decimal("0")

            if alert.side == "BUY":
                if self._daily_realized(db) <= -self.settings.max_daily_realized_loss_usd:
                    raise RiskViolation("Daily realized-loss limit reached; new buys blocked.")
                if cash < notional:
                    raise RiskViolation("Insufficient simulated cash for this venue.")
                if existing is None and len(positions) >= self.settings.max_positions:
                    raise RiskViolation("Maximum number of open positions exceeded.")
                if (held + alert.quantity) * alert.price > self.settings.max_symbol_exposure_usd:
                    raise RiskViolation("Symbol exposure cap exceeded.")
                gross = sum((
                    usd(p["quantity"]) * (
                        alert.price if p["venue"] == alert.venue and p["symbol"] == alert.symbol
                        else usd(p["last_alert_price"])
                    ) for p in positions
                ), Decimal("0"))
                if gross + notional > self.settings.max_gross_exposure_usd:
                    raise RiskViolation("Total gross exposure cap exceeded.")

                new_qty = held + alert.quantity
                new_cost = (held * avg + notional) / new_qty
                db.execute(
                    """INSERT INTO positions(venue,symbol,quantity,avg_cost,last_alert_price)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(venue,symbol) DO UPDATE SET
                    quantity=excluded.quantity,
                    avg_cost=excluded.avg_cost,
                    last_alert_price=excluded.last_alert_price""",
                    (alert.venue, alert.symbol, str(new_qty), str(new_cost), str(alert.price)),
                )
                cash -= notional
            else:
                if alert.quantity > held:
                    raise RiskViolation("Spot-like paper mode cannot sell unowned quantity.")
                realized = (alert.price - avg) * alert.quantity
                remaining = held - alert.quantity
                if remaining == 0:
                    db.execute(
                        "DELETE FROM positions WHERE venue=? AND symbol=?",
                        (alert.venue, alert.symbol),
                    )
                else:
                    db.execute(
                        "UPDATE positions SET quantity=?, last_alert_price=? WHERE venue=? AND symbol=?",
                        (str(remaining), str(alert.price), alert.venue, alert.symbol),
                    )
                cash += notional

            db.execute("UPDATE balances SET cash=? WHERE venue=?", (str(cash), alert.venue))
            db.execute(
                """INSERT INTO orders (
                  signal_id,payload_hash,venue,symbol,side,strategy,quantity,
                  price,notional,realized_pnl,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (alert.signal_id, fingerprint, alert.venue, alert.symbol, alert.side,
                 alert.strategy, str(alert.quantity), str(alert.price), str(notional),
                 str(realized), "SIMULATED_FILLED", utc_now()),
            )
            db.execute(
                "INSERT INTO events(created_at,type,signal_id,message) VALUES(?,?,?,?)",
                (utc_now(), "SIMULATED_FILLED", alert.signal_id,
                 f"{alert.venue} {alert.side} {alert.symbol} at alert-supplied price"),
            )
            db.execute("COMMIT")
            return {
                "status": "SIMULATED_FILLED", "mode": "SIMULATED",
                "signal_id": alert.signal_id, "venue": alert.venue,
                "realized_pnl_usd": str(realized),
            }
        except (RiskViolation, SignalConflict) as error:
            if db.in_transaction:
                db.execute("ROLLBACK")
            self._event("REJECTED", alert.signal_id, str(error))
            raise
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def set_halt(self, value: bool) -> dict:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE controls SET halted=? WHERE id=1", (int(value),))
            db.execute(
                "INSERT INTO events(created_at,type,signal_id,message) VALUES(?,?,?,?)",
                (utc_now(), "CONTROL", None, "HALTED" if value else "RESUMED"),
            )
            db.execute("COMMIT")
        return {"halted": value, "mode": "SIMULATED"}

    def snapshot(self) -> dict:
        with self._db() as db:
            balances = [dict(r) for r in db.execute("SELECT * FROM balances ORDER BY venue")]
            positions = [dict(r) for r in db.execute("SELECT * FROM positions ORDER BY venue,symbol")]
            daily = self._daily_realized(db)
            return {
                "mode": "SIMULATED_ONLY",
                "halted": bool(db.execute("SELECT halted FROM controls WHERE id=1").fetchone()["halted"]),
                "balances": balances, "positions": positions,
                "daily_realized_pnl_usd": str(daily),
                "note": "Positions are not marked to real market data; per-venue account balances are fictional.",
            }

    def orders(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute(
                """SELECT signal_id,venue,symbol,side,strategy,quantity,price,
                notional,realized_pnl,status,created_at
                FROM orders ORDER BY rowid DESC LIMIT 100"""
            )]

    def events(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT 100"
            )]
