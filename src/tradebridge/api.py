"""TradeBridge Pro HTTP interface — mock venues ONLY, never real orders."""
from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from . import __version__
from .config import Settings, VENUE_SYMBOLS
from .engine import PaperRouter, RiskViolation, SignalConflict
from .models import Signal


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    app = FastAPI(
        title="TradeBridge Pro | Simulated Execution Bridge",
        version=__version__,
        description="TradingView-style alerts routed to three simulated venues. "
        "No IBKR, MT5 or CEX account is accessed.",
    )
    engine: PaperRouter | None = None

    def get_engine() -> PaperRouter:
        nonlocal engine
        if engine is None:
            try:
                engine = PaperRouter(config)
            except ValueError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="Service not configured. Set two distinct, strong environment secrets.",
                ) from exc
        return engine

    def require_operator(x_api_key: str | None = Header(default=None)) -> None:
        if (
            not config._valid_secret(config.operator_key)
            or x_api_key is None
            or not compare_digest(x_api_key, config.operator_key)
        ):
            raise HTTPException(status_code=401, detail="Invalid operator API key.")

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True, "mode": "SIMULATED_ONLY", "version": __version__}

    @app.get("/api/venues")
    def venues():
        return {
            "mode": "SIMULATED_ONLY",
            "venues": {name: sorted(symbols) for name, symbols in VENUE_SYMBOLS.items()},
            "warning": "Venue names are mock adapters, not connections to any real broker.",
        }

    @app.post("/api/webhook")
    def receive_signal(alert: Signal, router: PaperRouter = Depends(get_engine)):
        if not (
            config._valid_secret(config.webhook_secret)
            and compare_digest(alert.secret, config.webhook_secret)
        ):
            raise HTTPException(status_code=401, detail="Invalid webhook secret.")
        now = datetime.now(timezone.utc)
        age = (now - alert.timestamp.astimezone(timezone.utc)).total_seconds()
        if age > config.max_signal_age_seconds or age < -30:
            raise HTTPException(status_code=422, detail="Signal expired or dated in the future.")
        try:
            return router.execute(alert)
        except SignalConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RiskViolation as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/portfolio", dependencies=[Depends(require_operator)])
    def portfolio(router: PaperRouter = Depends(get_engine)):
        return router.snapshot()

    @app.get("/api/orders", dependencies=[Depends(require_operator)])
    def orders(router: PaperRouter = Depends(get_engine)):
        return {"mode": "SIMULATED_ONLY", "orders": router.orders()}

    @app.get("/api/events", dependencies=[Depends(require_operator)])
    def events(router: PaperRouter = Depends(get_engine)):
        return {"events": router.events()}

    @app.post("/api/control/halt", dependencies=[Depends(require_operator)])
    def halt(router: PaperRouter = Depends(get_engine)):
        return router.set_halt(True)

    @app.post("/api/control/resume", dependencies=[Depends(require_operator)])
    def resume(router: PaperRouter = Depends(get_engine)):
        return router.set_halt(False)

    return app


app = create_app()
