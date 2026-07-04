# PortfolioAlpha

A standalone swing trading system with three strategies: Donchian + ADX, Keltner + RSI + Volume, and Supertrend + Volume. Extracted and cleaned from the ngen26 monorepo.

## Architecture

```
PortfolioAlpha/
├── agents/                  # Automated agents
│   ├── stock_selection.py   # Pre-market stock scanner (08:30)
│   └── live_trader.py       # Live position monitor + entry/exit
├── core/                    # Shared core modules
│   ├── strategy_base.py     # Base class for all strategies
│   ├── registry.py          # Strategy loading + config management
│   ├── data_loader.py       # yfinance data download
│   ├── backtest_engine.py   # Multi-strategy backtester
│   ├── atomic.py            # Thread-safe JSON I/O
│   └── notifications.py     # Telegram integration
├── strategies/              # Strategy implementations
│   ├── donchian_adx.py      # Donchian + ADX
│   ├── keltner_rsi.py       # Keltner + RSI + Volume
│   └── supertrend_volume.py  # Supertrend + Volume
├── live/
│   └── cache.py             # DuckDB cache for positions
├── cfg/                     # Configuration
│   ├── settings.py          # Global settings (capital, limits)
│   ├── universes.py         # Stock universe definitions
│   ├── strategies.json      # Strategy configurations
│   └── default_*.json       # Default config backups
├── common/                  # Shared utilities
│   └── market_data/
│       ├── cache.py         # OHLCV data cache (DuckDB)
│       ├── provider.py      # yfinance data provider
│       └── scan_logger.py   # Scan history logging
├── broker/                  # Broker integration (optional)
│   ├── api.py               # Broker API (Shoonya)
│   ├── session.py           # Login session management
│   └── data.py              # Market data via broker
├── reports/                 # Streamlit UI pages
│   ├── dashboard.py         # Live position dashboard
│   ├── stock_selection.py   # Scan results viewer
│   ├── backtest.py          # Multi-strategy backtester
│   ├── admin.py             # Settings and configuration
│   ├── scheduler.py         # Task scheduler management
│   └── about.py             # Documentation
├── dashboard.py             # Streamlit entry point
└── requirements.txt         # Python dependencies
```

## Strategies

### 1. Donchian + ADX
- **Universe**: Margin < 200K (~112 stocks)
- **Entry**: Close breaks above Donchian 20-day high (LONG) or below 20-day low (SHORT), with +DI > -DI confirmation
- **Filter**: ADX > 25 (configurable, default 35)
- **Exit**: Trailing stop, target, or time-limit

### 2. Keltner + RSI + Volume
- **Universe**: Margin < 200K (~112 stocks)
- **Entry**: Close beyond Keltner channel bands with ADX > 20 AND:
  - LONG: Close > upper band, +DI > -DI, RSI > 55, volume > 2x MA20
  - SHORT: Close < lower band, -DI > +DI, RSI < 45, volume > 2x MA20
- **Exit**: Trailing stop, target, or time-limit

### 3. Supertrend + Volume
- **Universe**: Nifty 50 (~54 stocks)
- **Entry**: Trend flip (direction change) with volume confirmation >= 1x MA20
- **Exit**: Trailing stop, target, or time-limit

## Backtest Results (6 months: Feb–Jul 2026)

| Strategy | Trades | Wins | Losses | WR | P&L | Max DD |
|----------|--------|------|--------|----|-----|--------|
| Donchian + ADX | 133 | 99 | 34 | 74.4% | +₹1,759,383 | ₹105,412 |
| Keltner + RSI + Vol | 123 | 88 | 35 | 71.5% | +₹1,676,440 | ₹127,328 |
| Supertrend + Volume | 116 | 87 | 29 | 75.0% | +₹1,695,275 | ₹51,662 |
| **Combined** | **372** | **274** | **98** | **73.7%** | **+₹5,131,098** | **₹127,328** |

## Installation

```bash
git clone https://github.com/ki26ran/PortfolioAlpha.git
cd PortfolioAlpha
pip install -r requirements.txt
```

## Usage

### Backtest
```bash
python -c "
import sys; sys.path.insert(0, '.')
from core.backtest_engine import run_backtest
from core.registry import get_strategy
from datetime import datetime

now = datetime.now()
months = [(f'{y}-{m:02d}', y, m) for i in range(5, -1, -1) 
          for m in [(now.month - i - 1) % 12 + 1] for y in [now.year - (1 if now.month - i < 1 else 0)]]
strat = get_strategy('keltner_rsi')
trades, _ = run_backtest(strat, months=months)
print(f'Total trades: {len(trades)}, P&L: {sum(t.get(\"pnl\",0) for t in trades):+,.0f}')
"
```

### Streamlit Dashboard
```bash
streamlit run dashboard.py
```

### Scheduled Scans (Crontab)
```bash
# Stock selection at 08:30 (weekdays)
30 8 * * 1-5 cd /path/to/PortfolioAlpha && python agents/stock_selection.py

# Live trader at 09:42 (weekdays — entry phase + hourly monitor)
42 9 * * 1-5 cd /path/to/PortfolioAlpha && python agents/live_trader.py
```

## Configuration

Edit `cfg/settings.py` to adjust:
- `CAPITAL_TOTAL`: Total capital (default ₹1,500,000)
- `MAX_POSITIONS_TOTAL`: Maximum concurrent positions (default 10)
- `MAX_POSITIONS_PER_STRATEGY`: Max positions per strategy (default 3)

Strategy parameters are in `cfg/strategies.json`. Each strategy has:
- `enabled`: true/false toggle
- `universe`: Stock universe to scan
- `entry_time`: Entry mode ("zscore", "15m_945")
- `params`: Strategy-specific settings

## Dependencies

- pandas, numpy, duckdb (core)
- streamlit, plotly (dashboard)
- yfinance (data)
- requests (telegram)
- NorenRestApiPy (broker - optional)

## License

MIT
