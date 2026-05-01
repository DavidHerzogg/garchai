import pandas as pd
import numpy as np


def run_backtest(df: pd.DataFrame) -> dict:
    df = df.copy()
    returns = df["close"].pct_change()
    strategy_returns = df["signal"].shift(1) * returns
    strategy_returns = strategy_returns.fillna(0)
    equity = (1 + strategy_returns).cumprod()

    timestamps = (
        df["timestamp"].astype(str).tolist()
        if "timestamp" in df.columns
        else list(range(len(equity)))
    )

    return {
        "equity": equity.tolist(),
        "timestamps": timestamps,
        "total_return": round(float(equity.iloc[-1] - 1) * 100, 2),
        "num_bars": len(df),
    }
