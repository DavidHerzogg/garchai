import ast
import multiprocessing as mp
import os
import io
import logging
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
from pydantic import BaseModel
from dotenv import load_dotenv

ENGINE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ENGINE_DIR.parent
MAX_CODE_ATTEMPTS = 3
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
R2_CONNECT_TIMEOUT_SECONDS = int(os.getenv("R2_CONNECT_TIMEOUT_SECONDS", "10"))
R2_READ_TIMEOUT_SECONDS = int(os.getenv("R2_READ_TIMEOUT_SECONDS", "30"))
MARKET_DATA_CACHE_SECONDS = float(os.getenv("MARKET_DATA_CACHE_SECONDS", "3600"))
MARKET_DATA_CACHE: dict[str, object] = {"loaded_at": 0.0, "df": None}
SYSTEM_PROMPT = """
You are a robust quantitative trading code generator for price-action strategies.
Return ONLY valid Python code, no markdown, no explanation.
The function signature MUST be:
    def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
Available columns are guaranteed: timestamp, open, high, low, close, volume.
Extra helper columns may exist: returns, log_return, bar_range, body, hl2, ohlc4.
Supported strategy families: momentum, opening range breakout (ORB), trend following,
mean reversion, volatility breakout, price/indicator relation strategies, and
single-asset statistical-arbitrage/latency proxies based on spreads, returns,
range, volume, rolling z-scores, and lead/lag features.
Rules:
- Add column "signal" with values -1, 0, 1.
- df is already chronological; do not sort by timestamp.
- Do not assume unavailable columns or other assets exist.
- If you use timestamp, use it only for hour/session filters, never as a required sort key.
- Use only provided pd and np variables; do not write import statements.
- Use vectorized pandas/numpy logic, no row loops, no network/file access, no while loops.
- Use ONLY past/current data: rolling(...).mean(), shift(1), expanding, etc.; no lookahead.
- Always fill signal NaNs with 0 and cast to int before returning.
- Return the modified df.
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
    def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
Guaranteed columns: timestamp, open, high, low, close, volume, returns, log_return,
bar_range, body, hl2, ohlc4.
Rules:
- Do not sort by timestamp; data is already chronological.
- Do not use columns that are not guaranteed.
- No imports, no file/network access, no while loops, no row loops.
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

    normalized = normalized.ffill().bfill().reset_index(drop=True)
    return normalized


REQUIRED_MARKET_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


def ensure_market_data(df: pd.DataFrame) -> pd.DataFrame:
    if REQUIRED_MARKET_COLUMNS.issubset(set(df.columns)):
        return df.copy().reset_index(drop=True)
    return normalize_market_data(df)


def get_market_data(refresh: bool = False) -> tuple[pd.DataFrame, bool, float]:
    started = time.perf_counter()
    now = time.time()
    cached_df = MARKET_DATA_CACHE.get("df")
    loaded_at = float(MARKET_DATA_CACHE.get("loaded_at") or 0)

    if (
        not refresh
        and isinstance(cached_df, pd.DataFrame)
        and now - loaded_at < MARKET_DATA_CACHE_SECONDS
    ):
        return cached_df.copy(), True, time.perf_counter() - started

    df = normalize_market_data(load_parquet_from_r2())
    MARKET_DATA_CACHE["df"] = df
    MARKET_DATA_CACHE["loaded_at"] = now
    return df.copy(), False, time.perf_counter() - started


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


async def call_openrouter(user_prompt: str) -> str:
    return await call_openrouter_completion(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )


def fallback_strategy_summary(prompt: str, code: str) -> str:
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
        return fallback_strategy_summary(prompt, code)


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


def fallback_strategy_code(prompt: str) -> str:
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
    "read_csv",
    "read_excel",
    "read_parquet",
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
        namespace: dict = {}
        exec(code, {"pd": pd, "np": __import__("numpy")}, namespace)
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


def execute_strategy(code: str, df: pd.DataFrame) -> pd.DataFrame:
    code = compile_generated_code(code)
    namespace: dict = {}
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
    exec(code, {"pd": pd, "np": np, "__builtins__": safe_builtins}, namespace)
    if "generate_signals" not in namespace:
        raise ValueError("generate_signals function not found in generated code")

    result = namespace["generate_signals"](df.copy())
    if not isinstance(result, pd.DataFrame):
        raise ValueError("generate_signals must return a pandas DataFrame")
    if "signal" not in result.columns:
        raise ValueError("Strategy did not produce a 'signal' column")

    signals = pd.Series(result["signal"], index=df.index)
    if len(signals) != len(df):
        raise ValueError("Generated signal length does not match market data length")

    output = df.copy()
    output["signal"] = signals
    return output


def run_backtest(df: pd.DataFrame) -> dict:
    from backtest import run_backtest as _bt
    return _bt(df)


def backtest_code(code: str, market_df: pd.DataFrame | None = None) -> dict:
    df = ensure_market_data(market_df if market_df is not None else load_parquet_from_r2())
    df = execute_strategy(code, df)

    if "signal" not in df.columns:
        raise ValueError("Strategy did not produce a 'signal' column")

    return run_backtest(df)


async def backtest_with_repair(prompt: str, code: str, market_df: pd.DataFrame) -> dict:
    errors: list[str] = []

    for attempt in range(max(1, MAX_CODE_ATTEMPTS)):
        try:
            result = backtest_code(code, market_df)
            summary = fallback_strategy_summary(prompt, code)
            if errors:
                summary += (
                    "\n\nHinweis: Der erste KI-Code musste automatisch repariert "
                    "oder durch eine robuste Fallback-Strategie ersetzt werden."
                )
            return {**result, "code": code, "summary": summary, "attempts": attempt + 1}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            errors.append(error)
            logger.warning("Generated strategy attempt %s failed: %s", attempt + 1, error.splitlines()[0])

            if attempt + 1 >= MAX_CODE_ATTEMPTS:
                break

            try:
                code = await repair_strategy_code(prompt, code, "\n\n".join(errors))
            except Exception as repair_exc:
                errors.append(f"Repair failed: {type(repair_exc).__name__}: {repair_exc}")
                break

    code = fallback_strategy_code(prompt)
    result = backtest_code(code, market_df)
    summary = fallback_strategy_summary(prompt, code)
    summary += (
        "\n\nHinweis: Der KI-Code war nicht lauffaehig. "
        "Der Server hat deshalb eine robuste Fallback-Strategie passend zum Prompt genutzt."
    )
    return {
        **result,
        "code": code,
        "summary": summary,
        "attempts": len(errors) + 1,
        "warnings": errors[-3:],
    }


async def generate_strategy(prompt: str) -> dict:
    started = time.perf_counter()
    code = await call_openrouter(prompt)
    return {
        "code": code,
        "model": OPENROUTER_MODEL,
        "timings": {"api_seconds": round(time.perf_counter() - started, 3)},
    }


async def run_prompt(prompt: str) -> dict:
    total_started = time.perf_counter()
    api_started = time.perf_counter()
    try:
        code = await call_openrouter(prompt)
        api_error = None
    except Exception as exc:
        code = fallback_strategy_code(prompt)
        api_error = f"{type(exc).__name__}: {exc}"
    api_seconds = time.perf_counter() - api_started

    market_df, cache_hit, data_seconds = get_market_data()
    backtest_started = time.perf_counter()
    result = await backtest_with_repair(prompt, code, market_df)
    backtest_seconds = time.perf_counter() - backtest_started

    timings = {
        "api_seconds": round(api_seconds, 3),
        "data_seconds": round(data_seconds, 3),
        "backtest_seconds": round(backtest_seconds, 3),
        "total_seconds": round(time.perf_counter() - total_started, 3),
        "data_cache_hit": cache_hit,
    }
    if api_error:
        timings["api_error"] = api_error
    return {**result, "timings": timings}


# ── Routes ───────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str

class BacktestRequest(BaseModel):
    code: str
    prompt: str = ""

@app.post("/generate")
async def generate(req: GenerateRequest):
    try:
        return await generate_strategy(req.prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@app.post("/backtest")
async def backtest(req: BacktestRequest):
    try:
        total_started = time.perf_counter()
        market_df, cache_hit, data_seconds = get_market_data()
        backtest_started = time.perf_counter()
        result = await backtest_with_repair(req.prompt, req.code, market_df)
        result["timings"] = {
            "data_seconds": round(data_seconds, 3),
            "backtest_seconds": round(time.perf_counter() - backtest_started, 3),
            "total_seconds": round(time.perf_counter() - total_started, 3),
            "data_cache_hit": cache_hit,
        }
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

@app.post("/run")
async def run(req: GenerateRequest):
    try:
        return await run_prompt(req.prompt)
    except Exception as e:
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
