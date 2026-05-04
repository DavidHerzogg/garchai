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
MAX_ALPHA_DECAY_LAG = int(os.getenv("BACKTEST_MAX_ALPHA_DECAY_LAG", "96"))
MAX_RETURN_DISTRIBUTION_BINS = int(os.getenv("BACKTEST_RETURN_DISTRIBUTION_BINS", "36"))


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

    # Quant metrics
    avg_trade = float(finite_pnls.mean())
    win_rate = (len(wins) / total) * 100 if total > 0 else 0
    expectancy = (win_rate / 100 * (wins.mean() if len(wins) > 0 else 0)) + \
                 ((1 - win_rate / 100) * (losses.mean() if len(losses) > 0 else 0))

    return {
        "trades_total": total,
        "long_trades": int(np.sum(sides > 0)),
        "short_trades": int(np.sum(sides < 0)),
        "winning_trades": int(len(wins)),
        "losing_trades": int(len(losses)),
        "win_rate": rounded(win_rate),
        "profit_factor": rounded(profit_factor),
        "expectancy": rounded(expectancy),
        "average_trade": rounded(avg_trade),
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


def finite_values(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return values[np.isfinite(values)]


def safe_percentile(values: np.ndarray, percentile: float) -> float | None:
    finite = finite_values(values)
    if len(finite) == 0:
        return None
    return float(np.nanpercentile(finite, percentile))


def safe_correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    count = min(len(left), len(right))
    if count < 3:
        return None

    left = left[:count]
    right = right[:count]
    mask = np.isfinite(left) & np.isfinite(right)
    if mask.sum() < 3:
        return None
    left = left[mask]
    right = right[mask]
    if float(np.std(left)) == 0 or float(np.std(right)) == 0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def compound_return_pct(returns: np.ndarray) -> float:
    finite = np.nan_to_num(np.asarray(returns, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    if len(finite) == 0:
        return 0
    return (float(np.prod(1 + finite)) - 1) * 100


def max_consecutive_true(mask: np.ndarray) -> int:
    mask = np.asarray(mask, dtype=bool)
    if len(mask) == 0 or not mask.any():
        return 0
    padded = np.r_[False, mask, False]
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    lengths = changes[1::2] - changes[::2]
    return int(lengths.max()) if len(lengths) else 0


def return_distribution(values: np.ndarray) -> list[dict]:
    returns_pct = finite_values(values * 100)
    if len(returns_pct) == 0:
        return []

    bins = min(MAX_RETURN_DISTRIBUTION_BINS, max(8, int(math.sqrt(len(returns_pct)))))
    counts, edges = np.histogram(returns_pct, bins=bins)
    rows: list[dict] = []
    for index, count in enumerate(counts):
        start = float(edges[index])
        end = float(edges[index + 1])
        rows.append(
            {
                "bin_start_pct": rounded(start, 4),
                "bin_end_pct": rounded(end, 4),
                "bin_mid_pct": rounded((start + end) / 2, 4),
                "count": int(count),
            }
        )
    return rows


def rolling_window(length: int, periods_per_year: float) -> int:
    if length <= 2:
        return 2
    monthly = int(max(24, min(periods_per_year / 12, 24 * 30)))
    return int(min(max(12, monthly), max(12, length // 3)))


def rolling_research_series(
    strategy_returns: np.ndarray,
    chart_indices: np.ndarray,
    periods_per_year: float,
) -> dict:
    if len(strategy_returns) == 0:
        return {
            "rolling_window": 0,
            "rolling_sharpe": [],
            "rolling_volatility_pct": [],
            "rolling_win_rate_pct": [],
            "rolling_profit_factor": [],
        }

    window = rolling_window(len(strategy_returns), periods_per_year)
    series = pd.Series(strategy_returns)
    rolling_mean = series.rolling(window, min_periods=max(4, window // 3)).mean()
    rolling_std = series.rolling(window, min_periods=max(4, window // 3)).std(ddof=0)
    rolling_sharpe = rolling_mean / rolling_std.replace(0, np.nan) * math.sqrt(periods_per_year)
    rolling_vol = rolling_std * math.sqrt(periods_per_year) * 100
    rolling_win_rate = (series > 0).rolling(window, min_periods=max(4, window // 3)).mean() * 100
    gross_wins = series.clip(lower=0).rolling(window, min_periods=max(4, window // 3)).sum()
    gross_losses = (-series.clip(upper=0)).rolling(window, min_periods=max(4, window // 3)).sum()
    rolling_profit_factor = gross_wins / gross_losses.replace(0, np.nan)

    return {
        "rolling_window": int(window),
        "rolling_sharpe": rounded_list(rolling_sharpe.to_numpy()[chart_indices], 2),
        "rolling_volatility_pct": rounded_list(rolling_vol.to_numpy()[chart_indices], 2),
        "rolling_win_rate_pct": rounded_list(rolling_win_rate.to_numpy()[chart_indices], 2),
        "rolling_profit_factor": rounded_list(rolling_profit_factor.to_numpy()[chart_indices], 2),
    }


def segment_drawdown_pct(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0
    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = np.where(peak != 0, equity / peak - 1, 0)
    return abs(float(np.nanmin(drawdown))) * 100


def validation_fold_report(
    strategy_returns: np.ndarray,
    periods_per_year: float,
    fold_count: int = 8,
) -> list[dict]:
    length = len(strategy_returns)
    if length < 4:
        return []

    fold_count = max(2, min(fold_count, length))
    folds = np.array_split(np.arange(length, dtype=np.int64), fold_count)
    rows: list[dict] = []
    for fold_index, indices in enumerate(folds, start=1):
        if len(indices) == 0:
            continue
        returns = strategy_returns[indices]
        equity = np.cumprod(1 + np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0))
        std = float(np.std(returns))
        sharpe = (
            float(np.mean(returns)) / std * math.sqrt(periods_per_year)
            if std > 0
            else None
        )
        rows.append(
            {
                "fold": fold_index,
                "bars": int(len(indices)),
                "return_pct": rounded(compound_return_pct(returns), 2),
                "sharpe_ratio": rounded(sharpe, 2),
                "max_drawdown_pct": rounded(segment_drawdown_pct(equity), 2),
                "hit_rate_pct": rounded(float(np.mean(returns > 0) * 100), 2),
            }
        )
    return rows


def monthly_return_report(seconds: np.ndarray | None, account_equity: np.ndarray) -> list[dict]:
    if seconds is None or len(seconds) != len(account_equity):
        return []

    mask = np.isfinite(seconds) & np.isfinite(account_equity)
    if mask.sum() < 2:
        return []

    parsed = pd.to_datetime(seconds[mask], unit="s", errors="coerce", utc=True)
    equity = account_equity[mask]
    valid = pd.Series(parsed).notna().to_numpy()
    if valid.sum() < 2:
        return []

    parsed = parsed[valid].tz_convert(None)
    equity = equity[valid]
    periods = pd.PeriodIndex(parsed, freq="M")
    rows: list[dict] = []
    for period in periods.unique():
        period_mask = periods == period
        values = equity[period_mask]
        if len(values) < 2 or values[0] == 0:
            continue
        rows.append(
            {
                "year": int(period.year),
                "month": int(period.month),
                "label": str(period),
                "return_pct": rounded((float(values[-1]) / float(values[0]) - 1) * 100, 2),
            }
        )
    return rows[-144:]


def annual_return_report(monthly_returns: list[dict]) -> list[dict]:
    if not monthly_returns:
        return []

    rows: list[dict] = []
    by_year: dict[int, list[float]] = {}
    for row in monthly_returns:
        value = row.get("return_pct")
        if value is None:
            continue
        by_year.setdefault(int(row["year"]), []).append(float(value) / 100)

    for year, returns in sorted(by_year.items()):
        rows.append(
            {
                "year": year,
                "return_pct": rounded((float(np.prod(1 + np.asarray(returns))) - 1) * 100, 2),
            }
        )
    return rows


def trade_pnl_report(trade_data: dict, max_points: int = 120) -> list[dict]:
    pnls = trade_data["pnl_pct"]
    if len(pnls) == 0:
        return []

    start = max(0, len(pnls) - max_points)
    selected = pnls[start:]
    cumulative = np.cumsum(np.nan_to_num(selected, nan=0.0, posinf=0.0, neginf=0.0))
    return [
        {
            "trade": int(start + index + 1),
            "pnl_pct": rounded(float(pnl), 2),
            "cumulative_pnl_pct": rounded(float(cumulative[index]), 2),
        }
        for index, pnl in enumerate(selected)
    ]


def alpha_decay_report(signal: np.ndarray, close: np.ndarray, max_lag: int = MAX_ALPHA_DECAY_LAG) -> dict:
    length = len(close)
    if length < 10:
        return {"half_life_bars": None, "edge_by_lag": []}

    max_lag = int(max(1, min(max_lag, max(1, length // 5))))
    signal_float = signal.astype(np.float64, copy=False)
    active = signal_float != 0
    rows: list[dict] = []

    for lag in range(1, max_lag + 1):
        entry_prices = close[:-lag]
        exit_prices = close[lag:]
        valid = np.isfinite(entry_prices) & np.isfinite(exit_prices) & (entry_prices != 0)
        forward_returns = np.zeros(len(entry_prices), dtype=np.float64)
        forward_returns[valid] = exit_prices[valid] / entry_prices[valid] - 1
        directional_edge = signal_float[:-lag] * forward_returns * 100
        active_mask = active[:-lag] & np.isfinite(directional_edge)

        if active_mask.sum() == 0:
            mean_edge = None
            hit_rate = None
        else:
            active_edge = directional_edge[active_mask]
            mean_edge = float(np.mean(active_edge))
            hit_rate = float(np.mean(active_edge > 0) * 100)

        ic = safe_correlation(signal_float[:-lag][valid], forward_returns[valid])
        rows.append(
            {
                "lag": lag,
                "mean_edge_pct": rounded(mean_edge, 5),
                "hit_rate_pct": rounded(hit_rate, 2),
                "ic": rounded(ic, 4),
                "samples": int(active_mask.sum()),
            }
        )

    edge_values = np.array(
        [
            abs(float(row["mean_edge_pct"]))
            if row.get("mean_edge_pct") is not None
            else np.nan
            for row in rows
        ],
        dtype=np.float64,
    )
    lags = np.arange(1, len(edge_values) + 1, dtype=np.float64)
    finite = np.isfinite(edge_values) & (edge_values > 0)
    half_life = None
    if finite.any():
        first_index = int(np.flatnonzero(finite)[0])
        first_edge = float(edge_values[first_index])
        below_half = np.flatnonzero(finite & (lags > lags[first_index]) & (edge_values <= first_edge / 2))
        if len(below_half):
            half_life = float(lags[int(below_half[0])])
        elif finite.sum() >= 4:
            x = lags[finite]
            y = np.log(edge_values[finite])
            slope, _ = np.polyfit(x, y, 1)
            if math.isfinite(float(slope)) and slope < 0:
                half_life = float(-math.log(2) / slope)

    return {
        "half_life_bars": rounded(half_life, 2),
        "edge_by_lag": rows,
    }


def regime_metrics(
    returns: np.ndarray,
    strategy_returns: np.ndarray,
    position: np.ndarray,
    mask: np.ndarray,
    periods_per_year: float,
) -> dict:
    mask = np.asarray(mask, dtype=bool)
    if len(mask) != len(strategy_returns) or not mask.any():
        return {
            "bars": 0,
            "return_pct": 0,
            "sharpe_ratio": None,
            "hit_rate_pct": 0,
            "exposure_pct": 0,
        }

    selected_returns = strategy_returns[mask]
    std = float(np.std(selected_returns))
    sharpe = (
        float(np.mean(selected_returns)) / std * math.sqrt(periods_per_year)
        if std > 0
        else None
    )
    return {
        "bars": int(mask.sum()),
        "return_pct": rounded(compound_return_pct(selected_returns), 2),
        "sharpe_ratio": rounded(sharpe, 2),
        "hit_rate_pct": rounded(float(np.mean(selected_returns > 0) * 100), 2),
        "exposure_pct": rounded(float(np.mean(np.abs(position[mask]) > 0) * 100), 2),
    }


def regime_report(
    close: np.ndarray,
    returns: np.ndarray,
    strategy_returns: np.ndarray,
    position: np.ndarray,
    periods_per_year: float,
) -> list[dict]:
    length = len(close)
    if length < 30:
        return []

    window = min(max(24, int(periods_per_year / 24)), max(24, length // 4))
    close_series = pd.Series(close)
    return_series = pd.Series(returns)
    realized_vol = return_series.rolling(window, min_periods=max(8, window // 3)).std().to_numpy()
    fast_window = max(4, window // 4)
    fast_ma = close_series.rolling(fast_window, min_periods=max(3, fast_window // 2)).mean()
    slow_ma = close_series.rolling(window, min_periods=max(8, window // 3)).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        trend_score = ((fast_ma / slow_ma) - 1).to_numpy()

    rows: list[dict] = []
    vol_valid = np.isfinite(realized_vol)
    if vol_valid.sum() >= 10:
        low, high = np.nanpercentile(realized_vol[vol_valid], [33.333, 66.667])
        regimes = [
            ("Low Vol", vol_valid & (realized_vol <= low)),
            ("Mid Vol", vol_valid & (realized_vol > low) & (realized_vol <= high)),
            ("High Vol", vol_valid & (realized_vol > high)),
        ]
        for name, mask in regimes:
            rows.append({"regime": name, **regime_metrics(returns, strategy_returns, position, mask, periods_per_year)})

    trend_valid = np.isfinite(trend_score)
    if trend_valid.sum() >= 10:
        low, high = np.nanpercentile(trend_score[trend_valid], [33.333, 66.667])
        regimes = [
            ("Down Trend", trend_valid & (trend_score <= low)),
            ("Range", trend_valid & (trend_score > low) & (trend_score <= high)),
            ("Up Trend", trend_valid & (trend_score > high)),
        ]
        for name, mask in regimes:
            rows.append({"regime": name, **regime_metrics(returns, strategy_returns, position, mask, periods_per_year)})

    return rows


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
    ulcer_index = (
        math.sqrt(float(np.nanmean(np.square(drawdown_pct * 100))))
        if len(drawdown_pct)
        else 0
    )
    longest_drawdown_bars = max_consecutive_true(drawdown_pct < 0)

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
    trade_pnls = finite_values(trade_data["pnl_pct"])
    winning_trade_pnls = trade_pnls[trade_pnls > 0]
    losing_trade_pnls = trade_pnls[trade_pnls < 0]
    avg_win_pct = float(np.mean(winning_trade_pnls)) if len(winning_trade_pnls) else None
    avg_loss_pct = float(np.mean(losing_trade_pnls)) if len(losing_trade_pnls) else None
    payoff_ratio = (
        abs(avg_win_pct / avg_loss_pct)
        if avg_win_pct is not None and avg_loss_pct not in (None, 0)
        else None
    )
    consecutive_wins = max_consecutive_true(trade_data["pnl_pct"] > 0)
    consecutive_losses = max_consecutive_true(trade_data["pnl_pct"] < 0)

    buy_hold_return = (
        (last_close / first_close - 1) * 100
        if first_close and math.isfinite(first_close) and math.isfinite(last_close)
        else 0
    )
    exposure = float(np.mean(np.abs(position) > 0) * 100) if len(position) else 0
    annual_volatility = returns_std * math.sqrt(periods_per_year) * 100
    trades_per_year = len(trade_pnls) / years if years > 0 else 0

    benchmark_annual_return_pct = annualized_return_pct(
        float(benchmark_equity[-1]) if len(benchmark_equity) else INITIAL_CAPITAL,
        INITIAL_CAPITAL,
        years,
    )
    benchmark_peak = (
        np.maximum.accumulate(benchmark_equity)
        if len(benchmark_equity)
        else np.array([], dtype=np.float64)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        benchmark_drawdown_pct = np.where(benchmark_peak != 0, benchmark_equity / benchmark_peak - 1, 0)
    benchmark_max_drawdown_pct = (
        abs(float(np.nanmin(benchmark_drawdown_pct))) * 100
        if len(benchmark_drawdown_pct)
        else 0
    )

    finite_strategy_returns = finite_values(strategy_returns)
    var_95_raw = safe_percentile(strategy_returns, 5)
    var_99_raw = safe_percentile(strategy_returns, 1)
    expected_shortfall_95 = None
    expected_shortfall_99 = None
    if var_95_raw is not None:
        tail = finite_strategy_returns[finite_strategy_returns <= var_95_raw]
        expected_shortfall_95 = -float(np.mean(tail)) * 100 if len(tail) else None
    if var_99_raw is not None:
        tail = finite_strategy_returns[finite_strategy_returns <= var_99_raw]
        expected_shortfall_99 = -float(np.mean(tail)) * 100 if len(tail) else None

    return_series = pd.Series(finite_strategy_returns)
    skewness = float(return_series.skew()) if len(return_series) >= 3 else None
    kurtosis = float(return_series.kurt()) if len(return_series) >= 4 else None
    p95 = safe_percentile(strategy_returns, 95)
    p5 = safe_percentile(strategy_returns, 5)
    tail_ratio = (
        abs(p95 / p5)
        if p95 is not None and p5 not in (None, 0)
        else None
    )
    gross_positive_returns = float(np.sum(strategy_returns[strategy_returns > 0]))
    gross_negative_returns = abs(float(np.sum(strategy_returns[strategy_returns < 0])))
    omega_ratio = (
        gross_positive_returns / gross_negative_returns
        if gross_negative_returns > 0
        else None
    )

    correlation_to_benchmark = safe_correlation(strategy_returns, returns)
    benchmark_variance = float(np.var(returns))
    beta_to_benchmark = (
        float(np.cov(strategy_returns, returns)[0, 1] / benchmark_variance)
        if len(strategy_returns) >= 2 and benchmark_variance > 0
        else None
    )
    alpha_annual_pct = (
        (float(np.mean(strategy_returns)) - beta_to_benchmark * float(np.mean(returns)))
        * periods_per_year
        * 100
        if beta_to_benchmark is not None
        else None
    )
    excess_returns = strategy_returns - returns
    tracking_error_pct = float(np.std(excess_returns)) * math.sqrt(periods_per_year) * 100
    information_ratio = (
        float(np.mean(excess_returns)) / float(np.std(excess_returns)) * math.sqrt(periods_per_year)
        if float(np.std(excess_returns)) > 0
        else None
    )

    chart_indices = downsample_indices(length)
    timestamps = format_labels(df, chart_indices, seconds)
    chart_step = max(1, math.ceil(length / max(1, len(chart_indices)))) if length else 1
    rolling_research = rolling_research_series(strategy_returns, chart_indices, periods_per_year)
    monthly_returns = monthly_return_report(seconds, account_equity)
    alpha_decay = alpha_decay_report(signal, close)

    return {
        "initial_capital": INITIAL_CAPITAL,
        "risk_percent": RISK_FRACTION * 100,
        "close": rounded_list(close[chart_indices], 4),
        "position": [int(value) for value in position[chart_indices]],
        "signal": [int(value) for value in signal[chart_indices]],
        "equity": rounded_list(account_equity[chart_indices], 2),
        "equity_pct": rounded_list((equity_multiplier[chart_indices] - 1) * 100, 4),
        "benchmark_equity": rounded_list(benchmark_equity[chart_indices], 2),
        "benchmark_pct": rounded_list((benchmark_multiplier[chart_indices] - 1) * 100, 4),
        "strategy_returns_pct": rounded_list(strategy_returns[chart_indices] * 100, 5),
        "benchmark_returns_pct": rounded_list(returns[chart_indices] * 100, 5),
        "drawdown_pct_series": rounded_list(drawdown_pct[chart_indices] * 100, 4),
        "benchmark_drawdown_pct_series": rounded_list(benchmark_drawdown_pct[chart_indices] * 100, 4),
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
        "recovery_factor": rounded(total_return_pct / max_drawdown_pct if max_drawdown_pct > 0 else None),
        "calmar_ratio": rounded(annual_return_pct / max_drawdown_pct if max_drawdown_pct > 0 else None),
        "annual_volatility_pct": rounded(annual_volatility),
        "ulcer_index": rounded(ulcer_index),
        "longest_drawdown_bars": int(longest_drawdown_bars),
        "buy_hold_return_pct": rounded(buy_hold_return),
        "benchmark_annual_return_pct": rounded(benchmark_annual_return_pct),
        "benchmark_max_drawdown_pct": rounded(benchmark_max_drawdown_pct),
        "excess_return_pct": rounded(total_return_pct - buy_hold_return),
        "alpha_annual_pct": rounded(alpha_annual_pct),
        "beta_to_benchmark": rounded(beta_to_benchmark),
        "correlation_to_benchmark": rounded(correlation_to_benchmark),
        "tracking_error_pct": rounded(tracking_error_pct),
        "information_ratio": rounded(information_ratio),
        "value_at_risk_95_pct": rounded(-var_95_raw * 100 if var_95_raw is not None else None),
        "value_at_risk_99_pct": rounded(-var_99_raw * 100 if var_99_raw is not None else None),
        "expected_shortfall_95_pct": rounded(expected_shortfall_95),
        "expected_shortfall_99_pct": rounded(expected_shortfall_99),
        "skewness": rounded(skewness),
        "kurtosis": rounded(kurtosis),
        "tail_ratio": rounded(tail_ratio),
        "omega_ratio": rounded(omega_ratio),
        "exposure_pct": rounded(exposure),
        "trades_per_year": rounded(trades_per_year),
        "avg_win_pct": rounded(avg_win_pct),
        "avg_loss_pct": rounded(avg_loss_pct),
        "payoff_ratio": rounded(payoff_ratio),
        "max_consecutive_wins": int(consecutive_wins),
        "max_consecutive_losses": int(consecutive_losses),
        "alpha_decay_half_life_bars": alpha_decay["half_life_bars"],
        "alpha_decay": alpha_decay,
        "return_distribution": return_distribution(strategy_returns),
        "monthly_returns": monthly_returns,
        "annual_returns": annual_return_report(monthly_returns),
        "validation_folds": validation_fold_report(strategy_returns, periods_per_year),
        "regime_breakdown": regime_report(close, returns, strategy_returns, position, periods_per_year),
        "trade_pnl_series": trade_pnl_report(trade_data),
        "num_bars": length,
        "periods_per_year": rounded(periods_per_year, 1),
        "years": rounded(years, 2),
        "trades": build_trade_rows(df, close, seconds, trade_data),
        **rolling_research,
        **trade_summary,
    }
