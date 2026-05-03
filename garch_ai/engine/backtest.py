import math
import warnings

import numpy as np
import pandas as pd


INITIAL_CAPITAL = 10_000.0
RISK_FRACTION = 0.01
FALLBACK_PERIODS_PER_YEAR = 24 * 252
SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


def rounded(value: float | int | None, digits: int = 2):
    if value is None:
        return None
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def annualized_return_pct(final_equity: float, initial_capital: float, years: float) -> float:
    if final_equity <= 0 or initial_capital <= 0 or years <= 0:
        return 0

    log_annual_return = math.log(final_equity / initial_capital) / years
    if not math.isfinite(log_annual_return):
        return 0

    # Very short tests can annualize to absurd values. Keep the metric finite
    # and readable instead of letting exp/power overflow.
    max_pct = 1_000_000.0
    min_pct = -99.99
    if log_annual_return >= math.log1p(max_pct / 100):
        return max_pct
    if log_annual_return <= math.log1p(min_pct / 100):
        return min_pct

    return math.expm1(log_annual_return) * 100


def safe_to_datetime(values: pd.Series) -> pd.Series:
    raw = values.reset_index(drop=True)
    numeric = pd.to_numeric(raw, errors="coerce")
    numeric_ratio = float(numeric.notna().mean()) if len(numeric) else 0

    try:
        if numeric_ratio > 0.85:
            median_abs = float(numeric.abs().dropna().median())
            if median_abs > 1e17:
                unit = "ns"
            elif median_abs > 1e14:
                unit = "us"
            elif median_abs > 1e11:
                unit = "ms"
            elif median_abs > 1e8:
                unit = "s"
            else:
                unit = None

            if unit:
                return pd.to_datetime(numeric, errors="coerce", utc=True, unit=unit)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return pd.to_datetime(raw, errors="coerce", utc=True)
    except Exception:
        return pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns, UTC]")


def datetime_seconds(parsed: pd.Series) -> np.ndarray:
    valid = parsed.dropna()
    if valid.empty:
        return np.array([], dtype=float)

    try:
        seconds = valid.astype("int64").to_numpy(dtype=float) / 1_000_000_000
    except Exception:
        seconds = np.array(
            [stamp.value / 1_000_000_000 for stamp in valid],
            dtype=float,
        )

    seconds = seconds[np.isfinite(seconds)]
    if len(seconds) < 2:
        return seconds

    # Ignore extreme outliers that can make annualization nonsensical.
    low, high = np.nanpercentile(seconds, [1, 99])
    trimmed = seconds[(seconds >= low) & (seconds <= high)]
    return trimmed if len(trimmed) >= 2 else seconds


def build_timestamps(df: pd.DataFrame, length: int) -> tuple[list[str], pd.Series]:
    if "timestamp" in df.columns:
        raw = df["timestamp"].reset_index(drop=True)
    else:
        raw = pd.Series([None] * length)

    parsed = safe_to_datetime(raw)
    labels: list[str] = []
    for index in range(length):
        stamp = parsed.iloc[index] if index < len(parsed) else pd.NaT
        if pd.notna(stamp):
            labels.append(stamp.strftime("%Y-%m-%d %H:%M"))
        else:
            labels.append(str(index))

    return labels, parsed


def infer_periods_per_year(parsed: pd.Series) -> float:
    seconds = datetime_seconds(parsed)
    if len(seconds) < 2:
        return FALLBACK_PERIODS_PER_YEAR

    diffs = np.diff(np.sort(seconds))
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if len(diffs) == 0:
        return FALLBACK_PERIODS_PER_YEAR

    median_seconds = float(np.median(diffs))
    if median_seconds <= 0:
        return FALLBACK_PERIODS_PER_YEAR

    periods = SECONDS_PER_YEAR / median_seconds
    if not math.isfinite(periods) or periods <= 0:
        return FALLBACK_PERIODS_PER_YEAR
    return min(max(periods, 1), 525_600)


def infer_years(parsed: pd.Series, bar_count: int, periods_per_year: float) -> float:
    seconds = datetime_seconds(parsed)
    if len(seconds) >= 2:
        elapsed_seconds = float(np.nanmax(seconds) - np.nanmin(seconds))
        if math.isfinite(elapsed_seconds) and elapsed_seconds > 0:
            return max(elapsed_seconds / SECONDS_PER_YEAR, 1 / periods_per_year)

    return max(bar_count / periods_per_year, 1 / periods_per_year)


def extract_trades(df: pd.DataFrame, position: pd.Series, timestamps: list[str]) -> list[dict]:
    closes = (
        pd.to_numeric(df["close"], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .ffill()
        .bfill()
        .to_numpy()
    )
    positions = position.fillna(0).astype(int).to_numpy()
    trades: list[dict] = []
    open_trade: dict | None = None

    for index, next_side in enumerate(positions):
        price = float(closes[index])
        stamp = timestamps[index] if index < len(timestamps) else str(index)

        if open_trade is not None and next_side != open_trade["side"]:
            side = open_trade["side"]
            entry_price = open_trade["entry_price"]
            pnl_pct = (
                side * ((price / entry_price) - 1) * 100
                if entry_price and math.isfinite(entry_price) and math.isfinite(price)
                else 0
            )
            trades.append(
                {
                    **open_trade,
                    "exit_index": index,
                    "exit_time": stamp,
                    "exit_price": price,
                    "pnl_pct": float(pnl_pct),
                    "bars": index - open_trade["entry_index"],
                }
            )
            open_trade = None

        if open_trade is None and next_side != 0:
            open_trade = {
                "side": int(next_side),
                "direction": "Long" if next_side > 0 else "Short",
                "entry_index": index,
                "entry_time": stamp,
                "entry_price": price,
            }

    if open_trade is not None and len(closes) > 0:
        side = open_trade["side"]
        entry_price = open_trade["entry_price"]
        exit_price = float(closes[-1])
        pnl_pct = (
            side * ((exit_price / entry_price) - 1) * 100
            if entry_price and math.isfinite(entry_price) and math.isfinite(exit_price)
            else 0
        )
        trades.append(
            {
                **open_trade,
                "exit_index": len(closes) - 1,
                "exit_time": timestamps[-1] if timestamps else str(len(closes) - 1),
                "exit_price": exit_price,
                "pnl_pct": float(pnl_pct),
                "bars": len(closes) - 1 - open_trade["entry_index"],
            }
        )

    return trades


def summarize_trades(trades: list[dict]) -> dict:
    if not trades:
        return {
            "trades_total": 0,
            "long_trades": 0,
            "short_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "profit_factor": None,
            "average_trade": 0,
            "best_trade": 0,
            "worst_trade": 0,
            "avg_bars_in_trade": 0,
        }

    pnls = np.array([trade["pnl_pct"] for trade in trades], dtype=float)
    pnls = pnls[np.isfinite(pnls)]
    if len(pnls) == 0:
        return {
            "trades_total": len(trades),
            "long_trades": sum(1 for trade in trades if trade["side"] > 0),
            "short_trades": sum(1 for trade in trades if trade["side"] < 0),
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "profit_factor": None,
            "average_trade": 0,
            "best_trade": 0,
            "worst_trade": 0,
            "avg_bars_in_trade": 0,
        }
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_profit = float(wins.sum())
    gross_loss = abs(float(losses.sum()))
    profit_factor = None if gross_loss == 0 else gross_profit / gross_loss

    return {
        "trades_total": len(trades),
        "long_trades": sum(1 for trade in trades if trade["side"] > 0),
        "short_trades": sum(1 for trade in trades if trade["side"] < 0),
        "winning_trades": int(len(wins)),
        "losing_trades": int(len(losses)),
        "win_rate": rounded((len(wins) / len(trades)) * 100),
        "profit_factor": rounded(profit_factor),
        "average_trade": rounded(float(pnls.mean())),
        "best_trade": rounded(float(pnls.max())),
        "worst_trade": rounded(float(pnls.min())),
        "avg_bars_in_trade": rounded(float(np.mean([trade["bars"] for trade in trades])), 1),
    }


def run_backtest(df: pd.DataFrame) -> dict:
    df = df.copy()
    df["signal"] = pd.to_numeric(df["signal"], errors="coerce").fillna(0).clip(-1, 1)

    close = (
        pd.to_numeric(df["close"], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .ffill()
        .bfill()
    )
    if close.isna().all():
        raise ValueError("Backtest data has no valid close prices")

    df["close"] = close
    returns = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)
    position = df["signal"].shift(1).fillna(0)
    strategy_returns = (position * returns).replace([np.inf, -np.inf], np.nan).fillna(0)
    equity_multiplier = (1 + strategy_returns).cumprod()
    account_equity = INITIAL_CAPITAL * equity_multiplier

    timestamps, parsed_timestamps = build_timestamps(df, len(account_equity))

    periods_per_year = infer_periods_per_year(parsed_timestamps)
    years = infer_years(parsed_timestamps, len(strategy_returns), periods_per_year)

    final_equity = float(account_equity.iloc[-1]) if len(account_equity) else INITIAL_CAPITAL
    total_return_pct = ((final_equity / INITIAL_CAPITAL) - 1) * 100
    total_return_amount = final_equity - INITIAL_CAPITAL
    first_close = float(close.iloc[0])
    last_close = float(close.iloc[-1])
    if first_close and math.isfinite(first_close):
        benchmark_multiplier = close / first_close
    else:
        benchmark_multiplier = pd.Series(1.0, index=close.index)
    benchmark_equity = INITIAL_CAPITAL * benchmark_multiplier.replace([np.inf, -np.inf], np.nan).fillna(1)

    annual_return_pct = annualized_return_pct(final_equity, INITIAL_CAPITAL, years)
    annual_return_amount = INITIAL_CAPITAL * annual_return_pct / 100

    peak = account_equity.cummax()
    drawdown_amount = account_equity - peak
    drawdown_pct = (account_equity / peak - 1).fillna(0)
    max_drawdown_amount = abs(float(drawdown_amount.min())) if len(drawdown_amount) else 0
    max_drawdown_pct = abs(float(drawdown_pct.min())) * 100 if len(drawdown_pct) else 0

    returns_std = float(strategy_returns.std(ddof=0))
    sharpe_ratio = (
        float(strategy_returns.mean()) / returns_std * math.sqrt(periods_per_year)
        if returns_std > 0
        else None
    )
    downside = strategy_returns[strategy_returns < 0]
    downside_std = float(downside.std(ddof=0)) if len(downside) else 0
    sortino_ratio = (
        float(strategy_returns.mean()) / downside_std * math.sqrt(periods_per_year)
        if downside_std > 0
        else None
    )

    trades = extract_trades(df, position, timestamps)
    trade_summary = summarize_trades(trades)
    buy_hold_return = (
        (last_close / first_close - 1) * 100
        if first_close and math.isfinite(first_close) and math.isfinite(last_close)
        else 0
    )
    exposure = (position.abs() > 0).mean() * 100 if len(position) else 0
    annual_volatility = returns_std * math.sqrt(periods_per_year) * 100

    return {
        "initial_capital": INITIAL_CAPITAL,
        "risk_percent": RISK_FRACTION * 100,
        "equity": [rounded(value, 2) for value in account_equity.tolist()],
        "equity_pct": [rounded((value - 1) * 100, 4) for value in equity_multiplier.tolist()],
        "benchmark_equity": [rounded(value, 2) for value in benchmark_equity.tolist()],
        "benchmark_pct": [rounded((value - 1) * 100, 4) for value in benchmark_multiplier.tolist()],
        "timestamps": timestamps,
        "total_return": rounded(total_return_pct),
        "total_return_pct": rounded(total_return_pct),
        "total_return_amount": rounded(total_return_amount),
        "total_return_amount_at_1pct": rounded(INITIAL_CAPITAL * RISK_FRACTION * total_return_pct / 100),
        "annual_return_pct": rounded(annual_return_pct),
        "annual_return_amount": rounded(annual_return_amount),
        "annual_return_amount_at_1pct": rounded(INITIAL_CAPITAL * RISK_FRACTION * annual_return_pct / 100),
        "final_equity": rounded(final_equity),
        "max_drawdown_amount": rounded(max_drawdown_amount),
        "max_drawdown_pct": rounded(max_drawdown_pct),
        "relative_drawdown_pct": rounded(max_drawdown_amount / INITIAL_CAPITAL * 100),
        "sharpe_ratio": rounded(sharpe_ratio),
        "sortino_ratio": rounded(sortino_ratio),
        "annual_volatility_pct": rounded(annual_volatility),
        "buy_hold_return_pct": rounded(buy_hold_return),
        "exposure_pct": rounded(exposure),
        "num_bars": len(df),
        "periods_per_year": rounded(periods_per_year, 1),
        "years": rounded(years, 2),
        "trades": [
            {
                **trade,
                "entry_price": rounded(trade["entry_price"], 2),
                "exit_price": rounded(trade["exit_price"], 2),
                "pnl_pct": rounded(trade["pnl_pct"]),
                "pnl_amount_at_1pct": rounded(INITIAL_CAPITAL * RISK_FRACTION * trade["pnl_pct"] / 100),
            }
            for trade in trades[:50]
        ],
        **trade_summary,
    }
