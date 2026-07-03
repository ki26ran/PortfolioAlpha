import datetime
import json
import time
import concurrent.futures

import pandas as pd
import yfinance as yf

from .api import api

_HD_TIMEOUT = 12
_PREV_DAY_CACHE = {}


def _call_time_price_series(api_obj, exchange, token, starttime, endtime, interval):
    return api_obj.get_time_price_series(exchange, token, starttime, endtime, interval)


def get_token_from_api(symbol, exchange):
    if api is None:
        raise RuntimeError("api not set — call setup_api() first")
    resp = api.searchscrip(exchange=exchange, searchtext=symbol)
    if resp is None:
        raise RuntimeError(f"searchscrip returned None for {symbol} on {exchange}")
    try:
        return resp.get("values")[0].get("token")
    except (IndexError, TypeError, AttributeError) as e:
        raise RuntimeError(f"searchscrip returned unexpected response for {symbol}: {e}")


def HistorialData(exchange, token, starttime, endtime, interval, retries=3):
    if api is None:
        raise RuntimeError("api not set — call setup_api() first")
    for attempt in range(1, retries + 1):
        try:
            st = starttime.timestamp() if hasattr(starttime, 'timestamp') else starttime
            et = endtime.timestamp() if hasattr(endtime, 'timestamp') else endtime
            with concurrent.futures.ThreadPoolExecutor(1) as _ex:
                fut = _ex.submit(_call_time_price_series, api, exchange, token, st, et, interval)
                data = fut.result(timeout=_HD_TIMEOUT)
            if not data:
                return None
            df = pd.DataFrame(data)
            if df.empty:
                return None
            cols = ['into', 'inth', 'intl', 'intc', 'intvwap', 'v']
            df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
            df = df[['time', 'into', 'inth', 'intl', 'intc', 'intvwap', 'v']]
            df.columns = ['Datetime', 'Open', 'High', 'Low', 'Close', 'VWAP', 'Volume']
            df = df.iloc[::-1]
            df['Datetime'] = pd.to_datetime(df['Datetime'], format="%d-%m-%Y %H:%M:%S")
            df.set_index('Datetime', inplace=True)
            return df
        except concurrent.futures.TimeoutError:
            if attempt < retries:
                time.sleep(1)
            else:
                return None
        except Exception:
            if attempt < retries:
                time.sleep(2)
            else:
                return None
    return None


def fetch_candle_data_api(exchange, symbol, date_str, interval="5m"):
    if api is None:
        raise RuntimeError("api not set — call setup_api() first")
    try:
        token = get_token_from_api(symbol, exchange)
        starttime = pd.to_datetime(date_str)
        endtime = starttime + pd.Timedelta(days=1)
        return HistorialData(exchange, token, starttime, endtime, interval)
    except Exception:
        return None


def fetch_candle_data_yf(symbol, date_str, interval="5m"):
    try:
        df = yf.download(
            symbol + ".NS",
            interval=interval,
            start=date_str,
            end=pd.to_datetime(date_str) + pd.Timedelta(days=1),
            auto_adjust=False,
            progress=False
        )
        if df.empty:
            return None
        df.columns = df.columns.droplevel(1)
        df = df.tz_convert('Asia/Kolkata').tz_localize(None)
        return df.between_time('09:15', '15:30')
    except Exception:
        return None


def fetch_intraday(exchange, symbol, date_str, datasource, interval):
    if not symbol or symbol == "Symbol":
        return None
    try:
        if datasource == 1:
            return fetch_candle_data_yf(symbol, date_str, interval)
        elif datasource == 2:
            if api is None:
                raise RuntimeError("api not set — call setup_api() first")
            df = fetch_candle_data_api(exchange, symbol, date_str, interval)
            if df is None:
                time.sleep(1)
                df = fetch_candle_data_api(exchange, symbol, date_str, interval)
            return df
        else:
            raise ValueError("Invalid datasource (1=Yahoo, 2=Broker)")
    except Exception:
        return None


def fetch_prev_day_ohlc(index_symbol, trade_date):
    if api is None:
        raise RuntimeError("api not set — call setup_api() first")
    start = pd.to_datetime(trade_date) - pd.Timedelta(days=7)
    end = pd.to_datetime(trade_date)
    ret = api.get_daily_price_series(
        exchange="NFO", tradingsymbol=index_symbol,
        startdate=start.timestamp(), enddate=end.timestamp()
    )
    if not ret:
        return None
    rows = [json.loads(x) for x in ret]
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    row = df.iloc[0]
    return {
        "pdh": float(row.inth),
        "pdl": float(row.intl),
        "pdc": float(row.intc),
        "date": row.time
    }


def fetch_prev_day_ohlc_yahoo(index_symbol, trade_date, lookback_days=10, use_cache=True):
    if isinstance(trade_date, str):
        trade_date = datetime.datetime.strptime(trade_date, "%Y-%m-%d")
    cache_key = f"{index_symbol}_{trade_date.date()}"
    if use_cache and cache_key in _PREV_DAY_CACHE:
        return _PREV_DAY_CACHE[cache_key]
    end_date = trade_date.date()
    start_date = end_date - datetime.timedelta(days=lookback_days)
    df = yf.download(
        index_symbol,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        interval="1d", auto_adjust=False, progress=False
    )
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    if len(df) < 1:
        return None
    prev = df.iloc[-1]
    result = {
        "high":  float(prev["High"]),
        "low":   float(prev["Low"]),
        "close": float(prev["Close"]),
        "date":  prev.name.strftime("%Y-%m-%d")
    }
    if use_cache:
        _PREV_DAY_CACHE[cache_key] = result
    return result


def yahoo_symbol(symbol):
    symbol = symbol.upper()
    if symbol == "NIFTY":
        return "^NSEI"
    if symbol == "BANKNIFTY":
        return "^NSEBANK"
    if symbol.endswith("-EQ"):
        return symbol.replace("-EQ", ".NS")
    return symbol
