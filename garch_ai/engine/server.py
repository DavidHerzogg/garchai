import os
import io
import textwrap
import traceback
import boto3
import pandas as pd
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="GARCH AI Engine")

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
OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-coder:free")
OPENROUTER_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:8000")

SYSTEM_PROMPT = """
You are a quantitative trading code generator.
Return ONLY valid Python code — no markdown, no explanation.
The function signature MUST be:
    def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
Rules:
- Input df columns: timestamp, open, high, low, close, volume
- Add column "signal" ∈ {-1, 0, 1} (1=long, -1=short, 0=flat)
- Use ONLY past data (no lookahead)
- Use only pandas and numpy
- Return the modified df
- Max 20 lines of logic
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
    )
    obj = s3.get_object(Bucket=R2_BUCKET, Key=R2_KEY)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


async def call_openrouter(user_prompt: str) -> str:
    if not OPENROUTER_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": OPENROUTER_REFERER,
                "X-Title": "GARCH AI",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                "temperature": 0,
            },
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise RuntimeError(
                f"OpenRouter request failed ({exc.response.status_code}): {detail}"
            ) from exc

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned an empty response")
        return content.strip()


def execute_strategy(code: str, df: pd.DataFrame) -> pd.DataFrame:
    # Strip markdown fences if model wrapped the code
    if code.startswith("```"):
        code = "\n".join(
            line for line in code.splitlines()
            if not line.strip().startswith("```")
        )
    namespace: dict = {}
    exec(textwrap.dedent(code), {"pd": pd, "np": __import__("numpy")}, namespace)
    if "generate_signals" not in namespace:
        raise ValueError("generate_signals function not found in generated code")
    return namespace["generate_signals"](df)


def run_backtest(df: pd.DataFrame) -> dict:
    from backtest import run_backtest as _bt
    return _bt(df)


def backtest_code(code: str) -> dict:
    df = load_parquet_from_r2()
    df = execute_strategy(code, df)

    if "signal" not in df.columns:
        raise ValueError("Strategy did not produce a 'signal' column")

    return run_backtest(df)


async def run_prompt(prompt: str) -> dict:
    code = await call_openrouter(prompt)
    result = backtest_code(code)
    return {**result, "code": code}


# ── Routes ───────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str

class BacktestRequest(BaseModel):
    code: str

@app.post("/generate")
async def generate(req: GenerateRequest):
    try:
        code = await call_openrouter(req.prompt)
        return {"code": code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@app.post("/backtest")
async def backtest(req: BacktestRequest):
    try:
        return backtest_code(req.code)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

@app.post("/run")
async def run(req: GenerateRequest):
    try:
        return await run_prompt(req.prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

@app.get("/health")
def health():
    return {"status": "ok"}
