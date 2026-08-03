"""
AI TradePro — Angel One (SmartAPI) execution backend  [hardened]

WHAT CHANGED VS. THE ORIGINAL (see REVIEW.md for the full list)
--------------------------------------------------------------
1. Broker credentials are NEVER accepted over HTTP anymore. They live only in
   server-side environment variables (.env). The browser cannot send or leak
   your password / API key / TOTP secret.
2. CORS is restricted to explicit local origins instead of "*". A wildcard
   origin together with allow_credentials=True is actually rejected by browsers
   and, for a server that can place real trades, it let *any* website you visit
   talk to your order engine.
3. Every state-changing call now requires a session token that the server mints
   at login and the browser must echo back in the X-Session-Token header.
4. Orders default to DRY_RUN (simulated). A real order is only sent when
   DRY_RUN=false in the environment AND the request explicitly sets confirm=true.
   This makes it very hard to fire a live F&O order by accident.
5. Exchange / product / variety / duration are request parameters, not hardcoded.
6. Structured errors, order logging, and a thread lock around the shared session.

This is a *personal, local* tool. It is not hardened for exposure to the public
internet. Do not bind it to 0.0.0.0 on a machine reachable from outside your LAN.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
from typing import Optional

import pyotp
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from SmartApi import SmartConnect
except ImportError:  # allow the module to import for review/testing without the SDK
    SmartConnect = None  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("tradepro")

# --------------------------------------------------------------------------- #
# Configuration (all secrets come from the environment / .env — never HTTP)    #
# --------------------------------------------------------------------------- #

ANGEL_API_KEY = os.getenv("ANGEL_API_KEY", "")
ANGEL_CLIENT_CODE = os.getenv("ANGEL_CLIENT_CODE", "")
ANGEL_PASSWORD = os.getenv("ANGEL_MPIN", os.getenv("ANGEL_PASSWORD", ""))
ANGEL_TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET", "")

# Comma-separated list of allowed browser origins.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000",
    ).split(",")
    if o.strip()
]

# Safety switch. Live orders require BOTH of these to be true.
DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"

app = FastAPI(title="AI TradePro Backend — Angel One Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # explicit list, NOT "*"
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Session-Token"],
)

# --------------------------------------------------------------------------- #
# Shared session state (single-user local tool). Guarded by a lock.           #
# --------------------------------------------------------------------------- #

_lock = threading.Lock()
_smart_api = None          # type: ignore
_session_token: Optional[str] = None   # our own token, not the broker JWT


def require_session(x_session_token: str = Header(default="")) -> None:
    """Reject any state-changing call that doesn't present the login token."""
    if not _session_token or not secrets.compare_digest(
        x_session_token, _session_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not logged in, or invalid session token.",
        )


# --------------------------------------------------------------------------- #
# Models                                                                       #
# --------------------------------------------------------------------------- #

class OrderDetails(BaseModel):
    tradingsymbol: str
    symboltoken: str
    transactiontype: str = Field(..., description="BUY or SELL")
    quantity: int = Field(..., gt=0)
    price: float = 0.0
    ordertype: str = "MARKET"
    exchange: str = "NFO"
    producttype: str = "INTRADAY"
    variety: str = "NORMAL"
    duration: str = "DAY"
    # A live order requires this to be explicitly true (belt-and-braces alongside DRY_RUN).
    confirm: bool = False


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "logged_in": _session_token is not None,
        "dry_run": DRY_RUN,
        "sdk_available": SmartConnect is not None,
    }


@app.post("/api/login")
def login_angel_one():
    """
    Logs into Angel One using SERVER-SIDE credentials only.
    The browser sends nothing here except the request itself.
    """
    global _smart_api, _session_token

    if SmartConnect is None:
        raise HTTPException(500, "SmartApi SDK not installed on the server.")
    if not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PASSWORD, ANGEL_TOTP_SECRET]):
        raise HTTPException(
            500,
            "Server is missing broker credentials. Set ANGEL_* variables in .env.",
        )

    with _lock:
        try:
            api = SmartConnect(api_key=ANGEL_API_KEY)
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            data = api.generateSession(ANGEL_CLIENT_CODE, ANGEL_PASSWORD, totp)

            if not isinstance(data, dict) or not data.get("status"):
                msg = data.get("message", "Login failed") if isinstance(data, dict) else "Login failed"
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=msg)

            _smart_api = api
            _session_token = secrets.token_urlsafe(32)
            log.info("Login successful for client %s", ANGEL_CLIENT_CODE)
            # We return OUR token, never the broker JWT.
            return {"status": "success", "message": "Connected", "sessionToken": _session_token}

        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Login error")
            raise HTTPException(500, detail=f"Login error: {exc}") from exc


@app.post("/api/logout", dependencies=[Depends(require_session)])
def logout():
    global _smart_api, _session_token
    with _lock:
        try:
            if _smart_api is not None:
                _smart_api.terminateSession(ANGEL_CLIENT_CODE)
        except Exception:  # noqa: BLE001
            log.warning("terminateSession failed (ignored)")
        _smart_api = None
        _session_token = None
    return {"status": "success"}


@app.post("/api/place-order", dependencies=[Depends(require_session)])
def place_order(order: OrderDetails):
    if _smart_api is None:
        raise HTTPException(401, "Not logged in.")

    params = {
        "variety": order.variety,
        "tradingsymbol": order.tradingsymbol,
        "symboltoken": order.symboltoken,
        "transactiontype": order.transactiontype.upper(),
        "exchange": order.exchange,
        "ordertype": order.ordertype,
        "producttype": order.producttype,
        "duration": order.duration,
        "price": str(order.price),
        "squareoff": "0",
        "stoploss": "0",
        "quantity": str(order.quantity),
    }

    # --- Safety gate: simulate unless BOTH the server flag and the request confirm live. ---
    if DRY_RUN or not order.confirm:
        log.info("DRY-RUN order (not sent to broker): %s", params)
        return {
            "status": "simulated",
            "dry_run": True,
            "message": "Order was simulated. Set DRY_RUN=false and confirm=true to trade live.",
            "params": params,
        }

    with _lock:
        try:
            order_id = _smart_api.placeOrder(params)
            log.info("LIVE order placed. id=%s params=%s", order_id, params)
            return {"status": "success", "orderId": order_id, "dry_run": False}
        except Exception as exc:  # noqa: BLE001
            log.exception("Order placement failed")
            raise HTTPException(500, detail=f"Order failed: {exc}") from exc


# --------------------------------------------------------------------------- #
# F&O market-data foundation (READ-ONLY — no orders here)                      #
#                                                                             #
# These endpoints turn the simulator into a real F&O tool by giving you       #
# actual instrument tokens, option chains, and live prices. They place no     #
# orders, so they're safe to test freely. NOTE: verify against your own       #
# account once — Angel One occasionally tweaks field formats.                  #
# --------------------------------------------------------------------------- #

# Angel One publishes the full instrument list here (public, no auth needed).
SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
_INSTRUMENTS_CACHE = os.path.join(os.path.dirname(__file__), "instruments.json")
_instruments: list[dict] = []


def _load_instruments(force: bool = False) -> list[dict]:
    """Download & cache the scrip master. Refreshes if older than a day."""
    global _instruments
    if _instruments and not force:
        return _instruments

    stale = True
    if os.path.exists(_INSTRUMENTS_CACHE):
        stale = (os.path.getmtime(_INSTRUMENTS_CACHE) < (__import__("time").time() - 86400))

    if force or stale or not os.path.exists(_INSTRUMENTS_CACHE):
        import urllib.request
        log.info("Downloading Angel One scrip master…")
        with urllib.request.urlopen(SCRIP_MASTER_URL, timeout=60) as resp:
            raw = resp.read()
        with open(_INSTRUMENTS_CACHE, "wb") as fh:
            fh.write(raw)

    import json as _json
    with open(_INSTRUMENTS_CACHE, "rb") as fh:
        _instruments = _json.load(fh)
    log.info("Loaded %d instruments.", len(_instruments))
    return _instruments


@app.post("/api/instruments/refresh")
def refresh_instruments():
    try:
        data = _load_instruments(force=True)
        return {"status": "success", "count": len(data)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not refresh instruments: {exc}") from exc


@app.get("/api/search")
def search_symbol(query: str, exchange: str = "", limit: int = 25):
    """Find real instruments (with tokens) by a name/symbol substring."""
    data = _load_instruments()
    q = query.upper()
    out = []
    for it in data:
        if q in str(it.get("symbol", "")).upper() or q in str(it.get("name", "")).upper():
            if exchange and str(it.get("exch_seg", "")).upper() != exchange.upper():
                continue
            out.append(it)
            if len(out) >= limit:
                break
    return {"count": len(out), "results": out}


@app.get("/api/option-chain")
def option_chain(name: str, expiry: str = "", exch_seg: str = "NFO"):
    """
    Return CE/PE option instruments for an underlying (e.g. name=NIFTY).
    `expiry` is an optional substring filter like '25JAN2025'.
    Each item carries the real `token` and `symbol` you need to place an order.
    """
    data = _load_instruments()
    name_u, exp_u, exch_u = name.upper(), expiry.upper(), exch_seg.upper()
    ce, pe = [], []
    for it in data:
        if str(it.get("exch_seg", "")).upper() != exch_u:
            continue
        if str(it.get("name", "")).upper() != name_u:
            continue
        itype = str(it.get("instrumenttype", "")).upper()
        if not itype.startswith("OPT"):
            continue
        sym = str(it.get("symbol", "")).upper()
        if exp_u and exp_u not in str(it.get("expiry", "")).upper():
            continue
        row = {
            "token": it.get("token"),
            "symbol": it.get("symbol"),
            "expiry": it.get("expiry"),
            "strike": it.get("strike"),
            "lotsize": it.get("lotsize"),
        }
        (ce if sym.endswith("CE") else pe if sym.endswith("PE") else []).append(row)
    ce.sort(key=lambda r: float(r["strike"] or 0))
    pe.sort(key=lambda r: float(r["strike"] or 0))
    return {"name": name_u, "expiry": expiry, "ce_count": len(ce), "pe_count": len(pe), "CE": ce, "PE": pe}


class LtpRequest(BaseModel):
    exchange: str = "NFO"
    tradingsymbol: str
    symboltoken: str


@app.post("/api/ltp", dependencies=[Depends(require_session)])
def get_ltp(req: LtpRequest):
    if _smart_api is None:
        raise HTTPException(401, "Not logged in.")
    with _lock:
        try:
            data = _smart_api.ltpData(req.exchange, req.tradingsymbol, req.symboltoken)
            if isinstance(data, dict) and data.get("status"):
                return {"status": "success", "data": data.get("data")}
            raise HTTPException(502, detail=str(data))
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, detail=f"LTP failed: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    # Bind to loopback by default so the order engine isn't exposed on your LAN.
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
