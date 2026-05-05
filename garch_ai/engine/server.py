import ast
import os
import io
import logging
import math
import re
import textwrap
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
import boto3
import numpy as np
import pandas as pd
import httpx
from botocore.config import Config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

ENGINE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ENGINE_DIR.parent
# Load the project env first, then engine/.env with override so a stale shell
# variable cannot silently win over the local backend configuration.
load_dotenv(PROJECT_DIR / ".env", override=False)
load_dotenv(ENGINE_DIR / ".env", override=True)

logger = logging.getLogger("garch_ai.engine")


def clean_secret(value: str) -> str:
    cleaned = value.strip().strip("\"'")
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    return cleaned


def require_openrouter_key() -> str:
    key = clean_secret(os.getenv("OPENROUTER_API_KEY", ""))
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not configured. Add it to engine/.env."
        )
    if key in {"YOUR_API_KEY", "OPENROUTER_API_KEY"} or "YOUR_API_KEY" in key:
        raise RuntimeError(
            "OPENROUTER_API_KEY still contains a placeholder. Replace it in engine/.env."
        )
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "GARCH AI Engine started successfully. Test it with GET /ping or GET /health."
    )
    yield


app = FastAPI(title="GARCH AI Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ───────────────────────────────────────────────────────────────────
R2_BUCKET       = "quant-data-prod"
R2_KEY          = "asset=XAUUSD/interval=1h/XAUUSD_H1_2015.parquet"
R2_ACCOUNT_ID   = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY   = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_KEY   = os.getenv("R2_SECRET_ACCESS_KEY", "")
OPENROUTER_KEY  = clean_secret(os.getenv("OPENROUTER_API_KEY", ""))
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free").lstrip("/")
OPENROUTER_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:8000")
OPENROUTER_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "90"))
STRATEGY_TIMEOUT_SECONDS = float(os.getenv("STRATEGY_TIMEOUT_SECONDS", "180"))
MAX_CODE_ATTEMPTS = int(os.getenv("MAX_CODE_ATTEMPTS", "4"))
MAX_OPTIMIZATION_RUNS = int(os.getenv("MAX_OPTIMIZATION_RUNS", "80"))
R2_CONNECT_TIMEOUT_SECONDS = int(os.getenv("R2_CONNECT_TIMEOUT_SECONDS", "10"))
R2_READ_TIMEOUT_SECONDS = int(os.getenv("R2_READ_TIMEOUT_SECONDS", "30"))
MARKET_DATA_CACHE_SECONDS = float(os.getenv("MARKET_DATA_CACHE_SECONDS", "3600"))
MARKET_DATA_CACHE: dict[str, object] = {"loaded_at": 0.0, "df": None}
SYSTEM_PROMPT = """
You are a high-end quantitative trading engineer.
Your task is to generate or refine a robust Python trading strategy based on the user's request and optional market context.

### Quantitative Context & Capabilities:
- **Available Data**: timestamp, open, high, low, close, volume.
- **Helper Columns**: returns, log_return, bar_range, body, hl2, ohlc4.
- **Advanced Concepts**: You should understand and be able to implement:
    - **Volatility-Adjusted Sizing**: Use ATR or rolling std for position scaling or stop distance.
    - **Market Regimes**: Adapt logic based on volatility (high/low), trend strength (ADX style), or momentum.
    - **Risk Management**: Implement Trailing Stops, Time-based Exits, or Break-even logic if requested.
    - **Statistical Arb**: Lead/lag features, rolling z-scores, mean reversion from dynamic bands.

### Implementation Rules:
- **Signature**: `def generate_signals(df: pd.DataFrame) -> pd.DataFrame:`
- **Parameters**: You MUST define a top-level `PARAMS` dictionary for EVERY tunable constant or research assumption used by the strategy: periods, thresholds, quantiles, z-score levels, ATR multipliers, volatility windows, regime filters, holding limits, stop/take-profit multipliers, sizing multipliers, cooldown bars, confirmation bars, and boolean switches.
    - Example: `PARAMS = {"rsi_period": 14, "entry_z": 1.5, "atr_mult": 2.0, "use_vol_filter": True}`
    - Never hide a numeric or boolean tuning value directly inside indicator logic. Put it in `PARAMS` and use `PARAMS["name"]`.
    - Prefer descriptive snake_case names because the web UI will automatically create editable input fields from `PARAMS`.
    - Add enough parameters to make the idea researchable, but do not overfit with meaningless knobs.
- **Vectorization**: Use ONLY pd and np vectorized logic. No loops, no `apply`, no `iterrows`.
- **Lookahead**: NEVER use future data. Use `.shift(1)` for indicators that depend on the current bar's close if the entry is at the same bar, or ensure logic is causal.
- **Output**: Add a "signal" column (-1, 0, 1). Fill NaNs with 0. Cast to int.
- **No Imports**: Use `pd` and `np` directly; they are pre-injected.

### Refinement Mode:
If history is provided, maintain the core logic of the previous strategy unless explicitly asked to change it. Focus on the requested improvements (e.g., "Add a stop loss", "Only trade in high volatility").
"""

SUMMARY_PROMPT = """
You summarize generated trading strategy code for a backtest report.
Write in German, concise and concrete.
Explain:
- entry conditions and why the strategy enters
- exit conditions and when it goes flat or flips
- whether stop loss or take profit exists in the generated code
- what indicators or market logic are used
Do not give financial advice. Do not use markdown tables.
"""

REPAIR_PROMPT = """
You repair generated trading strategy Python code.
Return ONLY valid Python code, no markdown, no explanation.
The code must define:
    PARAMS = {...}
    def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
Guaranteed columns: timestamp, open, high, low, close, volume, returns, log_return,
bar_range, body, hl2, ohlc4.
Rules:
- Preserve the user's requested strategy logic. Do not replace it with a generic fallback.
- Put every tunable numeric or boolean value in PARAMS and reference it from PARAMS in the strategy.
- Do not sort by timestamp; data is already chronological.
- Do not use columns that are not guaranteed.
- No imports, no file/network access, no while loops, no row loops.
- No pandas apply/map/iterrows/itertuples or custom Python callbacks.
- Use pd and np only.
- Add signal with -1, 0, 1, fill NaNs with 0, cast to int, return df.
"""

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_parquet_from_r2() -> pd.DataFrame:
    missing = [
        name
        for name, value in {
            "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
            "R2_ACCESS_KEY_ID": R2_ACCESS_KEY,
            "R2_SECRET_ACCESS_KEY": R2_SECRET_KEY,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing R2 environment variables: {', '.join(missing)}")

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(
            connect_timeout=R2_CONNECT_TIMEOUT_SECONDS,
            read_timeout=R2_READ_TIMEOUT_SECONDS,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )
    obj = s3.get_object(Bucket=R2_BUCKET, Key=R2_KEY)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


COLUMN_ALIASES = {
    "timestamp": [
        "timestamp",
        "time",
        "date",
        "datetime",
        "open_time",
        "close_time",
        "bar_time",
        "ts",
    ],
    "open": ["open", "o", "bid_open", "ask_open", "mid_open"],
    "high": ["high", "h", "bid_high", "ask_high", "mid_high"],
    "low": ["low", "l", "bid_low", "ask_low", "mid_low"],
    "close": [
        "close",
        "c",
        "price",
        "last",
        "mid",
        "bid",
        "ask",
        "bid_close",
        "ask_close",
        "mid_close",
    ],
    "volume": ["volume", "vol", "tick_volume", "real_volume", "qty"],
}


def normalized_column_name(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    normalized = {normalized_column_name(column): column for column in df.columns}
    for alias in aliases:
        key = normalized_column_name(alias)
        if key in normalized:
            return normalized[key]

    for key, column in normalized.items():
        if any(key.endswith(f"_{normalized_column_name(alias)}") for alias in aliases):
            return column
    return None


def safe_datetime_series(values: pd.Series, length: int) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    if parsed.notna().mean() < 0.5:
        numeric = pd.to_numeric(values, errors="coerce")
        if numeric.notna().mean() >= 0.5:
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
                parsed = pd.to_datetime(numeric, errors="coerce", utc=True, unit=unit)

    fallback = pd.date_range("2000-01-01", periods=length, freq="h", tz="UTC")
    parsed = pd.Series(parsed, index=range(length))
    parsed = parsed.where(parsed.notna(), pd.Series(fallback, index=range(length)))
    return parsed


def normalize_market_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        raise ValueError("Market data is empty")

    df = raw_df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join(str(part) for part in column if str(part)) for column in df.columns]
    else:
        df.columns = [str(column) for column in df.columns]

    df = df.reset_index(drop=False)
    length = len(df)

    close_col = find_column(df, COLUMN_ALIASES["close"])
    if close_col is None:
        raise ValueError(
            f"Market data has no usable close/price column. Columns: {list(raw_df.columns)[:20]}"
        )

    normalized = pd.DataFrame(index=range(length))
    for field in ["open", "high", "low", "close"]:
        source = find_column(df, COLUMN_ALIASES[field]) or close_col
        series = pd.to_numeric(df[source], errors="coerce").replace([np.inf, -np.inf], np.nan)
        normalized[field] = series.ffill().bfill()

    if normalized["close"].isna().all():
        raise ValueError("Market data has no valid close prices")

    volume_col = find_column(df, COLUMN_ALIASES["volume"])
    if volume_col is not None:
        normalized["volume"] = (
            pd.to_numeric(df[volume_col], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0)
        )
    else:
        normalized["volume"] = 0.0

    timestamp_col = find_column(df, COLUMN_ALIASES["timestamp"])
    if timestamp_col is not None:
        parsed_timestamp = safe_datetime_series(df[timestamp_col], length)
    else:
        parsed_timestamp = pd.Series(
            pd.date_range("2000-01-01", periods=length, freq="h", tz="UTC"),
            index=range(length),
        )
    normalized["timestamp"] = parsed_timestamp.dt.strftime("%Y-%m-%d %H:%M:%S")
    try:
        normalized["_timestamp_ns"] = parsed_timestamp.astype("int64")
    except Exception:
        normalized["_timestamp_ns"] = pd.to_datetime(
            normalized["timestamp"], errors="coerce", utc=True
        ).astype("int64")

    # Helper columns improve robustness for relation, momentum, ORB, mean reversion,
    # and single-asset stat-arb style prompts without requiring extra datasets.
    normalized["returns"] = normalized["close"].pct_change().fillna(0)
    normalized["log_return"] = np.log(normalized["close"] / normalized["close"].shift(1)).replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0)
    normalized["bar_range"] = (normalized["high"] - normalized["low"]).fillna(0)
    normalized["body"] = (normalized["close"] - normalized["open"]).fillna(0)
    normalized["hl2"] = ((normalized["high"] + normalized["low"]) / 2).fillna(normalized["close"])
    normalized["ohlc4"] = (
        (normalized["open"] + normalized["high"] + normalized["low"] + normalized["close"]) / 4
    ).fillna(normalized["close"])

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "returns",
        "log_return",
        "bar_range",
        "body",
        "hl2",
        "ohlc4",
    ]:
        normalized[column] = pd.to_numeric(
            normalized[column], errors="coerce", downcast="float"
        )

    normalized = normalized.ffill().bfill().reset_index(drop=True)
    return normalized


REQUIRED_MARKET_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


def ensure_market_data(df: pd.DataFrame) -> pd.DataFrame:
    if REQUIRED_MARKET_COLUMNS.issubset(set(df.columns)):
        return df.copy().reset_index(drop=True)
    return normalize_market_data(df)


def get_market_data(refresh: bool = False, copy: bool = False) -> tuple[pd.DataFrame, bool, float]:
    started = time.perf_counter()
    now = time.time()
    cached_df = MARKET_DATA_CACHE.get("df")
    loaded_at = float(MARKET_DATA_CACHE.get("loaded_at") or 0)

    if (
        not refresh
        and isinstance(cached_df, pd.DataFrame)
        and now - loaded_at < MARKET_DATA_CACHE_SECONDS
    ):
        output = cached_df.copy(deep=False) if copy else cached_df
        return output, True, time.perf_counter() - started

    df = normalize_market_data(load_parquet_from_r2())
    MARKET_DATA_CACHE["df"] = df
    MARKET_DATA_CACHE["loaded_at"] = now
    output = df.copy(deep=False) if copy else df
    return output, False, time.perf_counter() - started


async def call_openrouter_completion(messages: list[dict], temperature: float = 0) -> str:
    api_key = require_openrouter_key()

    timeout = httpx.Timeout(
        OPENROUTER_TIMEOUT_SECONDS,
        connect=min(10.0, OPENROUTER_TIMEOUT_SECONDS),
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": OPENROUTER_REFERER,
                    "X-Title": "GARCH AI",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": messages,
                    "temperature": temperature,
                },
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"OpenRouter did not respond within {OPENROUTER_TIMEOUT_SECONDS:.0f} seconds."
            ) from exc

        try:
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"OpenRouter did not respond within {OPENROUTER_TIMEOUT_SECONDS:.0f} seconds."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            if exc.response.status_code == 401:
                raise RuntimeError(
                    "OpenRouter rejected OPENROUTER_API_KEY with 401 Unauthorized. "
                    "The Authorization header is formatted correctly as "
                    "'Bearer <OPENROUTER_API_KEY>', so check that engine/.env "
                    "contains an active OpenRouter key from https://openrouter.ai/keys."
                ) from exc
            raise RuntimeError(
                f"OpenRouter request failed ({exc.response.status_code}): {detail}"
            ) from exc

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned an empty response")
        return content.strip()


async def call_openrouter(user_prompt: str, history: list[dict] | None = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    return await call_openrouter_completion(messages, temperature=0)


def heuristic_strategy_summary(prompt: str, code: str) -> str:
    has_stop = bool(re.search(r"\b(stop|stop_loss|sl)\b", code, re.IGNORECASE))
    has_take_profit = bool(re.search(r"\b(take_profit|tp|target)\b", code, re.IGNORECASE))

    risk_text = []
    risk_text.append("ein Stop Loss" if has_stop else "kein expliziter Stop Loss")
    risk_text.append("ein Take Profit" if has_take_profit else "kein expliziter Take Profit")

    return (
        f"Die Strategie wurde aus deiner Idee abgeleitet: {prompt.strip()} "
        "Der generierte Code erzeugt pro Kerze ein Signal: 1 fuer Long, -1 fuer Short "
        "und 0 fuer Flat. Ein Entry entsteht, wenn das Signal von Flat auf Long/Short "
        "wechselt oder direkt in die Gegenrichtung flippt. Der Exit entsteht, wenn das "
        "Signal auf 0 zurueckgeht oder in die Gegenrichtung wechselt. Im aktuellen Code "
        f"gibt es {risk_text[0]} und {risk_text[1]}; das Risikomanagement laeuft daher "
        "hauptsaechlich ueber Signalwechsel."
    )


async def summarize_strategy(prompt: str, code: str) -> str:
    try:
        return await call_openrouter_completion(
            [
                {"role": "system", "content": SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User idea:\n{prompt}\n\n"
                        f"Generated Python strategy code:\n{code}\n"
                    ),
                },
            ],
            temperature=0.1,
        )
    except Exception as exc:
        logger.warning("Strategy summary generation failed: %s", exc)
        return heuristic_strategy_summary(prompt, code)


async def repair_strategy_code(prompt: str, code: str, error: str) -> str:
    return await call_openrouter_completion(
        [
            {"role": "system", "content": REPAIR_PROMPT},
            {
                "role": "user",
                "content": (
                    f"User strategy idea:\n{prompt}\n\n"
                    f"Broken code:\n{code}\n\n"
                    f"Runtime error:\n{error[:2000]}\n\n"
                    "Return a corrected generate_signals implementation."
                ),
            },
        ],
        temperature=0,
    )


def disabled_legacy_strategy_template(prompt: str) -> str:
    raise RuntimeError("Legacy strategy templates are disabled; repair AI code instead.")
    prompt_lower = prompt.lower()

    if any(word in prompt_lower for word in ["orb", "opening range", "breakout", "ausbruch"]):
        return """
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lookback = 24
    upper = df["high"].rolling(lookback, min_periods=lookback).max().shift(1)
    lower = df["low"].rolling(lookback, min_periods=lookback).min().shift(1)
    df["signal"] = np.where(df["close"] > upper, 1, np.where(df["close"] < lower, -1, 0))
    df["signal"] = pd.Series(df["signal"], index=df.index).ffill().fillna(0).astype(int)
    return df
"""

    if any(word in prompt_lower for word in ["mean", "reversion", "rsi", "überverkauft", "ueberverkauft", "zscore"]):
        return """
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    df["signal"] = np.where(rsi < 30, 1, np.where(rsi > 70, -1, 0))
    df["signal"] = pd.Series(df["signal"], index=df.index).ffill().fillna(0).astype(int)
    return df
"""

    if any(word in prompt_lower for word in ["stat", "arb", "spread", "pair", "lat", "lead", "lag"]):
        return """
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    basis = df["close"] - df["hl2"]
    mean = basis.rolling(48, min_periods=48).mean()
    std = basis.rolling(48, min_periods=48).std().replace(0, np.nan)
    z = (basis - mean) / std
    df["signal"] = np.where(z < -1.5, 1, np.where(z > 1.5, -1, 0))
    df["signal"] = pd.Series(df["signal"], index=df.index).ffill().fillna(0).astype(int)
    return df
"""

    if any(word in prompt_lower for word in ["vol", "range", "atr"]):
        return """
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    atr = df["bar_range"].rolling(14, min_periods=14).mean()
    upper = df["close"].shift(1) + atr.shift(1)
    lower = df["close"].shift(1) - atr.shift(1)
    df["signal"] = np.where(df["close"] > upper, 1, np.where(df["close"] < lower, -1, 0))
    df["signal"] = pd.Series(df["signal"], index=df.index).ffill().fillna(0).astype(int)
    return df
"""

    return """
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    fast = df["close"].ewm(span=20, adjust=False).mean()
    slow = df["close"].ewm(span=50, adjust=False).mean()
    momentum = df["close"].pct_change(12)
    df["signal"] = np.where((fast > slow) & (momentum > 0), 1, np.where((fast < slow) & (momentum < 0), -1, 0))
    df["signal"] = pd.Series(df["signal"], index=df.index).ffill().fillna(0).astype(int)
    return df
"""


def normalize_generated_code(code: str) -> str:
    code = code.strip()
    fenced = re.search(r"```(?:python|py)?\s*(.*?)```", code, re.IGNORECASE | re.DOTALL)
    if fenced:
        code = fenced.group(1).strip()

    code = textwrap.dedent(code)
    code = code.replace("\u00a0", " ")

    # Common LLM typo: "import pandasas pd" / "import numpyas np".
    replacements = {
        "import pandasas pd": "import pandas as pd",
        "import pandas aspd": "import pandas as pd",
        "import numpyas np": "import numpy as np",
        "import numpy asnp": "import numpy as np",
    }
    for old, new in replacements.items():
        code = re.sub(rf"(?m)^\s*{re.escape(old)}\s*$", new, code)

    return code


def extract_generate_signals_function(code: str) -> str | None:
    lines = code.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.lstrip().startswith("def generate_signals")),
        None,
    )
    if start is None:
        return None

    selected = []
    for line in lines[start:]:
        stripped = line.lstrip()
        is_top_level = line == stripped
        if selected and is_top_level and stripped and not stripped.startswith(("#", "@")):
            break
        selected.append(line)
    return "\n".join(selected).strip()


DISALLOWED_AST_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Lambda,
    ast.ClassDef,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
    ast.GeneratorExp,
)
DISALLOWED_CALLS = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "open",
    "input",
}
DISALLOWED_ATTRS = {
    "apply",
    "applymap",
    "iterrows",
    "itertuples",
    "map",
    "pipe",
    "read_csv",
    "read_excel",
    "read_parquet",
    "sort_index",
    "sort_values",
    "to_csv",
    "to_excel",
    "to_pickle",
    "to_parquet",
}


def validate_generated_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, DISALLOWED_AST_NODES):
            raise ValueError(f"Generated code uses forbidden syntax: {type(node).__name__}")

        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Generated code uses forbidden private names")

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DISALLOWED_CALLS:
                raise ValueError(f"Generated code calls forbidden function: {func.id}")
            if isinstance(func, ast.Attribute) and func.attr in DISALLOWED_ATTRS:
                raise ValueError(f"Generated code calls forbidden method: {func.attr}")


def extract_params(code: str) -> dict:
    try:
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "PARAMS":
                        if isinstance(node.value, ast.Dict):
                            return {
                                ast.literal_eval(k): ast.literal_eval(v)
                                for k, v in zip(node.value.keys, node.value.values)
                                if k is not None
                            }
    except Exception:
        pass
    return {}


def normalize_param_value(value):
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(float(value)):
            return int(value) if isinstance(value, int) else float(value)
        return None
    if isinstance(value, str):
        return value
    return value


def infer_numeric_bounds(value: float | int, name: str) -> tuple[float, float, float]:
    lower_name = name.lower()
    is_integer = isinstance(value, int) and not isinstance(value, bool)
    numeric = float(value)

    if is_integer:
        if any(token in lower_name for token in ["period", "window", "lookback", "bars", "len", "length"]):
            lower = max(2, int(round(numeric * 0.5)))
            upper = max(lower + 1, int(round(numeric * 2.5)))
        elif any(token in lower_name for token in ["hour", "session", "cooldown", "hold"]):
            lower = max(0, int(round(numeric * 0.5)))
            upper = max(lower + 1, int(round(numeric * 2 + 4)))
        else:
            lower = max(0, int(round(numeric - max(2, abs(numeric) * 0.5))))
            upper = max(lower + 1, int(round(numeric + max(2, abs(numeric) * 0.5))))
        return float(lower), float(upper), 1.0

    if any(token in lower_name for token in ["quantile", "percentile"]):
        return 0.01, 0.99, 0.01
    if any(token in lower_name for token in ["ratio", "fraction", "weight", "prob", "rate"]):
        if 0 <= numeric <= 1:
            return 0.0, 1.0, 0.01
    if any(token in lower_name for token in ["z", "threshold", "entry", "exit"]):
        spread = max(0.25, abs(numeric) * 1.25)
        return numeric - spread, numeric + spread, 0.05
    if any(token in lower_name for token in ["mult", "factor", "atr", "std", "vol"]):
        lower = max(0.01, numeric * 0.4)
        upper = max(lower + 0.01, numeric * 2.5)
        return lower, upper, 0.05

    spread = max(0.1, abs(numeric) * 0.75)
    return numeric - spread, numeric + spread, 0.01


def build_param_schema(params: dict) -> list[dict]:
    schema: list[dict] = []
    for name, raw_value in params.items():
        value = normalize_param_value(raw_value)
        if isinstance(value, bool):
            schema.append(
                {
                    "name": str(name),
                    "type": "boolean",
                    "value": value,
                    "optimizer_enabled": False,
                }
            )
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            min_value, max_value, step = infer_numeric_bounds(value, str(name))
            schema.append(
                {
                    "name": str(name),
                    "type": "integer",
                    "value": value,
                    "min": int(round(min_value)),
                    "max": int(round(max_value)),
                    "step": int(step),
                    "optimizer_min": int(round(min_value)),
                    "optimizer_max": int(round(max_value)),
                    "optimizer_steps": 5,
                    "optimizer_enabled": True,
                }
            )
            continue
        if isinstance(value, float):
            min_value, max_value, step = infer_numeric_bounds(value, str(name))
            schema.append(
                {
                    "name": str(name),
                    "type": "number",
                    "value": round(value, 8),
                    "min": round(min_value, 8),
                    "max": round(max_value, 8),
                    "step": step,
                    "optimizer_min": round(min_value, 8),
                    "optimizer_max": round(max_value, 8),
                    "optimizer_steps": 5,
                    "optimizer_enabled": True,
                }
            )
            continue
        schema.append(
            {
                "name": str(name),
                "type": "text",
                "value": "" if value is None else str(value),
                "optimizer_enabled": False,
            }
        )
    return schema


def require_strategy_params(code: str) -> dict:
    params = extract_params(code)
    if not isinstance(params, dict) or not params:
        raise ValueError(
            "Generated strategy must define a non-empty top-level PARAMS dict so the UI can expose all tunable variables."
        )
    return {str(key): normalize_param_value(value) for key, value in params.items()}


def coerce_param_overrides(base_params: dict, overrides: dict | None) -> dict | None:
    if not overrides:
        return None

    coerced: dict = {}
    for key, raw_value in overrides.items():
        name = str(key)
        if name not in base_params:
            continue
        base_value = base_params[name]
        try:
            if isinstance(base_value, bool):
                if isinstance(raw_value, str):
                    coerced[name] = raw_value.strip().lower() in {"1", "true", "yes", "on"}
                else:
                    coerced[name] = bool(raw_value)
            elif isinstance(base_value, int) and not isinstance(base_value, bool):
                coerced[name] = int(round(float(raw_value)))
            elif isinstance(base_value, float):
                coerced[name] = float(raw_value)
            else:
                coerced[name] = raw_value
        except (TypeError, ValueError):
            continue
    return coerced


def linspace_values(min_value: float, max_value: float, steps: int, as_integer: bool) -> list:
    steps = int(max(1, min(steps, 21)))
    if steps == 1:
        values = [min_value]
    else:
        values = np.linspace(min_value, max_value, steps).tolist()
    if as_integer:
        return sorted({int(round(value)) for value in values})
    return [round(float(value), 8) for value in values]


def default_param_ranges(params: dict, schema: list[dict] | None = None) -> dict:
    schema_by_name = {item["name"]: item for item in (schema or build_param_schema(params))}
    ranges: dict = {}
    for name, value in params.items():
        item = schema_by_name.get(str(name))
        if not item or not item.get("optimizer_enabled"):
            continue
        ranges[str(name)] = linspace_values(
            float(item["optimizer_min"]),
            float(item["optimizer_max"]),
            int(item.get("optimizer_steps") or 5),
            item["type"] == "integer",
        )
    return ranges


def sanitize_param_ranges(params: dict, requested_ranges: dict | None, max_runs: int) -> tuple[dict, int]:
    schema = build_param_schema(params)
    ranges: dict = {}
    requested_ranges = requested_ranges or {}

    for name, values in requested_ranges.items():
        if str(name) not in params:
            continue
        base_value = params[str(name)]
        if isinstance(base_value, bool):
            continue
        if not isinstance(base_value, (int, float)):
            continue
        if not isinstance(values, list):
            continue
        cleaned = []
        for value in values[:31]:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(numeric):
                continue
            cleaned.append(int(round(numeric)) if isinstance(base_value, int) else round(numeric, 8))
        cleaned = sorted(set(cleaned))
        if cleaned:
            ranges[str(name)] = cleaned

    if not ranges:
        ranges = default_param_ranges(params, schema)

    capped_runs = max(1, min(int(max_runs or MAX_OPTIMIZATION_RUNS), MAX_OPTIMIZATION_RUNS))
    total = 1
    for values in ranges.values():
        total *= max(1, len(values))

    if total <= capped_runs:
        return ranges, total

    # Thin large grids deterministically so every parameter still participates.
    reduced = {name: list(values) for name, values in ranges.items()}
    while total > capped_runs and any(len(values) > 1 for values in reduced.values()):
        name = max(reduced, key=lambda key: len(reduced[key]))
        values = reduced[name]
        if len(values) <= 1:
            break
        keep_count = max(1, len(values) - 1)
        indices = np.unique(np.rint(np.linspace(0, len(values) - 1, keep_count)).astype(int))
        reduced[name] = [values[int(index)] for index in indices]
        total = 1
        for values in reduced.values():
            total *= max(1, len(values))

    return reduced, total


def compile_generated_code(raw_code: str) -> str:
    candidates = []
    normalized = normalize_generated_code(raw_code)
    candidates.append(normalized)

    extracted = extract_generate_signals_function(normalized)
    if extracted:
        candidates.append(extracted)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            tree = ast.parse(candidate)
            validate_generated_ast(tree)
            return candidate
        except (SyntaxError, ValueError) as exc:
            last_error = exc

    preview = normalized.splitlines()[0] if normalized.splitlines() else "<empty>"
    raise SyntaxError(
        f"AI returned invalid Python code near line 1: {preview!r}"
    ) from last_error


def execute_strategy_worker(code: str, df: pd.DataFrame, output_queue) -> None:
    try:
        code = compile_generated_code(code)
        namespace: dict = {"pd": pd, "np": np}
        exec(code, namespace)
        if "generate_signals" not in namespace:
            raise ValueError("generate_signals function not found in generated code")

        result = namespace["generate_signals"](df)
        if not isinstance(result, pd.DataFrame):
            raise ValueError("generate_signals must return a pandas DataFrame")
        if "signal" not in result.columns:
            raise ValueError("Strategy did not produce a 'signal' column")

        output_queue.put(("ok", result["signal"].tolist()))
    except Exception as exc:
        output_queue.put(("error", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))


def execute_strategy(code: str, df: pd.DataFrame, params_override: dict | None = None) -> pd.DataFrame:
    code = compile_generated_code(code)
    safe_builtins = {
        "abs": abs,
        "bool": bool,
        "float": float,
        "int": int,
        "len": len,
        "max": max,
        "min": min,
        "round": round,
    }
    namespace: dict = {"pd": pd, "np": np, "__builtins__": safe_builtins}
    exec(code, namespace)

    if params_override and "PARAMS" in namespace:
        if isinstance(namespace["PARAMS"], dict):
            namespace["PARAMS"].update(params_override)

    if "generate_signals" not in namespace:
        raise ValueError("generate_signals function not found in generated code")

    result = namespace["generate_signals"](df.copy())
    if not isinstance(result, pd.DataFrame):
        raise ValueError("generate_signals must return a pandas DataFrame")
    if "signal" not in result.columns:
        raise ValueError("Strategy did not produce a 'signal' column")

    signals = pd.to_numeric(result["signal"], errors="coerce")
    if len(signals) != len(df):
        raise ValueError("Generated signal length does not match market data length")
    signals = pd.Series(signals.to_numpy(), index=df.index).replace([np.inf, -np.inf], np.nan)
    signals = signals.fillna(0).clip(-1, 1).astype(int)

    output = df.copy(deep=False)
    output["signal"] = signals
    return output


def make_smoke_test_data(rows: int = 320) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    close = 100 + np.sin(index / 9) * 2 + index * 0.03
    open_ = close + np.sin(index / 5) * 0.15
    high = np.maximum(open_, close) + 0.35
    low = np.minimum(open_, close) - 0.35
    volume = 1000 + (np.cos(index / 11) * 100)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=rows, freq="h", tz="UTC").strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    df["_timestamp_ns"] = pd.date_range("2020-01-01", periods=rows, freq="h", tz="UTC").astype(
        "int64"
    )
    df["returns"] = df["close"].pct_change().fillna(0)
    df["log_return"] = np.log(df["close"] / df["close"].shift(1)).replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0)
    df["bar_range"] = (df["high"] - df["low"]).fillna(0)
    df["body"] = (df["close"] - df["open"]).fillna(0)
    df["hl2"] = ((df["high"] + df["low"]) / 2).fillna(df["close"])
    df["ohlc4"] = ((df["open"] + df["high"] + df["low"] + df["close"]) / 4).fillna(df["close"])
    return df


def smoke_test_strategy_code(code: str) -> str:
    compiled = compile_generated_code(code)
    require_strategy_params(compiled)
    smoke_df = make_smoke_test_data()
    started = time.perf_counter()
    result = execute_strategy(compiled, smoke_df)
    elapsed = time.perf_counter() - started
    if elapsed > 2.0:
        raise TimeoutError(
            f"Generated strategy is too slow on smoke data ({elapsed:.2f}s)."
        )

    signals = pd.to_numeric(result["signal"], errors="coerce").fillna(0)
    if len(signals) != len(smoke_df):
        raise ValueError("Generated signal length changed during smoke test")
    if not set(signals.astype(int).unique()).issubset({-1, 0, 1}):
        raise ValueError("Generated signal contains values outside -1, 0, 1")
    return compiled


async def prepare_strategy_code(prompt: str, code: str) -> tuple[str, list[str]]:
    errors: list[str] = []
    current_code = code

    for attempt in range(max(1, MAX_CODE_ATTEMPTS)):
        try:
            return smoke_test_strategy_code(current_code), errors
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            errors.append(error)
            logger.warning("Strategy validation attempt %s failed: %s", attempt + 1, error)

            if attempt + 1 >= MAX_CODE_ATTEMPTS:
                break

            current_code = await repair_strategy_code(prompt, current_code, "\n\n".join(errors))

    detail = "; ".join(errors[-3:])
    raise ValueError(
        "AI strategy code could not be made executable without changing the requested "
        f"strategy into a fallback. No fallback was used. Last errors: {detail}"
    )


def run_backtest(df: pd.DataFrame) -> dict:
    try:
        from backtest import run_backtest as _bt
    except ModuleNotFoundError:
        from engine.backtest import run_backtest as _bt
    return _bt(df)


def backtest_prepared_code(prompt: str, code: str, market_df: pd.DataFrame, params: dict | None = None) -> dict:
    compiled = smoke_test_strategy_code(code)
    started = time.perf_counter()
    result = backtest_code(compiled, market_df, params)
    strategy_seconds = time.perf_counter() - started
    summary = heuristic_strategy_summary(prompt, compiled)
    extracted_params = require_strategy_params(compiled)
    active_params = {**extracted_params, **(coerce_param_overrides(extracted_params, params) or {})}
    summaries = build_backtest_summaries(result)
    return {
        **result,
        "code": compiled,
        "params": extracted_params,
        "active_params": active_params,
        "param_schema": build_param_schema(extracted_params),
        "summary": summary,
        **summaries,
        "attempts": 1,
        "strategy_seconds": round(strategy_seconds, 3),
    }


def backtest_code(code: str, market_df: pd.DataFrame | None = None, params: dict | None = None) -> dict:
    df = ensure_market_data(market_df if market_df is not None else load_parquet_from_r2())
    base_params = require_strategy_params(code)
    df = execute_strategy(code, df, coerce_param_overrides(base_params, params))

    if "signal" not in df.columns:
        raise ValueError("Strategy did not produce a 'signal' column")

    return run_backtest(df)


async def generate_strategy(prompt: str, history: list[dict] | None = None) -> dict:
    started = time.perf_counter()
    raw_code = await call_openrouter(prompt, history)
    code, repair_errors = await prepare_strategy_code(prompt, raw_code)
    timings = {"api_seconds": round(time.perf_counter() - started, 3)}
    if repair_errors:
        timings["repair_attempts"] = len(repair_errors)
    return {
        "code": code,
        "model": OPENROUTER_MODEL,
        "timings": timings,
    }


async def run_prompt(prompt: str) -> dict:
    total_started = time.perf_counter()
    generated = await generate_strategy(prompt)
    api_seconds = generated["timings"]["api_seconds"]

    market_df, cache_hit, data_seconds = get_market_data()
    backtest_started = time.perf_counter()
    result = backtest_prepared_code(prompt, generated["code"], market_df)
    backtest_seconds = time.perf_counter() - backtest_started

    timings = {
        "api_seconds": round(api_seconds, 3),
        "data_seconds": round(data_seconds, 3),
        "backtest_seconds": round(backtest_seconds, 3),
        "total_seconds": round(time.perf_counter() - total_started, 3),
        "data_cache_hit": cache_hit,
    }
    if "repair_attempts" in generated["timings"]:
        timings["repair_attempts"] = generated["timings"]["repair_attempts"]
    return {**result, "timings": timings}


def selected_metric(result: dict, metric: str) -> float:
    candidates = [metric, "sharpe_ratio", "sortino_ratio", "calmar_ratio", "total_return_pct"]
    for key in candidates:
        value = result.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
    return -float("inf")


def compact_metrics(result: dict, metric: str) -> dict:
    return {
        "metric": metric,
        "metric_value": round(selected_metric(result, metric), 4),
        "total_return_pct": result.get("total_return_pct"),
        "annual_return_pct": result.get("annual_return_pct"),
        "sharpe_ratio": result.get("sharpe_ratio"),
        "sortino_ratio": result.get("sortino_ratio"),
        "calmar_ratio": result.get("calmar_ratio"),
        "max_drawdown_pct": result.get("max_drawdown_pct"),
        "win_rate": result.get("win_rate"),
        "profit_factor": result.get("profit_factor"),
        "expectancy": result.get("expectancy"),
        "trades_total": result.get("trades_total"),
        "alpha_decay_half_life_bars": result.get("alpha_decay_half_life_bars"),
    }


def format_pct(value, digits: int = 2) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return "-"
    prefix = "+" if float(value) > 0 else ""
    return f"{prefix}{float(value):.{digits}f}%"


def format_num(value, digits: int = 2) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return "-"
    return f"{float(value):.{digits}f}"


def best_and_worst_folds(folds: list[dict]) -> tuple[dict | None, dict | None]:
    valid = [
        fold
        for fold in folds
        if isinstance(fold.get("return_pct"), (int, float))
        and math.isfinite(float(fold["return_pct"]))
    ]
    if not valid:
        return None, None
    return max(valid, key=lambda fold: float(fold["return_pct"])), min(
        valid,
        key=lambda fold: float(fold["return_pct"]),
    )


def build_backtest_summaries(result: dict) -> dict:
    total_return = result.get("total_return_pct")
    sharpe = result.get("sharpe_ratio")
    max_drawdown = result.get("max_drawdown_pct")
    win_rate = result.get("win_rate")
    trades = result.get("trades_total")
    exposure = result.get("exposure_pct")
    half_life = result.get("alpha_decay_half_life_bars")
    buy_hold = result.get("buy_hold_return_pct")
    excess = result.get("excess_return_pct")
    folds = result.get("validation_folds") or []
    best_fold, worst_fold = best_and_worst_folds(folds)
    monthly_returns = result.get("monthly_returns") or []
    positive_months = [
        row
        for row in monthly_returns
        if isinstance(row.get("return_pct"), (int, float)) and row["return_pct"] > 0
    ]

    headline = (
        f"Backtest: {format_pct(total_return)} total, Sharpe {format_num(sharpe)}, "
        f"max DD {format_pct(max_drawdown)} bei {format_pct(exposure)} Exposure."
    )
    bullets = [
        (
            f"Benchmark-Vergleich: Buy-and-hold {format_pct(buy_hold)}, "
            f"Excess Return {format_pct(excess)}."
        ),
        (
            f"Trades: {trades if trades is not None else '-'} Trades, "
            f"Winrate {format_pct(win_rate)}, Profit Factor {format_num(result.get('profit_factor'))}."
        ),
        (
            f"Tail Risk: VaR 95 {format_pct(result.get('value_at_risk_95_pct'))}, "
            f"Expected Shortfall 95 {format_pct(result.get('expected_shortfall_95_pct'))}."
        ),
    ]
    if half_life is not None:
        bullets.append(f"Alpha Decay: geschaetzte Halbwertszeit {format_num(half_life)} Bars.")
    if best_fold and worst_fold:
        bullets.append(
            "Walk-forward Folds: bester Fold "
            f"{best_fold.get('fold')} mit {format_pct(best_fold.get('return_pct'))}, "
            f"schlechtester Fold {worst_fold.get('fold')} mit {format_pct(worst_fold.get('return_pct'))}."
        )

    chart_summary = {
        "equity": (
            f"Equity-Chart zeigt Strategy {format_pct(total_return)} vs Benchmark {format_pct(buy_hold)}; "
            f"der Abstand liegt bei {format_pct(excess)}."
        ),
        "drawdown": (
            f"Drawdown-Chart markiert max DD {format_pct(max_drawdown)} "
            f"und {result.get('longest_drawdown_bars', '-')} Bars laengste Drawdown-Phase."
        ),
        "rolling": (
            f"Rolling-Quality nutzt ein Fenster von {result.get('rolling_window', '-')} Bars "
            "fuer Sharpe, Volatilitaet und Winrate."
        ),
        "distribution": (
            f"Return-Distribution zeigt Skew {format_num(result.get('skewness'))}, "
            f"Kurtosis {format_num(result.get('kurtosis'))}, Tail Ratio {format_num(result.get('tail_ratio'))}."
        ),
        "alpha_decay": (
            "Alpha-Decay-Chart zeigt Forward Edge je Lag; "
            f"Halbwertszeit {format_num(half_life)} Bars."
        ),
        "monthly": (
            f"Monthly-Heatmap: {len(positive_months)}/{len(monthly_returns)} Monate positiv."
            if monthly_returns
            else "Monthly-Heatmap hat noch nicht genug Monatsdaten."
        ),
    }
    return {
        "analysis_summary": {
            "headline": headline,
            "bullets": bullets,
        },
        "chart_summary": chart_summary,
    }


def build_optimization_rows(
    compiled_code: str,
    prompt: str,
    market_df: pd.DataFrame,
    base_params: dict,
    ranges: dict,
    metric: str,
) -> tuple[list[dict], dict]:
    from itertools import product

    keys = list(ranges.keys())
    if not keys:
        values_grid = [()]
    else:
        values_grid = product(*(ranges[key] for key in keys))

    rows: list[dict] = []
    best_result: dict | None = None
    best_score = -float("inf")
    for values in values_grid:
        params = {**base_params, **dict(zip(keys, values))}
        try:
            result = backtest_code(compiled_code, market_df, params)
        except Exception as exc:
            logger.warning("Optimization point failed for %s: %s", params, exc)
            continue
        metric_value = selected_metric(result, metric)
        compact = compact_metrics(result, metric)
        rows.append(
            {
                "params": params,
                "metric_value": metric_value,
                "compact": compact,
                "folds": result.get("validation_folds", []),
            }
        )
        if metric_value > best_score:
            best_score = metric_value
            best_result = result
    rows.sort(key=lambda row: row["metric_value"], reverse=True)
    if best_result is None:
        best_result = {}
    return rows, best_result


def optimization_leaderboard(rows: list[dict], metric: str, limit: int = 20) -> list[dict]:
    return [
        {
            "rank": index + 1,
            "params": row["params"],
            **row["compact"],
        }
        for index, row in enumerate(rows[:limit])
    ]


def optimization_surface(rows: list[dict], ranges: dict, metric: str) -> dict:
    varied_keys = [key for key, values in ranges.items() if len(values) > 1]
    if not varied_keys:
        return {"x_param": None, "y_param": None, "points": []}

    x_param = varied_keys[0]
    y_param = varied_keys[1] if len(varied_keys) > 1 else None
    points = []
    for row in rows:
        params = row["params"]
        points.append(
            {
                "x": params.get(x_param),
                "y": params.get(y_param) if y_param else 0,
                "z": round(float(row["metric_value"]), 4),
                "params": params,
            }
        )
    return {"x_param": x_param, "y_param": y_param, "points": points}


def parameter_sensitivity(rows: list[dict], ranges: dict, metric: str) -> list[dict]:
    output: list[dict] = []
    for key, values in ranges.items():
        buckets = []
        for value in values:
            metric_values = [
                row["metric_value"]
                for row in rows
                if row["params"].get(key) == value
            ]
            finite = [value for value in metric_values if math.isfinite(float(value))]
            if not finite:
                continue
            buckets.append(
                {
                    "value": value,
                    "runs": len(finite),
                    "mean_metric": round(float(np.mean(finite)), 4),
                    "median_metric": round(float(np.median(finite)), 4),
                }
            )
        if not buckets:
            continue
        best_bucket = max(buckets, key=lambda item: item["mean_metric"])
        worst_bucket = min(buckets, key=lambda item: item["mean_metric"])
        output.append(
            {
                "param": key,
                "best_value": best_bucket["value"],
                "worst_value": worst_bucket["value"],
                "spread": round(best_bucket["mean_metric"] - worst_bucket["mean_metric"], 4),
                "buckets": buckets,
            }
        )
    return output


def stability_report(rows: list[dict], metric: str) -> dict:
    if not rows:
        return {}

    metric_values = np.array(
        [row["metric_value"] for row in rows],
        dtype=np.float64,
    )
    finite_metric = metric_values[np.isfinite(metric_values)]
    returns = np.array(
        [
            float(row["compact"].get("total_return_pct") or 0)
            for row in rows
        ],
        dtype=np.float64,
    )
    sharpes = np.array(
        [
            float(row["compact"].get("sharpe_ratio") or 0)
            for row in rows
        ],
        dtype=np.float64,
    )
    if len(finite_metric) == 0:
        return {}

    q25, q75 = np.nanpercentile(finite_metric, [25, 75])
    top_decile = np.nanpercentile(finite_metric, 90)
    return {
        "runs": int(len(rows)),
        "metric": metric,
        "median_metric": round(float(np.nanmedian(finite_metric)), 4),
        "mean_metric": round(float(np.nanmean(finite_metric)), 4),
        "iqr": round(float(q75 - q25), 4),
        "best_metric": round(float(np.nanmax(finite_metric)), 4),
        "worst_metric": round(float(np.nanmin(finite_metric)), 4),
        "top_decile_metric": round(float(top_decile), 4),
        "profitable_param_rate_pct": round(float(np.mean(returns > 0) * 100), 2),
        "positive_sharpe_rate_pct": round(float(np.mean(sharpes > 0) * 100), 2),
    }


def estimate_pbo(rows: list[dict], metric: str) -> dict:
    if len(rows) < 5:
        return {
            "available": False,
            "reason": "PBO needs at least five parameter candidates.",
        }

    fold_ids = sorted(
        {
            int(fold["fold"])
            for row in rows
            for fold in row.get("folds", [])
            if isinstance(fold.get("fold"), int)
        }
    )
    if len(fold_ids) < 4:
        return {
            "available": False,
            "reason": "PBO needs at least four validation folds.",
        }

    fold_index = {fold_id: index for index, fold_id in enumerate(fold_ids)}
    matrix = np.full((len(rows), len(fold_ids)), np.nan, dtype=np.float64)
    fold_metric_key = "sharpe_ratio" if "sharpe" in metric else "return_pct"
    for row_index, row in enumerate(rows):
        for fold in row.get("folds", []):
            fold_id = fold.get("fold")
            if fold_id not in fold_index:
                continue
            value = fold.get(fold_metric_key)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                matrix[row_index, fold_index[fold_id]] = float(value)

    if np.isfinite(matrix).sum() < len(rows) * 2:
        return {
            "available": False,
            "reason": "Not enough finite fold scores for PBO.",
        }

    from itertools import combinations

    fold_indices = list(range(len(fold_ids)))
    train_size = max(2, len(fold_indices) // 2)
    splits = list(combinations(fold_indices, train_size))
    if len(splits) > 126:
        selected = np.unique(np.rint(np.linspace(0, len(splits) - 1, 126)).astype(int))
        splits = [splits[int(index)] for index in selected]

    rank_percentiles: list[float] = []
    train_test_spreads: list[float] = []
    for train_tuple in splits:
        train = np.array(train_tuple, dtype=np.int64)
        test = np.array([index for index in fold_indices if index not in train_tuple], dtype=np.int64)
        if len(test) == 0:
            continue
        train_slice = matrix[:, train]
        test_slice = matrix[:, test]
        train_counts = np.isfinite(train_slice).sum(axis=1)
        test_counts = np.isfinite(test_slice).sum(axis=1)
        train_scores = np.full(len(rows), np.nan, dtype=np.float64)
        test_scores = np.full(len(rows), np.nan, dtype=np.float64)
        train_scores[train_counts > 0] = np.nansum(train_slice[train_counts > 0], axis=1) / train_counts[train_counts > 0]
        test_scores[test_counts > 0] = np.nansum(test_slice[test_counts > 0], axis=1) / test_counts[test_counts > 0]
        finite_train = np.isfinite(train_scores)
        finite_test = np.isfinite(test_scores)
        if finite_train.sum() < 2 or finite_test.sum() < 2:
            continue
        best_train_index = int(np.nanargmax(np.where(finite_train, train_scores, -np.inf)))
        selected_test_score = test_scores[best_train_index]
        if not math.isfinite(float(selected_test_score)):
            continue
        finite_test_scores = test_scores[finite_test]
        rank = float(np.mean(finite_test_scores <= selected_test_score) * 100)
        rank_percentiles.append(rank)
        train_test_spreads.append(float(train_scores[best_train_index] - selected_test_score))

    if not rank_percentiles:
        return {
            "available": False,
            "reason": "No valid train/test PBO split could be computed.",
        }

    rank_array = np.array(rank_percentiles, dtype=np.float64)
    pbo = float(np.mean(rank_array < 50) * 100)
    return {
        "available": True,
        "method": "Combinatorially symmetric cross-validation over chronological folds",
        "metric": fold_metric_key,
        "folds": int(len(fold_ids)),
        "splits": int(len(rank_percentiles)),
        "pbo_probability_pct": round(pbo, 2),
        "median_oos_rank_pct": round(float(np.median(rank_array)), 2),
        "rank_percentiles": [round(float(value), 2) for value in rank_percentiles],
        "median_train_test_degradation": round(float(np.median(train_test_spreads)), 4),
    }


def format_param_dict(params: dict, limit: int = 6) -> str:
    items = list(params.items())[:limit]
    suffix = ", ..." if len(params) > limit else ""
    return ", ".join(f"{key}={value}" for key, value in items) + suffix


def build_research_summary(
    rows: list[dict],
    ranges: dict,
    metric: str,
    best_params: dict,
    best_metrics: dict,
    stability: dict,
    pbo: dict,
    elapsed: float,
) -> dict:
    best_value = selected_metric(best_metrics, metric)
    pbo_text = (
        f"PBO {format_pct(pbo.get('pbo_probability_pct'))}, median OOS rank "
        f"{format_pct(pbo.get('median_oos_rank_pct'))}."
        if pbo.get("available")
        else f"PBO nicht verfuegbar: {pbo.get('reason', 'zu wenige valide Splits')}."
    )
    planned_runs = 1
    for values in ranges.values():
        planned_runs *= max(1, len(values))
    headline = (
        f"Optimization: {len(rows)} valide Runs, best {metric}={format_num(best_value, 4)} "
        f"mit {format_param_dict(best_params)}."
    )
    bullets = [
        (
            f"Grid: {len(ranges)} Parameter aktiv, geplant {planned_runs} Kombinationen, "
            f"Laufzeit {format_num(elapsed)}s."
        ),
        (
            f"Stabilitaet: Median {metric}={format_num(stability.get('median_metric'), 4)}, "
            f"IQR {format_num(stability.get('iqr'), 4)}, positive Sharpe Rate "
            f"{format_pct(stability.get('positive_sharpe_rate_pct'))}."
        ),
        pbo_text,
        (
            f"Best Backtest: Return {format_pct(best_metrics.get('total_return_pct'))}, "
            f"Sharpe {format_num(best_metrics.get('sharpe_ratio'))}, "
            f"Max DD {format_pct(best_metrics.get('max_drawdown_pct'))}."
        ),
    ]
    chart_summary = {
        "surface": (
            "Optimization Surface zeigt die Metric-Landschaft fuer die ersten zwei "
            "variierten Parameter; flache Plateaus sind robuster als isolierte Peaks."
        ),
        "pbo": (
            "PBO-Chart zeigt, wie oft der in-sample beste Kandidat out-of-sample im "
            "unteren Rangbereich landet."
        ),
        "leaderboard": (
            "Leaderboard zeigt kompakte Kennzahlen je Parametersatz; die beste Zeile "
            "liefert die Chartdaten im Performance-Tab."
        ),
        "sensitivity": (
            "Sensitivity zeigt, welche Parameterwerte die Zielmetric im Mittel treiben."
        ),
        "folds": (
            "Validation Folds zeigen chronologische Stabilitaet statt nur einen "
            "einzigen Gesamtbacktest."
        ),
    }
    return {
        "headline": headline,
        "bullets": bullets,
        "chart_summary": chart_summary,
    }


def run_parameter_research(
    prompt: str,
    code: str,
    market_df: pd.DataFrame,
    params: dict | None,
    param_ranges: dict | None,
    metric: str,
    max_runs: int,
) -> dict:
    compiled = smoke_test_strategy_code(code)
    base_params = require_strategy_params(compiled)
    active_params = {**base_params, **(coerce_param_overrides(base_params, params) or {})}
    ranges, planned_runs = sanitize_param_ranges(active_params, param_ranges, max_runs)
    started = time.perf_counter()
    rows, best_metrics = build_optimization_rows(
        compiled,
        prompt,
        market_df,
        active_params,
        ranges,
        metric,
    )
    elapsed = time.perf_counter() - started
    if not rows:
        raise ValueError("No optimization candidate produced a valid backtest.")

    best = rows[0]
    best_metrics = {
        **best_metrics,
        "code": compiled,
        "params": base_params,
        "active_params": best["params"],
        "param_schema": build_param_schema(base_params),
        "summary": heuristic_strategy_summary(prompt, compiled),
    }
    best_metrics.update(build_backtest_summaries(best_metrics))
    stability = stability_report(rows, metric)
    pbo = estimate_pbo(rows, metric)
    research_summary = build_research_summary(
        rows=rows,
        ranges=ranges,
        metric=metric,
        best_params=best["params"],
        best_metrics=best_metrics,
        stability=stability,
        pbo=pbo,
        elapsed=elapsed,
    )
    return {
        "code": compiled,
        "base_params": base_params,
        "active_params": active_params,
        "param_schema": build_param_schema(base_params),
        "ranges": ranges,
        "planned_runs": planned_runs,
        "completed_runs": len(rows),
        "metric": metric,
        "best": {
            "params": best["params"],
            "metric_value": round(float(best["metric_value"]), 4),
            "metrics": best_metrics,
        },
        "leaderboard": optimization_leaderboard(rows, metric),
        "surface": optimization_surface(rows, ranges, metric),
        "sensitivity": parameter_sensitivity(rows, ranges, metric),
        "stability": stability,
        "pbo": pbo,
        "research_summary": research_summary,
        "research_seconds": round(elapsed, 3),
    }


# ── Routes ───────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    history: list[dict] | None = None

class BacktestRequest(BaseModel):
    code: str
    prompt: str = ""
    params: dict | None = None

class OptimizeRequest(BaseModel):
    code: str
    prompt: str = ""
    params: dict | None = None
    param_ranges: dict = Field(default_factory=dict)
    metric: str = "sharpe_ratio"
    max_runs: int = MAX_OPTIMIZATION_RUNS

@app.post("/generate")
async def generate(req: GenerateRequest):
    try:
        res = await generate_strategy(req.prompt, req.history)
        res["params"] = require_strategy_params(res["code"])
        res["param_schema"] = build_param_schema(res["params"])
        return res
    except ValueError as e:
        logger.exception("Strategy generation/validation failed")
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}")
    except Exception as e:
        logger.exception("Strategy generation failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@app.post("/backtest")
async def backtest(req: BacktestRequest):
    try:
        total_started = time.perf_counter()
        market_df, cache_hit, data_seconds = get_market_data()
        backtest_started = time.perf_counter()
        result = backtest_prepared_code(req.prompt, req.code, market_df, req.params)
        result["timings"] = {
            "data_seconds": round(data_seconds, 3),
            "backtest_seconds": round(time.perf_counter() - backtest_started, 3),
            "strategy_seconds": result.get("strategy_seconds"),
            "total_seconds": round(time.perf_counter() - total_started, 3),
            "data_cache_hit": cache_hit,
        }
        return result

    except ValueError as e:
        logger.exception("Backtest rejected invalid strategy code")
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}")
    except Exception as e:
        logger.exception("Backtest failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

@app.post("/optimize")
async def optimize(req: OptimizeRequest):
    try:
        market_df, _, _ = get_market_data()
        return run_parameter_research(
            prompt=req.prompt,
            code=req.code,
            market_df=market_df,
            params=req.params,
            param_ranges=req.param_ranges,
            metric=req.metric,
            max_runs=req.max_runs,
        )

    except Exception as e:
        logger.exception("Optimization failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/research")
async def research(req: OptimizeRequest):
    return await optimize(req)

@app.post("/run")
async def run(req: GenerateRequest):
    try:
        return await run_prompt(req.prompt)
    except ValueError as e:
        logger.exception("Run rejected invalid strategy code")
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}")
    except Exception as e:
        logger.exception("Run failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

@app.get("/", response_class=HTMLResponse)
def index():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    return HTMLResponse(
        """
        <!doctype html>
        <html>
          <head><title>GARCH AI Engine</title></head>
          <body>
            <h1>GARCH AI Engine is running</h1>
            <p><a href="/ping">/ping</a></p>
            <p><a href="/health">/health</a></p>
            <p><a href="/docs">/docs</a></p>
          </body>
        </html>
        """
    )

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ping")
def ping():
    return "pong"
