import os, sys, time, json, argparse
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from common.market_data.cache import get_cache

SYNC_LOG = os.path.join(BASE, "data", "sync_log.txt")
RESULT_FILE = os.path.join(BASE, "data", "last_sync_result.json")
os.makedirs(os.path.dirname(SYNC_LOG), exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(SYNC_LOG, "a") as f:
        f.write(line + "\n")


def _get_date_range(table):
    try:
        cache = get_cache()
        con = cache._db_read()
        r = con.execute(f"SELECT MIN(date)::VARCHAR, MAX(date)::VARCHAR FROM {table}").fetchone()
        con.close()
        return r[0] if r else None, r[1] if r else None
    except Exception:
        return None, None


def _get_dt_range(table):
    try:
        cache = get_cache()
        con = cache._db_read()
        r = con.execute(f"SELECT MIN(datetime_ist)::VARCHAR, MAX(datetime_ist)::VARCHAR FROM {table}").fetchone()
        con.close()
        return (r[0][:10] if r[0] else None), (r[1][:10] if r[1] else None)
    except Exception:
        return None, None


def sync_daily(cache, full=False):
    tickers = cache.get_universe("nifty200")
    ago = 1095 if full else 7
    start = (datetime.now() - timedelta(days=ago)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    log(f"Daily sync: {len(tickers)} tickers {start} to {end}")
    t0 = time.time()
    result = cache._bulk_fetch_daily(tickers, start, end)
    elapsed = time.time() - t0
    min_d, max_d = _get_date_range("daily_bars")
    log(f"  Done — {result['batches_fetched']} batches, {elapsed:.0f}s")
    return {"timeframe": "daily", "interval": f"{start} to {end}", "batches": result['batches_fetched'],
            "seconds": round(elapsed), "min_date": min_d, "max_date": max_d,
            "rows_before": result.get("rows_before", 0), "rows_after": result.get("rows_after", 0)}


def sync_intraday(cache, interval, days_back, label, full=False):
    tickers = cache.get_universe("nifty200")
    ago = 60 if full else days_back
    start = (datetime.now() - timedelta(days=ago)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    log(f"{label} sync: {len(tickers)} tickers {start} to {end}")
    t0 = time.time()
    result = cache._bulk_fetch_intraday(tickers, interval, start, end)
    elapsed = time.time() - t0
    min_d, max_d = _get_dt_range(interval)
    log(f"  Done — {result['batches_fetched']} batches, {elapsed:.0f}s")
    return {"timeframe": label, "interval": f"{start} to {end}", "batches": result['batches_fetched'],
            "seconds": round(elapsed), "min_date": min_d, "max_date": max_d}


def get_db_row_counts():
    try:
        cache = get_cache()
        con = cache._db_read()
        counts = {}
        for tf, table in [("daily", "daily_bars"), ("5m", "bars_5min"), ("1m", "bars_1min")]:
            r = con.execute(f"SELECT COUNT(DISTINCT ticker), COUNT(*) FROM {table}").fetchone()
            counts[tf] = {"tickers": r[0], "rows": r[1]}
        con.close()
        return counts
    except Exception as e:
        return {"error": str(e)}


def run_sync(full=False, daily=True, intraday=True):
    cache = get_cache()
    provider = type(cache.provider).__name__
    mode = "FULL" if full else "QUICK"
    log(f"Provider: {provider}")
    log(f"Mode: {mode} sync")

    counts_before = get_db_row_counts()
    details = {"provider": provider, "mode": mode, "started_at": datetime.now().isoformat()}

    if daily:
        details["daily"] = sync_daily(cache, full)
    if intraday:
        details["5m"] = sync_intraday(cache, "5m", 3, "5-min", full)
        details["1m"] = sync_intraday(cache, "1m", 2, "1-min", full)

    counts_after = get_db_row_counts()
    details["counts_before"] = counts_before
    details["counts_after"] = counts_after
    details["finished_at"] = datetime.now().isoformat()

    total_secs = sum(d.get("seconds", 0) for d in details.values() if isinstance(d, dict) and "seconds" in d)
    details["total_seconds"] = total_secs
    log(f"Data sync complete — {total_secs}s total")

    with open(RESULT_FILE, "w") as f:
        json.dump(details, f, indent=2, default=str)

    return details


def get_status():
    if not os.path.exists(SYNC_LOG):
        return {"last_sync": None, "lines": 0}
    with open(SYNC_LOG) as f:
        lines = f.readlines()
    last = lines[-1].strip() if lines else None
    return {"last_sync": last, "lines": len(lines)}


def get_sync_log(n=20):
    if not os.path.exists(SYNC_LOG):
        return []
    with open(SYNC_LOG) as f:
        lines = f.readlines()
    return [l.strip() for l in lines[-n:]]


def get_last_result():
    if not os.path.exists(RESULT_FILE):
        return None
    with open(RESULT_FILE) as f:
        return json.load(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PortfolioAlpha Data Sync")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--daily", action="store_true")
    parser.add_argument("--intraday", action="store_true")
    args = parser.parse_args()

    result = run_sync(
        full=args.full,
        daily=not args.intraday or args.daily,
        intraday=not args.daily or args.intraday,
    )
    print(f"\n=== SYNC SUMMARY ===")
    for tf in ["daily", "5m", "1m"]:
        if tf in result:
            d = result[tf]
            print(f"{d['timeframe']}: {d['batches']} batches, {d['seconds']}s, range {d['min_date']} to {d['max_date']}")
    print(f"Total: {result['total_seconds']}s")
