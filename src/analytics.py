import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "telemetry.db"


def get_conn(db_path: str = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Overview KPIs ────────────────────────────────────────────────────────────

def kpi_summary(db_path=None) -> dict:
    conn = get_conn(db_path)
    cur = conn.execute("""
        SELECT
            COUNT(DISTINCT session_id)                          AS total_sessions,
            COUNT(DISTINCT user_id)                             AS total_users,
            COUNT(DISTINCT user_practice)                       AS total_practices,
            COALESCE(SUM(cost_usd), 0)                          AS total_cost_usd,
            COALESCE(SUM(input_tokens + output_tokens), 0)      AS total_tokens,
            COUNT(CASE WHEN event_name = 'api_request' THEN 1 END) AS total_api_calls,
            COUNT(CASE WHEN event_name = 'user_prompt' THEN 1 END) AS total_prompts
        FROM events
    """)
    row = dict(cur.fetchone())
    conn.close()
    return row


# ─── Token & Cost Analytics ───────────────────────────────────────────────────

def token_usage_by_practice(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            user_practice,
            COUNT(*)                                      AS api_calls,
            SUM(input_tokens)                             AS input_tokens,
            SUM(output_tokens)                            AS output_tokens,
            SUM(cache_read_tokens)                        AS cache_read_tokens,
            SUM(input_tokens + output_tokens)             AS total_tokens,
            ROUND(SUM(cost_usd), 4)                       AS total_cost_usd,
            ROUND(AVG(cost_usd), 6)                       AS avg_cost_per_call
        FROM events
        WHERE event_name = 'api_request'
          AND user_practice IS NOT NULL
        GROUP BY user_practice
        ORDER BY total_cost_usd DESC
    """, conn)
    conn.close()
    return df


def token_usage_by_model(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            model,
            COUNT(*)                                      AS api_calls,
            SUM(input_tokens + output_tokens)             AS total_tokens,
            ROUND(SUM(cost_usd), 4)                       AS total_cost_usd,
            ROUND(AVG(duration_ms), 0)                    AS avg_duration_ms
        FROM events
        WHERE event_name = 'api_request'
          AND model IS NOT NULL
        GROUP BY model
        ORDER BY total_cost_usd DESC
    """, conn)
    conn.close()
    return df


def cost_over_time(db_path=None, granularity: str = "hour") -> pd.DataFrame:
    """granularity: 'hour' | 'day' """
    fmt = "%Y-%m-%d %H:00" if granularity == "hour" else "%Y-%m-%d"
    conn = get_conn(db_path)
    df = pd.read_sql_query(f"""
        SELECT
            strftime('{fmt}', event_timestamp) AS period,
            ROUND(SUM(cost_usd), 6)            AS cost_usd,
            SUM(input_tokens + output_tokens)  AS total_tokens,
            COUNT(*)                           AS api_calls
        FROM events
        WHERE event_name = 'api_request'
          AND event_timestamp IS NOT NULL
        GROUP BY period
        ORDER BY period
    """, conn)
    conn.close()
    return df


# ─── Session Analytics ────────────────────────────────────────────────────────

def session_stats(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            session_id,
            user_practice,
            user_email,
            MIN(event_timestamp) AS session_start,
            MAX(event_timestamp) AS session_end,
            COUNT(CASE WHEN event_name = 'user_prompt'  THEN 1 END) AS prompts,
            COUNT(CASE WHEN event_name = 'api_request'  THEN 1 END) AS api_calls,
            COUNT(CASE WHEN event_name = 'tool_decision' THEN 1 END) AS tool_decisions,
            ROUND(SUM(cost_usd), 6)                                  AS session_cost_usd,
            SUM(input_tokens + output_tokens)                        AS session_tokens
        FROM events
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        ORDER BY session_cost_usd DESC
    """, conn)
    conn.close()
    return df


def peak_usage_by_hour(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            CAST(strftime('%H', event_timestamp) AS INTEGER) AS hour_of_day,
            COUNT(*)                                          AS event_count,
            ROUND(SUM(cost_usd), 4)                          AS cost_usd
        FROM events
        WHERE event_timestamp IS NOT NULL
        GROUP BY hour_of_day
        ORDER BY hour_of_day
    """, conn)
    conn.close()
    return df


def peak_usage_by_weekday(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            CASE strftime('%w', event_timestamp)
                WHEN '0' THEN 'Sunday'
                WHEN '1' THEN 'Monday'
                WHEN '2' THEN 'Tuesday'
                WHEN '3' THEN 'Wednesday'
                WHEN '4' THEN 'Thursday'
                WHEN '5' THEN 'Friday'
                WHEN '6' THEN 'Saturday'
            END AS weekday,
            strftime('%w', event_timestamp) AS weekday_num,
            COUNT(*) AS event_count,
            ROUND(SUM(cost_usd), 4) AS cost_usd
        FROM events
        WHERE event_timestamp IS NOT NULL
        GROUP BY weekday_num
        ORDER BY weekday_num
    """, conn)
    conn.close()
    return df


# ─── Tool Usage Analytics ─────────────────────────────────────────────────────

def tool_usage_stats(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            tool_name,
            COUNT(*)                                                      AS total_uses,
            COUNT(CASE WHEN decision = 'accept' THEN 1 END)              AS accepted,
            COUNT(CASE WHEN decision = 'reject'  THEN 1 END)             AS rejected,
            ROUND(100.0 * COUNT(CASE WHEN decision = 'accept' THEN 1 END)
                  / COUNT(*), 1)                                          AS accept_rate_pct
        FROM events
        WHERE event_name = 'tool_decision'
          AND tool_name IS NOT NULL
        GROUP BY tool_name
        ORDER BY total_uses DESC
    """, conn)
    conn.close()
    return df


def tool_accept_by_practice(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            user_practice,
            tool_name,
            COUNT(*)                                                      AS uses,
            ROUND(100.0 * COUNT(CASE WHEN decision = 'accept' THEN 1 END)
                  / COUNT(*), 1)                                          AS accept_rate_pct
        FROM events
        WHERE event_name = 'tool_decision'
          AND tool_name IS NOT NULL
          AND user_practice IS NOT NULL
        GROUP BY user_practice, tool_name
        ORDER BY user_practice, uses DESC
    """, conn)
    conn.close()
    return df


def tool_result_performance(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            tool_name,
            COUNT(*)                                                       AS executions,
            COUNT(CASE WHEN success = 'true' THEN 1 END)                  AS successes,
            ROUND(100.0 * COUNT(CASE WHEN success = 'true' THEN 1 END)
                  / COUNT(*), 1)                                           AS success_rate_pct,
            ROUND(AVG(duration_ms), 0)                                     AS avg_duration_ms
        FROM events
        WHERE event_name = 'tool_result'
          AND tool_name IS NOT NULL
        GROUP BY tool_name
        ORDER BY executions DESC
    """, conn)
    conn.close()
    return df


# ─── Prompt Analytics ─────────────────────────────────────────────────────────

def prompt_length_distribution(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            user_practice,
            ROUND(AVG(prompt_length), 0) AS avg_prompt_length,
            MIN(prompt_length)           AS min_prompt_length,
            MAX(prompt_length)           AS max_prompt_length,
            COUNT(*)                     AS prompt_count
        FROM events
        WHERE event_name = 'user_prompt'
          AND prompt_length IS NOT NULL
        GROUP BY user_practice
        ORDER BY avg_prompt_length DESC
    """, conn)
    conn.close()
    return df


# ─── User Behavior ────────────────────────────────────────────────────────────

def top_users_by_cost(db_path=None, limit: int = 20) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query(f"""
        SELECT
            user_email,
            user_practice,
            COUNT(DISTINCT session_id)                AS sessions,
            ROUND(SUM(cost_usd), 4)                   AS total_cost_usd,
            SUM(input_tokens + output_tokens)         AS total_tokens,
            COUNT(CASE WHEN event_name = 'user_prompt' THEN 1 END) AS prompts
        FROM events
        WHERE user_email IS NOT NULL AND user_email != ''
        GROUP BY user_email
        ORDER BY total_cost_usd DESC
        LIMIT {limit}
    """, conn)
    conn.close()
    return df


def terminal_type_distribution(db_path=None) -> pd.DataFrame:
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            terminal_type,
            COUNT(DISTINCT session_id) AS sessions,
            COUNT(DISTINCT user_id)    AS users
        FROM events
        WHERE terminal_type IS NOT NULL
        GROUP BY terminal_type
        ORDER BY sessions DESC
    """, conn)
    conn.close()
    return df


# ─── Employee-enriched Analytics (requires user_metadata table) ───────────────

def cost_by_level(db_path=None) -> pd.DataFrame:
    """Cost & token usage broken down by seniority level (L1–L10)."""
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            m.level,
            COUNT(DISTINCT e.session_id)              AS sessions,
            COUNT(DISTINCT e.user_email)              AS users,
            ROUND(SUM(e.cost_usd), 4)                 AS total_cost_usd,
            ROUND(AVG(e.cost_usd), 6)                 AS avg_cost_per_call,
            SUM(e.input_tokens + e.output_tokens)     AS total_tokens
        FROM events e
        JOIN user_metadata m ON e.user_email = m.email
        WHERE e.event_name = 'api_request' AND m.level IS NOT NULL
        GROUP BY m.level
        ORDER BY m.level
    """, conn)
    conn.close()
    return df


def cost_by_location(db_path=None) -> pd.DataFrame:
    """Cost breakdown by office location."""
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            m.location,
            COUNT(DISTINCT e.user_email)              AS users,
            ROUND(SUM(e.cost_usd), 4)                 AS total_cost_usd,
            SUM(e.input_tokens + e.output_tokens)     AS total_tokens,
            COUNT(CASE WHEN e.event_name = 'api_request' THEN 1 END) AS api_calls
        FROM events e
        JOIN user_metadata m ON e.user_email = m.email
        WHERE m.location IS NOT NULL
        GROUP BY m.location
        ORDER BY total_cost_usd DESC
    """, conn)
    conn.close()
    return df


def tool_acceptance_by_level(db_path=None) -> pd.DataFrame:
    """Do senior engineers accept/reject tools differently than juniors?"""
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            m.level,
            e.tool_name,
            COUNT(*)                                                        AS uses,
            ROUND(100.0 * COUNT(CASE WHEN e.decision = 'accept' THEN 1 END)
                  / COUNT(*), 1)                                            AS accept_rate_pct
        FROM events e
        JOIN user_metadata m ON e.user_email = m.email
        WHERE e.event_name = 'tool_decision' AND e.tool_name IS NOT NULL
        GROUP BY m.level, e.tool_name
        ORDER BY m.level, uses DESC
    """, conn)
    conn.close()
    return df


def avg_cost_per_user_by_practice_level(db_path=None) -> pd.DataFrame:
    """Heatmap-ready: avg cost per user, practice × level."""
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            m.practice,
            m.level,
            ROUND(SUM(e.cost_usd) / COUNT(DISTINCT e.user_email), 4) AS avg_cost_per_user
        FROM events e
        JOIN user_metadata m ON e.user_email = m.email
        WHERE e.event_name = 'api_request'
        GROUP BY m.practice, m.level
        ORDER BY m.practice, m.level
    """, conn)
    conn.close()
    return df


# ─── Advanced Statistical Analysis ───────────────────────────────────────────


def prompt_cost_correlation(db_path=None) -> dict:
    """
    Pearson correlation between prompt length and subsequent API cost.
    Computed per session (avg prompt length vs. total session cost).
    """
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            session_id,
            AVG(CASE WHEN event_name = 'user_prompt' THEN prompt_length END) AS avg_prompt_len,
            SUM(CASE WHEN event_name = 'api_request' THEN cost_usd END)      AS session_cost
        FROM events
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        HAVING avg_prompt_len IS NOT NULL AND session_cost IS NOT NULL
    """, conn)
    conn.close()

    if len(df) < 5:
        return {"correlation": None, "p_value": None, "n": len(df)}

    from scipy import stats
    r, p = stats.pearsonr(df["avg_prompt_len"], df["session_cost"])
    return {
        "correlation": round(r, 4),
        "p_value": round(p, 6),
        "n": len(df),
        "interpretation": (
            "Strong positive" if r > 0.7 else
            "Moderate positive" if r > 0.4 else
            "Weak positive" if r > 0.1 else
            "Negligible" if r > -0.1 else
            "Negative"
        ),
    }


def session_duration_stats(db_path=None) -> dict:
    """
    Distribution statistics for session duration (in minutes).
    Returns mean, median, std, percentiles, and a histogram-ready DataFrame.
    """
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            session_id,
            user_practice,
            ROUND((JULIANDAY(MAX(event_timestamp))
                 - JULIANDAY(MIN(event_timestamp))) * 1440, 2) AS duration_min
        FROM events
        WHERE session_id IS NOT NULL AND event_timestamp IS NOT NULL
        GROUP BY session_id
        HAVING duration_min > 0
    """, conn)
    conn.close()

    if df.empty:
        return {"stats": {}, "data": pd.DataFrame()}

    d = df["duration_min"]
    stats_dict = {
        "mean": round(float(d.mean()), 2),
        "median": round(float(d.median()), 2),
        "std": round(float(d.std()), 2),
        "p25": round(float(d.quantile(0.25)), 2),
        "p75": round(float(d.quantile(0.75)), 2),
        "p90": round(float(d.quantile(0.90)), 2),
        "p95": round(float(d.quantile(0.95)), 2),
        "max": round(float(d.max()), 2),
        "count": len(d),
    }
    return {"stats": stats_dict, "data": df}


def cost_efficiency_by_model(db_path=None) -> pd.DataFrame:
    """
    Tokens-per-dollar and cost-per-1K-tokens for each model.
    Useful for identifying the most cost-efficient model.
    """
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            model,
            COUNT(*)                                        AS api_calls,
            SUM(input_tokens + output_tokens)              AS total_tokens,
            ROUND(SUM(cost_usd), 6)                        AS total_cost_usd,
            ROUND(AVG(duration_ms), 0)                     AS avg_latency_ms
        FROM events
        WHERE event_name = 'api_request'
          AND model IS NOT NULL
          AND cost_usd > 0
        GROUP BY model
        ORDER BY total_cost_usd DESC
    """, conn)
    conn.close()

    if not df.empty:
        df["tokens_per_dollar"] = np.where(
            df["total_cost_usd"] > 0,
            (df["total_tokens"] / df["total_cost_usd"]).round(0).astype(int),
            0,
        )
        df["cost_per_1k_tokens"] = np.where(
            df["total_tokens"] > 0,
            (df["total_cost_usd"] / df["total_tokens"] * 1000).round(6),
            0,
        )
    return df


def user_engagement_clusters(db_path=None, n_clusters: int = 4) -> pd.DataFrame:
    """
    K-Means clustering of users by engagement features:
      sessions, api_calls, prompts, total_cost, avg_prompt_length
    Returns user-level data with a 'cluster' label.
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans

    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            user_email,
            user_practice,
            COUNT(DISTINCT session_id)                                          AS sessions,
            COUNT(CASE WHEN event_name = 'api_request' THEN 1 END)            AS api_calls,
            COUNT(CASE WHEN event_name = 'user_prompt' THEN 1 END)            AS prompts,
            COALESCE(SUM(cost_usd), 0)                                         AS total_cost,
            COALESCE(AVG(CASE WHEN event_name = 'user_prompt'
                              THEN prompt_length END), 0)                      AS avg_prompt_len
        FROM events
        WHERE user_email IS NOT NULL AND user_email != ''
        GROUP BY user_email
    """, conn)
    conn.close()

    if len(df) < n_clusters:
        df["cluster"] = 0
        return df

    feature_cols = ["sessions", "api_calls", "prompts", "total_cost", "avg_prompt_len"]
    X = df[feature_cols].fillna(0).values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df["cluster"] = km.fit_predict(X_scaled)

    return df.sort_values("cluster")


def cache_efficiency(db_path=None) -> pd.DataFrame:
    """
    Cache hit-rate analysis: what fraction of input tokens came from cache?
    Broken down by practice.
    """
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            user_practice,
            SUM(input_tokens)                                   AS total_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0)                 AS cache_read_tokens,
            COALESCE(SUM(cache_creation_tokens), 0)             AS cache_creation_tokens,
            ROUND(100.0 * COALESCE(SUM(cache_read_tokens), 0)
                  / NULLIF(SUM(input_tokens), 0), 2)            AS cache_hit_rate_pct
        FROM events
        WHERE event_name = 'api_request'
          AND user_practice IS NOT NULL
        GROUP BY user_practice
        ORDER BY cache_hit_rate_pct DESC
    """, conn)
    conn.close()
    return df


def api_error_analysis(db_path=None) -> pd.DataFrame:
    """Error rate analysis by practice and model."""
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            user_practice,
            model,
            COUNT(CASE WHEN event_name = 'api_request' THEN 1 END) AS api_requests,
            COUNT(CASE WHEN event_name = 'api_error'   THEN 1 END) AS api_errors,
            ROUND(100.0 * COUNT(CASE WHEN event_name = 'api_error' THEN 1 END)
                  / NULLIF(COUNT(CASE WHEN event_name IN ('api_request', 'api_error')
                                 THEN 1 END), 0), 2)               AS error_rate_pct
        FROM events
        WHERE event_name IN ('api_request', 'api_error')
          AND user_practice IS NOT NULL
        GROUP BY user_practice, model
        HAVING api_requests + api_errors > 5
        ORDER BY error_rate_pct DESC
    """, conn)
    conn.close()
    return df

