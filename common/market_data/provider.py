"""
Data Provider Abstraction.
All data fetching goes through this layer. Swap backends by changing config.json.
"""
import os, sys, json, time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

try:
    from yfinance.exceptions import YFPricesMissingError
except ImportError:
    class YFPricesMissingError(Exception):
        pass

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")


def _load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


class DataProvider(ABC):

    @abstractmethod
    def download_daily(self, symbols: List[str], start: str, end: str) -> pd.DataFrame:
        """Return DataFrame with MultiIndex columns (Price, Ticker) or single-level."""

    @abstractmethod
    def download_intraday(self, symbols: List[str], start: str, end: str,
                          interval: str = "5m") -> pd.DataFrame:
        """Return DataFrame with MultiIndex columns."""

    @abstractmethod
    def get_last_price(self, symbol: str) -> Optional[float]:
        """Return current price for a single symbol."""


class YahooFinanceProvider(DataProvider):

    def __init__(self, config: dict = None):
        self.config = config or _load_config()
        self.batch_size = self.config.get("sync", {}).get("batch_size", 30)
        self.retry_count = self.config.get("sync", {}).get("retry_count", 3)
        self.retry_delay = self.config.get("sync", {}).get("retry_delay", 60)

    def _download_with_retry(self, tickers_str: str, **kwargs) -> pd.DataFrame:
        for attempt in range(self.retry_count):
            try:
                df = yf.download(tickers_str, progress=False, timeout=120, **kwargs)
                if not df.empty:
                    return df
                return df
            except YFPricesMissingError:
                print(f"  [WARN] YFPricesMissingError for {tickers_str[:80]} — skipping batch")
                return pd.DataFrame()
            except Exception as e:
                print(f"  [WARN] yfinance attempt {attempt+1}/{self.retry_count} failed: {e}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise e
        return pd.DataFrame()

    def download_daily(self, symbols: List[str], start: str, end: str) -> pd.DataFrame:
        result = pd.DataFrame()
        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i:i + self.batch_size]
            tickers = " ".join(batch)
            df = self._download_with_retry(tickers, start=start, end=end, interval="1d",
                                            auto_adjust=False, group_by="ticker")
            if not df.empty:
                if result.empty:
                    result = df
                else:
                    result = pd.concat([result, df], axis=1)
            if i + self.batch_size < len(symbols):
                time.sleep(1)
        return result

    def download_intraday(self, symbols: List[str], start: str, end: str,
                          interval: str = "5m") -> pd.DataFrame:
        interval_map = {"hourly": "1h", "1h": "1h", "60m": "1h",
                        "5m": "5m", "1m": "1m", "daily": "1d", "1d": "1d"}
        yf_interval = interval_map.get(interval, interval)

        # 1m data limited to ~8 days per request; split into weekly chunks
        if yf_interval == "1m":
            chunks = []
            s = pd.Timestamp(start)
            e = pd.Timestamp(end)
            while s < e:
                chunk_end = min(s + timedelta(days=7), e)
                chunks.append((s.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
                s = chunk_end
        else:
            chunks = [(start, end)]

        chunk_dfs = []
        for c_start, c_end in chunks:
            chunk_df = pd.DataFrame()
            for i in range(0, len(symbols), self.batch_size):
                batch = symbols[i:i + self.batch_size]
                tickers = " ".join(batch)
                df = self._download_with_retry(tickers, start=c_start, end=c_end,
                                                interval=yf_interval, auto_adjust=False,
                                                group_by="ticker")
                if not df.empty:
                    if chunk_df.empty:
                        chunk_df = df
                    else:
                        chunk_df = pd.concat([chunk_df, df], axis=1)
                if i + self.batch_size < len(symbols):
                    time.sleep(1)
            if not chunk_df.empty:
                chunk_dfs.append(chunk_df)
            if len(chunks) > 1:
                time.sleep(2)

        if chunk_dfs:
            return pd.concat(chunk_dfs, axis=0)
        return pd.DataFrame()

    def get_last_price(self, symbol: str) -> Optional[float]:
        try:
            ticker = symbol + ".NS" if not symbol.endswith((".NS", ".BO")) else symbol
            df = yf.download(ticker, period="1d", interval="5m", progress=False, timeout=30)
            if df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                closes = df["Close"]
                if isinstance(closes, pd.DataFrame):
                    closes = closes.iloc[:, 0]
            else:
                closes = df["Close"]
            idx = -2 if len(closes) >= 2 else -1
            val = float(closes.iloc[idx])
            return None if pd.isna(val) else round(val, 2)
        except Exception:
            return None


class ShoonyaProvider(DataProvider):
    """Data provider that fetches market data via the Shoonya broker API.
    Requires valid broker credentials in broker/auth.duckdb.
    Uses broker/trading.py for all API calls.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._api = None
        self._paths_checked = False
        self.broker_name = self.config.get("broker_name", "SHOONYA")
        self.broker_user = self.config.get("broker_user", "FA138862")

    def _ensure_paths(self):
        if self._paths_checked:
            return
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        broker_dir = os.path.join(root, "broker")
        for p in sys.path:
            if p in (root, broker_dir):
                sys.path.remove(p)
        sys.path.insert(0, root)
        sys.path.insert(1, broker_dir)
        self._paths_checked = True

    def _ensure_api(self):
        self._ensure_paths()
        if self._api is None:
            from broker.broker.api import setup_api
            self._api = setup_api(self.broker_name, self.broker_user)
        return self._api

    def _shoonya_to_multiindex(self, symbol_map: dict, interval: str) -> pd.DataFrame:
        """Convert per-symbol Shoonya DataFrames into a Yahoo-style MultiIndex DataFrame."""
        if not symbol_map:
            return pd.DataFrame()
        pieces = {}
        for sym_ns, df in symbol_map.items():
            if df is None or df.empty:
                continue
            df = df.copy()
            for col in df.columns:
                low = col.lower()
                if low in ("open", "high", "low", "close", "volume"):
                    col_key = col.capitalize()
                    pieces[(col_key, sym_ns)] = df[col]
        if not pieces:
            return pd.DataFrame()
        result = pd.DataFrame(pieces)
        result.columns = pd.MultiIndex.from_tuples(result.columns, names=["Price", "Ticker"])
        result = result.sort_index()
        return result

    def _to_shoonya_sym(self, sym):
        """Convert Yahoo-style symbol to Shoonya trading symbol (RELIANCE.NS → RELIANCE-EQ)."""
        clean = sym.replace(".NS", "").replace(".BO", "")
        if not clean.endswith("-EQ") and not clean.endswith("-BE"):
            clean += "-EQ"
        return clean

    def download_daily(self, symbols, start, end):
        """Fetch daily bars via Shoonya get_daily_price_series (proven reliable).
        Symbols with ampersand (&) or other special chars may fail — those
        are automatically retried via Yahoo Finance fallback.
        Uses ThreadPoolExecutor for parallel symbol fetches.
        Returns Yahoo-style MultiIndex DataFrame."""
        self._ensure_api()
        import concurrent.futures as _futures

        def _fetch_one(sym):
            shoonya_sym = self._to_shoonya_sym(sym)
            try:
                st_ts = pd.to_datetime(start).timestamp()
                et_ts = pd.to_datetime(end).timestamp()
                with _futures.ThreadPoolExecutor(1) as _ex:
                    fut = _ex.submit(self._api.get_daily_price_series, "NSE", shoonya_sym, st_ts, et_ts)
                    raw = fut.result(timeout=15)
                if not raw:
                    return None
                rows = [json.loads(x) if isinstance(x, str) else x for x in raw]
                df = pd.DataFrame(rows)
                if df.empty:
                    return None
                vol_col = "intv" if "intv" in df.columns else "v"
                for c in ["into", "inth", "intl", "intc", vol_col]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                df = df[["time", "into", "inth", "intl", "intc", vol_col]]
                df.columns = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
                df["Datetime"] = pd.to_datetime(df["Datetime"], format="%d-%b-%Y", errors="coerce")
                df = df.sort_values("Datetime").set_index("Datetime")
                return (sym, df)
            except Exception:
                return None

        symbol_map = {}
        with _futures.ThreadPoolExecutor(max_workers=8) as pool:
            for r in pool.map(_fetch_one, symbols):
                if r is not None:
                    sym, df = r
                    symbol_map[sym] = df

        # Yahoo fallback for symbols that failed on Shoonya (e.g. M&M.NS)
        ns_failed = [s for s in symbols if s not in symbol_map]
        if ns_failed:
            if ns_failed:
                try:
                    yf = YahooFinanceProvider(self.config)
                    yf_df = yf.download_daily(ns_failed, start, end)
                    if yf_df is not None and not yf_df.empty and isinstance(yf_df.columns, pd.MultiIndex):
                        for ns in ns_failed:
                            try:
                                sdf = yf_df.xs(ns, level="Ticker", axis=1).copy()
                                if sdf.empty:
                                    continue
                                sdf = sdf.reset_index()
                                sdf.columns = [c.lower() for c in sdf.columns]
                                sdf["Datetime"] = pd.to_datetime(sdf.get("date", sdf.get("datetime", sdf.index)))
                                for date_col in ["date", "datetime", "index"]:
                                    if date_col in sdf.columns:
                                        sdf = sdf.drop(columns=[date_col])
                                sdf = sdf.set_index("Datetime")
                                rename = {"open": "Open", "high": "High", "low": "Low",
                                          "close": "Close", "volume": "Volume"}
                                sdf = sdf.rename(columns={c: rename[c] for c in sdf.columns if c in rename})
                                keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in sdf.columns]
                                symbol_map[ns] = sdf[keep]
                            except (KeyError, ValueError):
                                continue
                except Exception:
                    pass

        return self._shoonya_to_multiindex(symbol_map, "DAY")

    def download_intraday(self, symbols, start, end, interval="5m"):
        """Fetch intraday bars. Shoonya get_time_price_series is unreliable
        (intermittent hangs), so immediately fall back to Yahoo Finance."""
        return self._yahoo_fallback(symbols, start, end, interval)

    def _yahoo_fallback(self, symbols, start, end, interval):
        """Fallback to Yahoo Finance when Shoonya is unavailable."""
        yf_provider = YahooFinanceProvider(self.config)
        return yf_provider.download_intraday(symbols, start, end, interval)

    def get_last_price(self, symbol):
        """Fetch latest price via Shoonya get_quotes."""
        self._ensure_api()
        clean = symbol.replace(".NS", "").replace(".BO", "")
        try:
            resp = self._api.get_quotes("NSE", clean)
            if resp and isinstance(resp, dict):
                return float(resp.get("lp", 0))
        except Exception:
            pass
        return None


_provider_instances = {}


def get_provider(portfolio="__default__") -> DataProvider:
    global _provider_instances
    if portfolio in _provider_instances:
        return _provider_instances[portfolio]

    config = _load_config()
    portfolio_map = config.get("portfolio_providers", {})
    provider_name = portfolio_map.get(portfolio) or portfolio_map.get("__default__") or "yahoo"

    if provider_name == "yahoo":
        _provider_instances[portfolio] = YahooFinanceProvider(config)
    elif provider_name == "shoonya":
        broker_cfg = config.get("broker", {})
        _provider_instances[portfolio] = ShoonyaProvider({**config, **broker_cfg})
    else:
        raise ValueError(f"Unknown data provider for portfolio '{portfolio}': {provider_name}")
    return _provider_instances[portfolio]
