"""
REST API for Claude Code Analytics
───────────────────────────────────
Exposes the analytics / prediction layer via FastAPI.

Run:
    uvicorn src.api:app --reload --port 8000

Swagger docs:  http://localhost:8000/docs
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sys

# Allow imports when running from project root
sys.path.insert(0, str(Path(__file__).parent))

from analytics import (
    kpi_summary,
    token_usage_by_practice,
    token_usage_by_model,
    cost_over_time,
    session_stats,
    peak_usage_by_hour,
    peak_usage_by_weekday,
    tool_usage_stats,
    tool_accept_by_practice,
    tool_result_performance,
    prompt_length_distribution,
    top_users_by_cost,
    terminal_type_distribution,
    cost_by_level,
    cost_by_location,
    tool_acceptance_by_level,
    avg_cost_per_user_by_practice_level,
)
from predict import (
    cost_forecast,
    token_forecast,
    detect_session_anomalies,
    detect_cost_anomalies_by_user,
)

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Claude Code Analytics API",
    description="Programmatic access to telemetry analytics and predictions.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = str(Path(__file__).parent.parent / "db" / "telemetry.db")


def _df_to_json(df):
    """Convert a pandas DataFrame to a list of dicts for JSON response."""
    return df.to_dict(orient="records")


# ─── Overview ─────────────────────────────────────────────────────────────────


@app.get("/api/kpi", tags=["Overview"])
def get_kpi():
    """High-level KPI summary (sessions, users, cost, tokens, …)."""
    return kpi_summary(DB)


# ─── Cost & Tokens ────────────────────────────────────────────────────────────


@app.get("/api/tokens/by-practice", tags=["Cost & Tokens"])
def get_tokens_by_practice():
    return _df_to_json(token_usage_by_practice(DB))


@app.get("/api/tokens/by-model", tags=["Cost & Tokens"])
def get_tokens_by_model():
    return _df_to_json(token_usage_by_model(DB))


@app.get("/api/cost/over-time", tags=["Cost & Tokens"])
def get_cost_over_time(granularity: str = Query("day", enum=["hour", "day"])):
    return _df_to_json(cost_over_time(DB, granularity=granularity))


# ─── Usage Patterns ───────────────────────────────────────────────────────────


@app.get("/api/sessions", tags=["Usage Patterns"])
def get_sessions(limit: int = Query(100, ge=1, le=5000)):
    df = session_stats(DB).head(limit)
    return _df_to_json(df)


@app.get("/api/usage/by-hour", tags=["Usage Patterns"])
def get_peak_by_hour():
    return _df_to_json(peak_usage_by_hour(DB))


@app.get("/api/usage/by-weekday", tags=["Usage Patterns"])
def get_peak_by_weekday():
    return _df_to_json(peak_usage_by_weekday(DB))


@app.get("/api/usage/terminal-types", tags=["Usage Patterns"])
def get_terminal_types():
    return _df_to_json(terminal_type_distribution(DB))


# ─── Tool Behavior ────────────────────────────────────────────────────────────


@app.get("/api/tools/usage", tags=["Tools"])
def get_tool_usage():
    return _df_to_json(tool_usage_stats(DB))


@app.get("/api/tools/acceptance-by-practice", tags=["Tools"])
def get_tool_acceptance_by_practice():
    return _df_to_json(tool_accept_by_practice(DB))


@app.get("/api/tools/performance", tags=["Tools"])
def get_tool_performance():
    return _df_to_json(tool_result_performance(DB))


# ─── Users ────────────────────────────────────────────────────────────────────


@app.get("/api/users/top", tags=["Users"])
def get_top_users(limit: int = Query(20, ge=1, le=200)):
    return _df_to_json(top_users_by_cost(DB, limit=limit))


@app.get("/api/users/prompts", tags=["Users"])
def get_prompt_stats():
    return _df_to_json(prompt_length_distribution(DB))


# ─── Employee Insights ────────────────────────────────────────────────────────


@app.get("/api/employees/cost-by-level", tags=["Employee Insights"])
def get_cost_by_level():
    return _df_to_json(cost_by_level(DB))


@app.get("/api/employees/cost-by-location", tags=["Employee Insights"])
def get_cost_by_location():
    return _df_to_json(cost_by_location(DB))


@app.get("/api/employees/tool-acceptance-by-level", tags=["Employee Insights"])
def get_tool_acceptance_by_level():
    return _df_to_json(tool_acceptance_by_level(DB))


@app.get("/api/employees/cost-heatmap", tags=["Employee Insights"])
def get_cost_heatmap():
    return _df_to_json(avg_cost_per_user_by_practice_level(DB))


# ─── Predictions ──────────────────────────────────────────────────────────────


@app.get("/api/predictions/cost-forecast", tags=["Predictions"])
def get_cost_forecast(days: int = Query(7, ge=1, le=90)):
    df = cost_forecast(DB, forecast_days=days)
    meta = {"r2": df.attrs.get("r2"), "slope_per_day": df.attrs.get("slope_per_day")}
    df["date"] = df["date"].astype(str)
    return {"meta": meta, "data": _df_to_json(df)}


@app.get("/api/predictions/token-forecast", tags=["Predictions"])
def get_token_forecast(days: int = Query(7, ge=1, le=90)):
    df = token_forecast(DB, forecast_days=days)
    meta = {"r2": df.attrs.get("r2")}
    df["date"] = df["date"].astype(str)
    return {"meta": meta, "data": _df_to_json(df)}


@app.get("/api/predictions/session-anomalies", tags=["Predictions"])
def get_session_anomalies(contamination: float = Query(0.05, ge=0.01, le=0.5)):
    df = detect_session_anomalies(DB, contamination=contamination)
    return _df_to_json(df)


@app.get("/api/predictions/user-anomalies", tags=["Predictions"])
def get_user_anomalies(contamination: float = Query(0.05, ge=0.01, le=0.5)):
    df = detect_cost_anomalies_by_user(DB, contamination=contamination)
    return _df_to_json(df)

