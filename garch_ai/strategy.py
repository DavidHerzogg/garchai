import pandas as pd
import numpy as np


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    fast = df["close"].rolling(window=20, min_periods=20).mean()
    slow = df["close"].rolling(window=50, min_periods=50).mean()

    signal = np.where(fast > slow, 1, np.where(fast < slow, -1, 0))

    df["signal"] = signal
    df["signal"] = df["signal"].fillna(0).astype(int)

    return df
