import math
import os
import warnings

import numpy as np
import pandas as pd


INITIAL_CAPITAL = 10_000.0
RISK_FRACTION = 0.01
FALLBACK_PERIODS_PER_YEAR = 24 * 252
SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60
MAX_RESPONSE_POINTS = int(os.getenv("BACKTEST_MAX_RESPONSE_POINTS", "1800"))
MAX_RETURNED_TRADES = int(os.getenv("BACKTEST_MAX_RETURNED_TRADES", "50"))


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


def clean_close_array(values: pd.Series) -> np.ndarray:
    close = (
        pd.to_numeric(values, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .ffill()
        .bfill()
    )
    if close.isna().all():
        raise ValueError("Backtest data has no valid close prices")
    return close.to_numpy(dtype=np.float64, copy=False)


def signal_array(values: pd.Series, length: int) -> np.ndarray:
    signal = pd.to_numeric(values, errors="coerce").to_numpy(dtype=np.float64, copy=False)
    if len(signal) != length:
        raise ValueError("Signal length does not match market data length")
    signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(signal, -1, 1).astype(np.int8, copy=False)


def returns_array(close: np.ndarray) -> np.ndarray:
    returns = np.zeros(len(close), dtype=np.float64)
    if len(close) > 1:
        previous = close[:-1]
        current = close[1:]
        valid = np.isfinite(previous) & np.isfinite(current) & (previous != 0)
        returns[1:][valid] = current[valid] / previous[valid] - 1
    return np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)


def timestamp_seconds(df: pd.DataFrame, length: int) -> np.ndarray | None:
    if "_timestamp_ns" in df.columns:
        numeric = pd.to_numeric(df["_timestamp_ns"], errors="coerce").to_numpy(
            dtype=np.float64,
            copy=False,
        )
        if len(numeric) == length:
            seconds = numeric / 1_000_000_000
            if np.isfinite(seconds).sum() >= 2:
                return seconds

    if "timestamp" not in df.columns:
        return None

    parsed = safe_to_datetime(df["timestamp"])
    seconds = np.full(length, np.nan, dtype=np.float64)
    count = min(length, len(parsed))
    if count == 0:
        return seconds

    mask = parsed.iloc[:count].notna().to_numpy()
    if mask.any():
        parsed_valid = parsed.iloc[:count][mask]
        seconds[np.arange(count)[mask]] = (
            parsed_valid.astype("int64").to_numpy(dtype=np.float64) / 1_000_000_000
        )
    return seconds if np.isfinite(seconds).sum() >= 2 else None


def robust_seconds(seconds: np.ndarray | None) -> np.ndarray:
    if seconds is None:
        return np.array([], dtype=np.float64)

    valid = seconds[np.isfinite(seconds)]
    if len(valid) < 2:
        return valid

    low, high = np.nanpercentile(valid, [1, 99])
    trimmed = valid[(valid >= low) & (valid <= high)]
    return trimmed if len(trimmed) >= 2 else valid


def infer_periods_per_year(seconds: np.ndarray | None) -> float:
    valid = robust_seconds(seconds)
    if len(valid) < 2:
        return FALLBACK_PERIODS_PER_YEAR

    diffs = np.diff(np.sort(valid))
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


def infer_years(seconds: np.ndarray | None, bar_count: int, periods_per_year: float) -> float:
    valid = robust_seconds(seconds)
    if len(valid) >= 2:
        elapsed_seconds = float(np.nanmax(valid) - np.nanmin(valid))
        if math.isfinite(elapsed_seconds) and elapsed_seconds > 0:
            return max(elapsed_seconds / SECONDS_PER_YEAR, 1 / periods_per_year)

    return max(bar_count / periods_per_year, 1 / periods_per_year)


def downsample_indices(length: int, max_points: int = MAX_RESPONSE_POINTS) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=np.int64)
    if length <= max_points:
        return np.arange(length, dtype=np.int64)

    indices = np.unique(np.rint(np.linspace(0, length - 1, max_points)).astype(np.int64))
    if indices[0] != 0:
        indices = np.insert(indices, 0, 0)
    if indices[-1] != length - 1:
        indices = np.append(indices, length - 1)
    return indices


def format_labels(df: pd.DataFrame, indices: np.ndarray, seconds: np.ndarray | None) -> list[str]:
    labels = np.array([str(int(index)) for index in indices], dtype=object)

    if seconds is not None and len(seconds):
        selected_seconds = seconds[indices]
        valid = np.isfinite(selected_seconds)
        if valid.any():
            parsed = pd.to_datetime(selected_seconds[valid], unit="s", errors="coerce", utc=True)
            formatted = pd.Series(parsed).dt.strftime("%Y-%m-%d %H:%M")
            formatted = formatted.fillna(pd.Series(labels[valid], index=formatted.index))
            labels[valid] = formatted.to_numpy(dtype=object)
            return labels.tolist()

    if "timestamp" in df.columns:
        raw = df["timestamp"].reset_index(drop=True).iloc[indices]
        parsed = safe_to_datetime(raw)
        mask = parsed.notna().to_numpy()
        if mask.any():
            formatted = parsed.dt.strftime("%Y-%m-%d %H:%M").fillna("")
            labels[mask] = formatted[mask].to_numpy(dtype=object)

    return labels.tolist()


def extract_trade_arrays(close: np.ndarray, position: np.ndarray) -> dict:
    length = len(position)
    empty = {
        "entry_idx": np.array([], dtype=np.int64),
        "exit_idx": np.array([], dtype=np.int64),
        "sides": np.array([], dtype=np.int8),
        "pnl_pct": np.array([], dtype=np.float64),
        "bars": np.array([], dtype=np.int64),
    }
    if length == 0:
        return empty

    changes = np.flatnonzero(np.r_[True, position[1:] != position[:-1]])
    if len(changes) == 0:
        return empty

    segment_sides = position[changes].astype(np.int8, copy=False)
    exits = np.r_[changes[1:], length - 1].astype(np.int64)
    entries = changes.astype(np.int64)
    active = segment_sides != 0
    if not active.any():
        return empty

    entries = entries[active]
    exits = exits[active]
    sides = segment_sides[active]
    entry_prices = close[entries]
    exit_prices = close[exits]

    pnl_pct = np.zeros(len(entries), dtype=np.float64)
    valid = (
        np.isfinite(entry_prices)
        & np.isfinite(exit_prices)
        & (entry_prices != 0)
    )
    pnl_pct[valid] = sides[valid] * (exit_prices[valid] / entry_prices[valid] - 1) * 100

    return {
        "entry_idx": entries,
        "exit_idx": exits,
        "sides": sides,
        "pnl_pct": pnl_pct,
        "bars": exits - entries,
    }


def summarize_trades(trade_data: dict) -> dict:
    sides = trade_data["sides"]
    pnls = trade_data["pnl_pct"]
    bars = trade_data["bars"]
    total = int(len(pnls))

    if total == 0:
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

    finite_pnls = pnls[np.isfinite(pnls)]
    if len(finite_pnls) == 0:
        finite_pnls = np.array([0.0], dtype=np.float64)

    wins = finite_pnls[finite_pnls > 0]
    losses = finite_pnls[finite_pnls < 0]
    gross_profit = float(wins.sum())
    gross_loss = abs(float(losses.sum()))
    profit_factor = None if gross_loss == 0 else gross_profit / gross_loss

    return {
        "trades_total": total,
        "long_trades": int(np.sum(sides > 0)),
        "short_trades": int(np.sum(sides < 0)),
        "winning_trades": int(len(wins)),
        "losing_trades": int(len(losses)),
        "win_rate": rounded((len(wins) / total) * 100),
        "profit_factor": rounded(profit_factor),
        "average_trade": rounded(float(finite_pnls.mean())),
        "best_trade": rounded(float(finite_pnls.max())),
        "worst_trade": rounded(float(finite_pnls.min())),
        "avg_bars_in_trade": rounded(float(np.mean(bars)) if len(bars) else 0, 1),
    }


def build_trade_rows(
    df: pd.DataFrame,
    close: np.ndarray,
    seconds: np.ndarray | None,
    trade_data: dict,
) -> list[dict]:
    total = len(trade_data["pnl_pct"])
    if total == 0:
        return []

    start = max(0, total - MAX_RETURNED_TRADES)
    selected = np.arange(start, total, dtype=np.int64)
    label_indices = np.unique(
        np.r_[trade_data["entry_idx"][selected], trade_data["exit_idx"][selected]]
    )
    label_lookup = dict(zip(label_indices.tolist(), format_labels(df, label_indices, seconds)))

    rows: list[dict] = []
    for trade_index in selected:
        side = int(trade_data["sides"][trade_index])
        entry_index = int(trade_data["entry_idx"][trade_index])
        exit_index = int(trade_data["exit_idx"][trade_index])
        pnl_pct = float(trade_data["pnl_pct"][trade_index])
        rows.append(
            {
                "side": side,
                "direction": "Long" if side > 0 else "Short",
                "entry_index": entry_index,
                "entry_time": label_lookup.get(entry_index, str(entry_index)),
                "entry_price": rounded(float(close[entry_index]), 2),
                "exit_index": exit_index,
                "exit_time": label_lookup.get(exit_index, str(exit_index)),
                "exit_price": rounded(float(close[exit_index]), 2),
                "pnl_pct": rounded(pnl_pct),
                "pnl_amount_at_1pct": rounded(INITIAL_CAPITAL * RISK_FRACTION * pnl_pct / 100),
                "bars": int(trade_data["bars"][trade_index]),
            }
        )
    return rows


def rounded_list(values: np.ndarray, digits: int = 2) -> list:
    return [rounded(float(value), digits) for value in values]


def run_backtest(df: pd.DataFrame) -> dict:
    if "signal" not in df.columns:
        raise ValueError("Strategy did not produce a 'signal' column")
    if "close" not in df.columns:
        raise ValueError("Backtest data has no close column")

    length = len(df)
    close = clean_close_array(df["close"])
    signal = signal_array(df["signal"], length)

    position = np.empty(length, dtype=np.int8)
    if length:
        position[0] = 0
        position[1:] = signal[:-1]

    returns = returns_array(close)
    strategy_returns = np.nan_to_num(position.astype(np.float64) * returns, nan=0.0, posinf=0.0, neginf=0.0)
    equity_multiplier = np.cumprod(1 + strategy_returns)
    account_equity = INITIAL_CAPITAL * equity_multiplier

    seconds = timestamp_seconds(df, length)
    periods_per_year = infer_periods_per_year(seconds)
    years = infer_years(seconds, len(strategy_returns), periods_per_year)

    final_equity = float(account_equity[-1]) if len(account_equity) else INITIAL_CAPITAL
    total_return_pct = ((final_equity / INITIAL_CAPITAL) - 1) * 100
    total_return_amount = final_equity - INITIAL_CAPITAL

    first_close = float(close[0]) if len(close) else 0
    last_close = float(close[-1]) if len(close) else 0
    if first_close and math.isfinite(first_close):
        benchmark_multiplier = np.nan_to_num(close / first_close, nan=1.0, posinf=1.0, neginf=1.0)
    else:
        benchmark_multiplier = np.ones(length, dtype=np.float64)
    benchmark_equity = INITIAL_CAPITAL * benchmark_multiplier

    annual_return_pct = annualized_return_pct(final_equity, INITIAL_CAPITAL, years)
    annual_return_amount = INITIAL_CAPITAL * annual_return_pct / 100

    peak = np.maximum.accumulate(account_equity) if len(account_equity) else np.array([], dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown_pct = np.where(peak != 0, account_equity / peak - 1, 0)
    drawdown_amount = account_equity - peak if len(peak) else np.array([], dtype=np.float64)
    max_drawdown_amount = abs(float(np.nanmin(drawdown_amount))) if len(drawdown_amount) else 0
    max_drawdown_pct = abs(float(np.nanmin(drawdown_pct))) * 100 if len(drawdown_pct) else 0

    returns_std = float(np.std(strategy_returns))
    sharpe_ratio = (
        float(np.mean(strategy_returns)) / returns_std * math.sqrt(periods_per_year)
        if returns_std > 0
        else None
    )
    downside = strategy_returns[strategy_returns < 0]
    downside_std = float(np.std(downside)) if len(downside) else 0
    sortino_ratio = (
        float(np.mean(strategy_returns)) / downside_std * math.sqrt(periods_per_year)
        if downside_std > 0
        else None
    )

    trade_data = extract_trade_arrays(close, position)
    trade_summary = summarize_trades(trade_data)

    buy_hold_return = (
        (last_close / first_close - 1) * 100
        if first_close and math.isfinite(first_close) and math.isfinite(last_close)
        else 0
    )
    exposure = float(np.mean(np.abs(position) > 0) * 100) if len(position) else 0
    annual_volatility = returns_std * math.sqrt(periods_per_year) * 100

    chart_indices = downsample_indices(length)
    timestamps = format_labels(df, chart_indices, seconds)
    chart_step = max(1, math.ceil(length / max(1, len(chart_indices)))) if length else 1

    return {
        "initial_capital": INITIAL_CAPITAL,
        "risk_percent": RISK_FRACTION * 100,
        "equity": rounded_list(account_equity[chart_indices], 2),
        "equity_pct": rounded_list((equity_multiplier[chart_indices] - 1) * 100, 4),
        "benchmark_equity": rounded_list(benchmark_equity[chart_indices], 2),
        "benchmark_pct": rounded_list((benchmark_multiplier[chart_indices] - 1) * 100, 4),
        "timestamps": timestamps,
        "chart_points": int(len(chart_indices)),
        "chart_sample_step": int(chart_step),
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
        "num_bars": length,
        "periods_per_year": rounded(periods_per_year, 1),
        "years": rounded(years, 2),
        "trades": build_trade_rows(df, close, seconds, trade_data),
        **trade_summary,
    }
