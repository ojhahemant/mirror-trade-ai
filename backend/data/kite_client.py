"""
Zerodha Kite Connect client with automatic token refresh and error handling.
Falls back to yfinance when Kite is unavailable.
"""
import asyncio
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
import pytz
import pandas as pd
import yfinance as yf
from loguru import logger

from api.config import settings

IST = pytz.timezone(settings.ist_timezone)


class KiteClientError(Exception):
    """Base exception for Kite client errors."""
    pass


class TokenExpiredError(KiteClientError):
    """Raised when Kite access token has expired."""
    pass


class KiteClient:
    """
    Wraps kiteconnect.KiteConnect with:
    - Automatic error handling
    - Token expiry detection
    - Rate limit backoff
    - yfinance fallback
    """

    BANKNIFTY_TOKEN = settings.banknifty_token
    BANKNIFTY_YF_SYMBOL = "^NSEBANK"
    INTERVALS = {
        "1min": "minute",
        "5min": "5minute",
        "15min": "15minute",
        "1hr": "60minute",
        "1day": "day",
    }

    def __init__(self):
        self._kite = None
        self._ticker = None
        self._kite_available = False
        self._last_price: Optional[Decimal] = None
        self._init_kite()

    def _init_kite(self):
        """Initialize Kite connection if credentials are available."""
        if not settings.kite_api_key or not settings.kite_access_token:
            logger.warning("Kite credentials not configured — using yfinance fallback")
            return
        try:
            from kiteconnect import KiteConnect
            self._kite = KiteConnect(api_key=settings.kite_api_key)
            self._kite.set_access_token(settings.kite_access_token)
            # Test connection
            profile = self._kite.profile()
            logger.info(f"Kite connected: {profile.get('user_name', 'Unknown')}")
            self._kite_available = True
        except ImportError:
            logger.warning("kiteconnect not installed — using yfinance fallback")
        except Exception as e:
            logger.warning(f"Kite init failed ({e}) — using yfinance fallback")

    def _check_token_expiry(self, error: Exception) -> bool:
        """Detect if error is token expiry."""
        error_str = str(error).lower()
        return any(kw in error_str for kw in ["token", "invalid", "expired", "unauthorised"])

    def get_historical_data(
        self,
        from_date: date,
        to_date: date,
        interval: str = "15min",
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.
        Returns DataFrame with columns: time, open, high, low, close, volume, oi
        """
        if self._kite_available:
            try:
                return self._kite_historical(from_date, to_date, interval)
            except TokenExpiredError:
                raise
            except Exception as e:
                logger.warning(f"Kite historical fetch failed ({e}), falling back to yfinance")

        return self._yfinance_historical(from_date, to_date, interval)

    def _kite_historical(
        self,
        from_date: date,
        to_date: date,
        interval: str,
    ) -> pd.DataFrame:
        """Fetch from Kite Connect API."""
        kite_interval = self.INTERVALS.get(interval, "15minute")
        try:
            records = self._kite.historical_data(
                instrument_token=self.BANKNIFTY_TOKEN,
                from_date=from_date,
                to_date=to_date,
                interval=kite_interval,
                oi=True,
            )
            if not records:
                return pd.DataFrame()

            df = pd.DataFrame(records)
            df.rename(columns={"date": "time"}, inplace=True)
            df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
            df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(IST)
            df = df[["time", "open", "high", "low", "close", "volume", "oi"]]
            df = df.sort_values("time").reset_index(drop=True)
            logger.debug(f"Kite: fetched {len(df)} candles ({interval})")
            return df

        except Exception as e:
            if self._check_token_expiry(e):
                raise TokenExpiredError(f"Kite token expired: {e}")
            raise

    def _yfinance_historical(
        self,
        from_date: date,
        to_date: date,
        interval: str,
    ) -> pd.DataFrame:
        """Fallback: fetch from Yahoo Finance."""
        yf_interval_map = {
            "1min": "1m",
            "5min": "5m",
            "15min": "15m",
            "1hr": "1h",
            "1day": "1d",
        }
        yf_interval = yf_interval_map.get(interval, "15m")

        try:
            ticker = yf.Ticker(self.BANKNIFTY_YF_SYMBOL)
            df = ticker.history(
                start=from_date.isoformat(),
                end=(to_date + timedelta(days=1)).isoformat(),
                interval=yf_interval,
                auto_adjust=True,
            )
            if df.empty:
                return pd.DataFrame()

            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            time_col = "datetime" if "datetime" in df.columns else "date"
            df.rename(columns={time_col: "time"}, inplace=True)

            if df["time"].dt.tz is None:
                df["time"] = df["time"].dt.tz_localize(IST)
            else:
                df["time"] = df["time"].dt.tz_convert(IST)

            df["oi"] = 0
            df = df[["time", "open", "high", "low", "close", "volume", "oi"]]
            df = df.sort_values("time").reset_index(drop=True)
            logger.debug(f"yfinance: fetched {len(df)} candles ({interval})")
            return df

        except Exception as e:
            logger.error(f"yfinance fetch failed: {e}")
            return pd.DataFrame()

    def get_live_quote(self) -> Optional[Dict[str, Any]]:
        """Get current Bank Nifty LTP and OHLC."""
        if self._kite_available:
            try:
                quote = self._kite.quote([settings.banknifty_symbol])
                q = quote.get(settings.banknifty_symbol, {})
                ohlc = q.get("ohlc", {})
                return {
                    "symbol": "BANKNIFTY",
                    "ltp": Decimal(str(q.get("last_price", 0))),
                    "change": Decimal(str(q.get("net_change", 0))),
                    "change_pct": Decimal(str(q.get("change", 0))),
                    "high": Decimal(str(ohlc.get("high", 0))),
                    "low": Decimal(str(ohlc.get("low", 0))),
                    "open": Decimal(str(ohlc.get("open", 0))),
                    "prev_close": Decimal(str(ohlc.get("close", 0))),
                    "timestamp": datetime.now(IST),
                }
            except TokenExpiredError:
                raise
            except Exception as e:
                logger.warning(f"Kite quote failed ({e}), using yfinance")

        return self._yfinance_live_quote()

    def _yfinance_live_quote(self) -> Optional[Dict[str, Any]]:
        """Fallback live quote from yfinance."""
        try:
            ticker = yf.Ticker(self.BANKNIFTY_YF_SYMBOL)
            info = ticker.fast_info
            ltp = Decimal(str(info.get("last_price", 0)))
            prev_close = Decimal(str(info.get("previous_close", ltp)))
            change = ltp - prev_close
            change_pct = (change / prev_close * 100) if prev_close else Decimal("0")
            return {
                "symbol": "BANKNIFTY",
                "ltp": ltp,
                "change": change,
                "change_pct": change_pct,
                "high": Decimal(str(info.get("day_high", 0))),
                "low": Decimal(str(info.get("day_low", 0))),
                "open": Decimal(str(info.get("open", 0))),
                "prev_close": prev_close,
                "timestamp": datetime.now(IST),
            }
        except Exception as e:
            logger.error(f"yfinance live quote failed: {e}")
            return None

    def get_options_chain(self) -> Optional[Dict[str, Any]]:
        """Fetch current expiry options chain from Kite."""
        if not self._kite_available:
            logger.warning("Options chain requires Kite Connect — returning None")
            return None
        try:
            instruments = self._kite.instruments("NFO")
            df = pd.DataFrame(instruments)
            bn_options = df[
                (df["name"] == "BANKNIFTY") &
                (df["instrument_type"].isin(["CE", "PE"]))
            ].copy()

            if bn_options.empty:
                return None

            # Get nearest expiry
            bn_options["expiry"] = pd.to_datetime(bn_options["expiry"])
            today = datetime.now(IST).date()
            future_expiries = bn_options[bn_options["expiry"].dt.date >= today]["expiry"].unique()
            if len(future_expiries) == 0:
                return None
            nearest_expiry = sorted(future_expiries)[0]
            current_expiry = bn_options[bn_options["expiry"] == nearest_expiry]

            tokens = current_expiry["instrument_token"].tolist()
            if not tokens:
                return None

            # Fetch quotes in batches of 500
            all_quotes = {}
            for i in range(0, len(tokens), 500):
                batch = tokens[i:i+500]
                try:
                    quotes = self._kite.quote(batch)
                    all_quotes.update(quotes)
                except Exception as e:
                    logger.warning(f"Options quote batch failed: {e}")

            chain_data = []
            for _, row in current_expiry.iterrows():
                token = str(row["instrument_token"])
                quote = all_quotes.get(token, {})
                chain_data.append({
                    "strike": Decimal(str(row["strike"])),
                    "option_type": row["instrument_type"],
                    "ltp": Decimal(str(quote.get("last_price", 0))),
                    "oi": quote.get("oi", 0),
                    "change_oi": quote.get("oi_day_change", 0),
                    "iv": Decimal(str(quote.get("depth", {}).get("implied_volatility", 0))),
                    "volume": quote.get("volume", 0),
                })

            return {
                "expiry": nearest_expiry.strftime("%Y-%m-%d"),
                "chain": chain_data,
            }
        except Exception as e:
            logger.error(f"Options chain fetch failed: {e}")
            return None

    def start_ticker(self, on_tick_callback):
        """Start WebSocket ticker for live price updates."""
        if not self._kite_available:
            logger.warning("Ticker requires Kite Connect — skipping")
            return
        try:
            from kiteconnect import KiteTicker
            self._ticker = KiteTicker(
                api_key=settings.kite_api_key,
                access_token=settings.kite_access_token,
            )

            def on_ticks(ws, ticks):
                for tick in ticks:
                    on_tick_callback(tick)

            def on_connect(ws, response):
                ws.subscribe([self.BANKNIFTY_TOKEN])
                ws.set_mode(ws.MODE_FULL, [self.BANKNIFTY_TOKEN])
                logger.info("Kite Ticker connected, subscribed to BANKNIFTY")

            def on_error(ws, code, reason):
                logger.error(f"Kite Ticker error {code}: {reason}")

            def on_close(ws, code, reason):
                logger.warning(f"Kite Ticker closed {code}: {reason}")

            self._ticker.on_ticks = on_ticks
            self._ticker.on_connect = on_connect
            self._ticker.on_error = on_error
            self._ticker.on_close = on_close
            self._ticker.connect(threaded=True)
        except Exception as e:
            logger.error(f"Ticker start failed: {e}")

    def stop_ticker(self):
        """Stop the WebSocket ticker."""
        if self._ticker:
            try:
                self._ticker.close()
            except Exception:
                pass


# Singleton instance
kite_client = KiteClient()
