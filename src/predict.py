"""
Predictive Analytics Module
───────────────────────────
Provides trend forecasting and anomaly detection on top of the
telemetry data stored in SQLite.

Features
--------
* **Cost Forecast** – Linear-regression forecast of daily API cost for
  the next *N* days.
* **Token Forecast** – Same approach for aggregate token consumption.
* **Anomaly Detection** – Isolation-Forest model flags sessions whose
  cost / token profile deviates significantly from the population.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression

DB_PATH = Path(__file__).parent.parent / "db" / "telemetry.db"


def _get_conn(db_path=None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Trend Forecasting ───────────────────────────────────────────────────────


def cost_forecast(db_path=None, forecast_days: int = 7) -> pd.DataFrame:
    """
    Fit a simple linear-regression on daily cost and predict the next
    *forecast_days*.  Returns a DataFrame with columns:
        date | cost_usd | type   ('actual' | 'forecast')
    """
    conn = _get_conn(db_path)
    df = pd.read_sql_query(
        """
        SELECT
            DATE(event_timestamp) AS date,
            SUM(cost_usd)         AS cost_usd
        FROM events
        WHERE event_name = 'api_request'
          AND event_timestamp IS NOT NULL
          AND cost_usd IS NOT NULL
        GROUP BY date
        ORDER BY date
        """,
        conn,
    )
    conn.close()

    if df.empty or len(df) < 3:
        return pd.DataFrame(columns=["date", "cost_usd", "type"])

    df["date"] = pd.to_datetime(df["date"])
    df["day_num"] = (df["date"] - df["date"].min()).dt.days

    X = df[["day_num"]].values
    y = df["cost_usd"].values

    model = LinearRegression().fit(X, y)

    # Forecast
    last_day = int(df["day_num"].max())
    future_days = np.arange(last_day + 1, last_day + 1 + forecast_days).reshape(-1, 1)
    future_cost = model.predict(future_days).clip(min=0)

    future_dates = pd.date_range(
        start=df["date"].max() + pd.Timedelta(days=1),
        periods=forecast_days,
    )

    df_actual = df[["date", "cost_usd"]].copy()
    df_actual["type"] = "actual"

    df_forecast = pd.DataFrame(
        {"date": future_dates, "cost_usd": future_cost, "type": "forecast"}
    )

    result = pd.concat([df_actual, df_forecast], ignore_index=True)

    # Attach model metadata
    result.attrs["r2"] = round(model.score(X, y), 4)
    result.attrs["slope_per_day"] = round(float(model.coef_[0]), 6)
    result.attrs["intercept"] = round(float(model.intercept_), 6)
    return result


def token_forecast(db_path=None, forecast_days: int = 7) -> pd.DataFrame:
    """
    Linear-regression forecast for daily token consumption.
    """
    conn = _get_conn(db_path)
    df = pd.read_sql_query(
        """
        SELECT
            DATE(event_timestamp) AS date,
            SUM(input_tokens + output_tokens) AS total_tokens
        FROM events
        WHERE event_name = 'api_request'
          AND event_timestamp IS NOT NULL
        GROUP BY date
        ORDER BY date
        """,
        conn,
    )
    conn.close()

    if df.empty or len(df) < 3:
        return pd.DataFrame(columns=["date", "total_tokens", "type"])

    df["date"] = pd.to_datetime(df["date"])
    df["day_num"] = (df["date"] - df["date"].min()).dt.days

    X = df[["day_num"]].values
    y = df["total_tokens"].values.astype(float)

    model = LinearRegression().fit(X, y)

    last_day = int(df["day_num"].max())
    future_days = np.arange(last_day + 1, last_day + 1 + forecast_days).reshape(-1, 1)
    future_tokens = model.predict(future_days).clip(min=0)

    future_dates = pd.date_range(
        start=df["date"].max() + pd.Timedelta(days=1),
        periods=forecast_days,
    )

    df_actual = df[["date", "total_tokens"]].copy()
    df_actual["type"] = "actual"

    df_forecast = pd.DataFrame(
        {"date": future_dates, "total_tokens": future_tokens, "type": "forecast"}
    )

    result = pd.concat([df_actual, df_forecast], ignore_index=True)
    result.attrs["r2"] = round(model.score(X, y), 4)
    return result


# ─── Anomaly Detection ───────────────────────────────────────────────────────


def detect_session_anomalies(
    db_path=None, contamination: float = 0.05
) -> pd.DataFrame:
    """
    Use Isolation Forest to flag anomalous sessions.

    Features used per session:
      - total cost
      - total tokens
      - number of API calls
      - number of prompts
      - avg prompt length
      - session duration (minutes)

    Returns all sessions with an 'is_anomaly' boolean column
    (True = outlier) and an 'anomaly_score'.
    """
    conn = _get_conn(db_path)
    df = pd.read_sql_query(
        """
        SELECT
            session_id,
            user_email,
            user_practice,
            COALESCE(SUM(cost_usd), 0)                                       AS total_cost,
            COALESCE(SUM(input_tokens + output_tokens), 0)                   AS total_tokens,
            COUNT(CASE WHEN event_name = 'api_request'  THEN 1 END)          AS api_calls,
            COUNT(CASE WHEN event_name = 'user_prompt'  THEN 1 END)          AS prompts,
            COALESCE(AVG(CASE WHEN event_name = 'user_prompt'
                              THEN prompt_length END), 0)                    AS avg_prompt_len,
            ROUND((JULIANDAY(MAX(event_timestamp))
                 - JULIANDAY(MIN(event_timestamp))) * 1440, 1)               AS duration_min
        FROM events
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        """,
        conn,
    )
    conn.close()

    if df.empty or len(df) < 10:
        df["is_anomaly"] = False
        df["anomaly_score"] = 0.0
        return df

    feature_cols = [
        "total_cost",
        "total_tokens",
        "api_calls",
        "prompts",
        "avg_prompt_len",
        "duration_min",
    ]
    X = df[feature_cols].fillna(0).values

    iso = IsolationForest(
        contamination=contamination, random_state=42, n_jobs=-1
    )
    preds = iso.fit_predict(X)        # 1 = normal, -1 = anomaly
    scores = iso.decision_function(X)  # lower = more anomalous

    df["is_anomaly"] = preds == -1
    df["anomaly_score"] = np.round(scores, 4)

    return df.sort_values("anomaly_score")


def detect_cost_anomalies_by_user(
    db_path=None, contamination: float = 0.05
) -> pd.DataFrame:
    """
    Flag individual users whose overall spending pattern is anomalous
    (Isolation Forest on aggregated user-level features).
    """
    conn = _get_conn(db_path)
    df = pd.read_sql_query(
        """
        SELECT
            user_email,
            user_practice,
            COUNT(DISTINCT session_id)                          AS sessions,
            COALESCE(SUM(cost_usd), 0)                          AS total_cost,
            COALESCE(SUM(input_tokens + output_tokens), 0)      AS total_tokens,
            COUNT(CASE WHEN event_name = 'api_request'  THEN 1 END) AS api_calls,
            COUNT(CASE WHEN event_name = 'user_prompt'  THEN 1 END) AS prompts
        FROM events
        WHERE user_email IS NOT NULL AND user_email != ''
        GROUP BY user_email
        """,
        conn,
    )
    conn.close()

    if df.empty or len(df) < 10:
        df["is_anomaly"] = False
        df["anomaly_score"] = 0.0
        return df

    feature_cols = ["sessions", "total_cost", "total_tokens", "api_calls", "prompts"]
    X = df[feature_cols].fillna(0).values

    iso = IsolationForest(contamination=contamination, random_state=42, n_jobs=-1)
    preds = iso.fit_predict(X)
    scores = iso.decision_function(X)

    df["is_anomaly"] = preds == -1
    df["anomaly_score"] = np.round(scores, 4)

    return df.sort_values("anomaly_score")

