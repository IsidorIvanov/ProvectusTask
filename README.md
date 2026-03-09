# 🤖 Claude Code Usage Analytics Platform

An end-to-end analytics platform that processes telemetry data from Claude Code sessions, transforming raw event streams into actionable insights about developer behavior through an interactive dashboard, REST API, and ML-powered predictions.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green)
![scikit--learn](https://img.shields.io/badge/scikit--learn-1.4+-orange)
![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey)
![Plotly](https://img.shields.io/badge/Plotly-5.22+-purple)

---

## 📋 Table of Contents

- [Architecture Overview](#-architecture-overview)
- [Data Flow & Pipeline](#-data-flow--pipeline)
- [Database Schema](#-database-schema)
- [Module-by-Module Code Walkthrough](#-module-by-module-code-walkthrough)
- [Features](#-features)
- [Dependencies](#-dependencies)
- [Setup Instructions](#-setup-instructions)
- [Usage](#-usage)
- [API Documentation](#-api-documentation)
- [Key Insights & Findings](#-key-insights--findings)
- [LLM Usage Log](#-llm-usage-log)

---

## 🏗️ Architecture Overview

The platform follows a **layered pipeline architecture** with clear separation of concerns:

```
┌──────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                              │
│                                                                  │
│   telemetry_logs.jsonl              employees.csv                │
│   ┌──────────────────────┐          ┌──────────────────────┐     │
│   │ 454K+ telemetry      │          │ 100 engineers        │     │
│   │ events in nested     │          │ email, name,         │     │
│   │ JSONL (CloudWatch    │          │ practice, level,     │     │
│   │ DATA_MESSAGE format) │          │ location             │     │
│   └──────────┬───────────┘          └──────────┬───────────┘     │
└──────────────┼──────────────────────────────────┼────────────────┘
               │                                  │
               ▼                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                    INGESTION LAYER (ingest.py)                    │
│                                                                  │
│   • Stream-parses JSONL line-by-line (never loads full file)     │
│   • Chunked DB writes (1,000 events/batch) for low memory       │
│   • Flattens nested JSON: message → attributes + resource       │
│   • Type-safe converters: _int(), _float() with try/except      │
│   • CSV DictReader for employee metadata                         │
│   • INSERT OR IGNORE deduplication on event ID                   │
│   • WAL journal mode + NORMAL sync for fast writes               │
│   • Validates messageType == "DATA_MESSAGE" before processing    │
│   • Logs warnings for malformed JSON, continues processing      │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                STORAGE LAYER (SQLite — db/telemetry.db)           │
│                                                                  │
│   Table: events (454K rows)          Table: user_metadata        │
│   ┌────────────────────────┐         ┌────────────────────┐      │
│   │ 27 columns (flattened) │         │ email (PK)         │      │
│   │ 6 indexes for fast     │    JOIN │ full_name          │      │
│   │ analytical queries     │◄────────│ practice           │      │
│   │                        │  email  │ level (L1–L10)     │      │
│   │ See schema below       │         │ location           │      │
│   └────────────────────────┘         └────────────────────┘      │
│                                                                  │
│   Indexes: event_name, session_id, user_id,                      │
│            user_practice, model, timestamp                        │
└─────┬──────────────────┬─────────────────────┬───────────────────┘
      │                  │                     │
      ▼                  ▼                     ▼
┌──────────────┐  ┌───────────────────┐  ┌───────────────────┐
│  Analytics   │  │   Predictions     │  │    REST API       │
│ (analytics   │  │   (predict.py)    │  │    (api.py)       │
│     .py)     │  │                   │  │                   │
│              │  │ • LinearRegression│  │ • FastAPI app     │
│ 20+ SQL      │  │   cost forecast   │  │ • 18 GET endpts  │
│ analytics    │  │ • LinearRegression│  │ • Swagger /docs   │
│ functions    │  │   token forecast  │  │ • CORS enabled    │
│              │  │ • IsolationForest │  │ • Query params    │
│ • KPIs       │  │   session anomaly │  │ • JSON responses  │
│ • Cost/Token │  │ • IsolationForest │  │                   │
│ • Sessions   │  │   user anomaly    │  │ Covers all        │
│ • Tools      │  │                   │  │ analytics +       │
│ • Users      │  │ • StandardScaler  │  │ predictions       │
│ • Prompts    │  │ • KMeans clusters │  │                   │
│ • Employees  │  │                   │  │                   │
│ • Stats      │  │                   │  │                   │
└──────┬───────┘  └────────┬──────────┘  └───────────────────┘
       │                   │
       ▼                   ▼
┌──────────────────────────────────────────────────────────────────┐
│              VISUALIZATION LAYER (dashboard.py)                   │
│                                                                  │
│   Streamlit + Plotly — 8 interactive tabs, 30+ charts:           │
│                                                                  │
│   💰 Cost & Tokens    ⏱️ Usage Patterns    🛠️ Tool Behavior     │
│   👤 Users            📝 Prompts           🏢 Employee Insights  │
│   🔮 Predictions      📊 Advanced Stats                         │
│                                                                  │
│   Sidebar: DB path config, time granularity selector             │
│   Header:  5 KPI metric cards (sessions, users, calls, $, toks) │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│            STREAMING LAYER (stream_simulator.py)                  │
│                                                                  │
│   Replays JSONL events into SQLite with configurable speed,      │
│   demonstrating real-time ingestion capability.                   │
│   Assigns fresh IDs to avoid dedup; batched inserts with delays. │
└──────────────────────────────────────────────────────────────────┘
```

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **SQLite** over PostgreSQL | Zero-config, portable, single-file DB; sufficient for 454K rows; WAL mode enables concurrent dashboard reads during streaming writes |
| **Chunked ingestion** (1,000 events/batch) | Keeps memory usage constant regardless of file size; enables progress logging |
| **Flat `events` table** (27 columns) | Avoids complex JOINs for 90% of analytics queries; single-table scans are fast at this scale |
| **`user_metadata` as separate table** | Clean separation of concerns; JOIN only when employee-enriched analytics needed |
| **Streamlit** for dashboard | Rapid prototyping, native Plotly support, interactive widgets, auto-refresh capability |
| **FastAPI** for API | Auto-generated OpenAPI/Swagger docs, type validation via Pydantic, async-ready |
| **Isolation Forest** for anomalies | Unsupervised (no labels required); handles high-dimensional feature spaces well |
| **K-Means** for user clustering | Simple, interpretable clusters; StandardScaler ensures feature parity |
| **Linear Regression** for forecasting | Transparent baseline model; R² score communicates fit quality clearly |

---

## 🔄 Data Flow & Pipeline

```
1. RAW DATA
   telemetry_logs.jsonl — each line is a CloudWatch DATA_MESSAGE containing
   a "logEvents" array. Each logEvent has:
     • id (unique event identifier)
     • timestamp (epoch ms)
     • message (JSON string containing body, attributes, resource)

   employees.csv — standard CSV with columns:
     email, full_name, practice, level, location

2. INGESTION (ingest.py)
   For each JSONL line:
     a) json.loads(line) → extract outer envelope
     b) Validate messageType == "DATA_MESSAGE"
     c) Iterate logEvents array
     d) json.loads(event["message"]) → extract attributes & resource dicts
     e) Flatten into 27-column dict with safe type converters
     f) Buffer in memory (up to 1,000 events)
     g) executemany INSERT OR IGNORE → flush to SQLite
     h) Repeat until EOF

   For CSV:
     a) csv.DictReader reads rows
     b) INSERT OR REPLACE into user_metadata table

3. ANALYTICS (analytics.py)
   Each function:
     a) Opens SQLite connection (row_factory = sqlite3.Row)
     b) Executes parameterized SQL query
     c) Returns pandas DataFrame or dict
     d) Caller (dashboard/api) handles presentation

4. PREDICTIONS (predict.py)
   Forecasting:
     a) Query daily aggregated cost/tokens from SQLite
     b) Create day_num feature (days since first observation)
     c) Fit LinearRegression on (day_num → cost/tokens)
     d) Predict next N days, clip at 0
     e) Return combined actual + forecast DataFrame with R² metadata

   Anomaly Detection:
     a) Query session/user-level aggregated features from SQLite
     b) IsolationForest.fit_predict() → labels (-1 = anomaly)
     c) decision_function() → anomaly scores
     d) Return DataFrame with is_anomaly + anomaly_score columns

5. VISUALIZATION (dashboard.py)
   a) Streamlit renders sidebar (settings) + header (KPIs)
   b) 8 tabs call analytics/predict functions
   c) Results rendered as Plotly charts + DataFrames
   d) Interactive widgets (sliders, selectors) control parameters

6. API (api.py)
   a) FastAPI app with CORS middleware
   b) Each endpoint calls an analytics/predict function
   c) DataFrame.to_dict(orient="records") → JSON response
   d) Swagger auto-docs at /docs
```

---

## 🗄️ Database Schema

### Table: `events` (454,428 rows)

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| `id` | TEXT (PK) | `logEvent.id` | Unique event identifier |
| `timestamp` | INTEGER (NOT NULL) | `logEvent.timestamp` | Epoch timestamp (ms) from CloudWatch |
| `event_timestamp` | TEXT | `attributes.event.timestamp` | ISO-8601 timestamp from the event itself |
| `event_name` | TEXT (NOT NULL) | `attributes.event.name` | Event type: `api_request`, `user_prompt`, `tool_decision`, `tool_result`, etc. |
| `organization_id` | TEXT | `attributes.organization.id` | Organization identifier |
| `session_id` | TEXT | `attributes.session.id` | Coding session identifier |
| `user_id` | TEXT | `attributes.user.id` | User identifier |
| `user_email` | TEXT | `attributes.user.email` | User email (JOIN key to `user_metadata`) |
| `user_practice` | TEXT | `resource.user.practice` | Engineering practice (Frontend, Backend, Data, ML, Platform) |
| `user_profile` | TEXT | `resource.user.profile` | User profile type |
| `terminal_type` | TEXT | `attributes.terminal.type` | Terminal/IDE type |
| `model` | TEXT | `attributes.model` | AI model used (e.g., `claude-sonnet-4-20250514`) |
| `input_tokens` | INTEGER | `attributes.input_tokens` | Number of input tokens consumed |
| `output_tokens` | INTEGER | `attributes.output_tokens` | Number of output tokens generated |
| `cache_creation_tokens` | INTEGER | `attributes.cache_creation_tokens` | Tokens used to create cache |
| `cache_read_tokens` | INTEGER | `attributes.cache_read_tokens` | Tokens read from cache |
| `cost_usd` | REAL | `attributes.cost_usd` | Cost of the API call in USD |
| `duration_ms` | INTEGER | `attributes.duration_ms` | API call duration in milliseconds |
| `prompt_length` | INTEGER | `attributes.prompt_length` | Character length of user prompt |
| `tool_name` | TEXT | `attributes.tool_name` | Name of tool used (e.g., `Read`, `Write`, `Bash`) |
| `decision` | TEXT | `attributes.decision` | Tool decision: `accept` or `reject` |
| `decision_source` | TEXT | `attributes.source` | Who made the decision (user/auto) |
| `success` | TEXT | `attributes.success` | Tool execution result: `true`/`false` |
| `host_name` | TEXT | `resource.host.name` | Host machine name |
| `os_type` | TEXT | `resource.os.type` | Operating system type |
| `service_version` | TEXT | `resource.service.version` | Claude Code version |
| `raw_message` | TEXT | `logEvent.message` | Full raw JSON message (for debugging) |
| `ingested_at` | TEXT | Auto-generated | Ingestion timestamp (`datetime('now')`) |

**Indexes** (for fast analytical queries):
- `idx_event_name` → `event_name` — filters by event type
- `idx_session_id` → `session_id` — session-level aggregations
- `idx_user_id` → `user_id` — user-level queries
- `idx_user_practice` → `user_practice` — practice breakdowns
- `idx_model` → `model` — model comparisons
- `idx_timestamp` → `timestamp` — time-series ordering

### Table: `user_metadata` (100 rows)

| Column | Type | Description |
|--------|------|-------------|
| `email` | TEXT (PK) | Employee email (JOIN key to `events.user_email`) |
| `full_name` | TEXT | Full name |
| `practice` | TEXT | Engineering practice |
| `level` | TEXT | Seniority level (L1–L10) |
| `location` | TEXT | Office location |

---

## 📦 Module-by-Module Code Walkthrough

### `src/ingest.py` — Data Ingestion Pipeline (304 lines)

**Purpose:** Reads raw data files and populates the SQLite database.

**Key Components:**
| Component | Description |
|-----------|-------------|
| `SCHEMA_SQL` | DDL string — creates `events` table with 27 columns + 6 indexes |
| `init_db(conn)` | Executes `SCHEMA_SQL` via `executescript()` |
| `parse_log_event(raw_event)` | Extracts `message` JSON string from a logEvent, flattens `attributes` + `resource` dicts into a single dict; normalizes event names (strips `claude_code.` prefix); returns `None` on any parse error |
| `_int(v)` / `_float(v)` | Safe type converters — return `None` instead of raising on bad input |
| `INSERT_SQL` | Parameterized INSERT OR IGNORE statement for all 27 columns |
| `ingest_jsonl(jsonl_path, db_path, limit)` | Main ingestion function — opens file, iterates lines, validates `messageType`, parses events, buffers in chunks of 1,000, flushes via `executemany`, returns summary dict |
| `ingest_csv(csv_path, db_path)` | Creates `user_metadata` table, reads CSV with `DictReader`, INSERT OR REPLACE each row |
| `__main__` block | CLI with argparse: `--jsonl` (required), `--csv`, `--db`, `--limit` |

**Error Handling:**
- `json.JSONDecodeError` on outer JSONL line → logs warning, increments `skipped`, continues
- `Exception` in `parse_log_event` → logs warning with event ID, returns `None`
- `_int()` / `_float()` → catches `ValueError`/`TypeError`, returns `None`
- Missing fields → `dict.get()` returns `None` (stored as SQL NULL)

---

### `src/analytics.py` — SQL Analytics & Advanced Statistics (568 lines)

**Purpose:** 20+ analytical functions that query SQLite and return DataFrames/dicts.

| Function | Returns | Description |
|----------|---------|-------------|
| `kpi_summary()` | `dict` | Aggregate KPIs: total sessions, users, practices, cost, tokens, API calls, prompts |
| `token_usage_by_practice()` | `DataFrame` | Token breakdown (input/output/cache) + cost per engineering practice |
| `token_usage_by_model()` | `DataFrame` | Token totals, cost, avg latency per AI model |
| `cost_over_time(granularity)` | `DataFrame` | Time-series cost aggregated by hour or day |
| `session_stats()` | `DataFrame` | Per-session summary: start/end time, prompts, API calls, tool decisions, cost, tokens |
| `peak_usage_by_hour()` | `DataFrame` | Event count + cost aggregated by hour of day (0–23) |
| `peak_usage_by_weekday()` | `DataFrame` | Event count + cost aggregated by day of week |
| `tool_usage_stats()` | `DataFrame` | Per-tool: total uses, accepted, rejected, accept rate % |
| `tool_accept_by_practice()` | `DataFrame` | Tool acceptance rate broken down by practice × tool |
| `tool_result_performance()` | `DataFrame` | Per-tool execution: success count, success rate %, avg duration |
| `prompt_length_distribution()` | `DataFrame` | Avg/min/max prompt length + count per practice |
| `top_users_by_cost(limit)` | `DataFrame` | Top N users ranked by total cost with session/token/prompt counts |
| `terminal_type_distribution()` | `DataFrame` | Sessions and users per terminal/IDE type |
| `cost_by_level()` | `DataFrame` | Cost/tokens by seniority level (JOINs `user_metadata`) |
| `cost_by_location()` | `DataFrame` | Cost/users/tokens by office location (JOINs `user_metadata`) |
| `tool_acceptance_by_level()` | `DataFrame` | Tool accept rate by seniority level × tool (JOINs `user_metadata`) |
| `avg_cost_per_user_by_practice_level()` | `DataFrame` | Heatmap-ready: avg cost/user for each practice × level combo |
| `prompt_cost_correlation()` | `dict` | Pearson correlation (r, p-value) between avg prompt length and session cost; uses `scipy.stats.pearsonr` |
| `session_duration_stats()` | `dict` | Duration distribution: mean, median, std, P25/P75/P90/P95/max + histogram-ready DataFrame |
| `cost_efficiency_by_model()` | `DataFrame` | Tokens-per-dollar and cost-per-1K-tokens for each model |
| `user_engagement_clusters(n_clusters)` | `DataFrame` | K-Means clustering on user features (sessions, API calls, prompts, cost, avg prompt length); uses `StandardScaler` + `KMeans` |
| `cache_efficiency()` | `DataFrame` | Cache hit rate (cache_read_tokens / input_tokens) per practice |
| `api_error_analysis()` | `DataFrame` | Error rate per practice × model combination |

---

### `src/predict.py` — Predictive Analytics / ML (264 lines)

**Purpose:** Trend forecasting and anomaly detection using scikit-learn.

| Function | ML Model | Features | Output |
|----------|----------|----------|--------|
| `cost_forecast(forecast_days)` | `LinearRegression` | `day_num` (days since first observation) → `cost_usd` | DataFrame with `date`, `cost_usd`, `type` (actual/forecast) + R², slope metadata |
| `token_forecast(forecast_days)` | `LinearRegression` | `day_num` → `total_tokens` | DataFrame with `date`, `total_tokens`, `type` + R² metadata |
| `detect_session_anomalies(contamination)` | `IsolationForest` | `total_cost`, `total_tokens`, `api_calls`, `prompts`, `avg_prompt_len`, `duration_min` | DataFrame with `is_anomaly` (bool) + `anomaly_score` per session |
| `detect_cost_anomalies_by_user(contamination)` | `IsolationForest` | `sessions`, `total_cost`, `total_tokens`, `api_calls`, `prompts` | DataFrame with `is_anomaly` + `anomaly_score` per user |

**Edge case handling:**
- Returns empty DataFrame if fewer than 3 data points (forecasting)
- Returns all `is_anomaly=False` if fewer than 10 sessions/users (anomaly detection)
- `.clip(min=0)` prevents negative forecast values

---

### `src/dashboard.py` — Interactive Streamlit Dashboard (577 lines)

**Purpose:** 8-tab interactive dashboard with 30+ Plotly visualizations.

| Tab | Charts & Widgets |
|-----|-----------------|
| **💰 Cost & Tokens** | Bar chart: cost by practice · Stacked bar: input/output/cache tokens by practice · Line chart: cost over time · Pie chart: cost share by model · Table: model performance |
| **⏱️ Usage Patterns** | Bar chart: events by hour of day · Bar chart: events by weekday · Table: top 50 sessions by cost · Pie chart: terminal type distribution |
| **🛠️ Tool Behavior** | Bar chart: tool usage colored by accept rate · Grouped bar: accepted vs rejected per tool · Bar chart: tool success rate · Bar chart: avg tool duration · Heatmap: tool acceptance by practice |
| **👤 Users** | Bar chart: top 15 users by cost colored by practice · Table: full top-20 user ranking |
| **📝 Prompts** | Bar chart: avg prompt length by practice · Scatter: prompt count vs avg length · Table: prompt length stats |
| **🏢 Employee Insights** | Bar chart: cost by seniority level · Bar chart: avg cost/call by level · Pie chart: cost by location · Bar chart: users by location · Heatmap: practice × level avg cost · Heatmap: tool acceptance by seniority |
| **🔮 Predictions** | Line chart: cost forecast (actual vs predicted) · Metrics: R², slope · Line chart: token forecast · Scatter: session anomaly map (cost vs tokens, red = anomaly) · Metrics: total/anomalies/% · Bar chart: anomalous users by cost · Table: flagged sessions/users |
| **📊 Advanced Stats** | Metrics: Pearson r, p-value, interpretation · Histogram + boxplot: session duration distribution · Bar charts: tokens/$ and $/1K-tokens per model · Scatter: K-Means user clusters · Table: cluster summary · Bar chart: cache hit rate by practice · Grouped bar: API error rate by practice × model |

**Interactive Controls:**
- Sidebar: DB path input, time granularity selector (hour/day)
- Tab 7: Forecast horizon slider (3–30 days), anomaly sensitivity slider (0.01–0.20)
- Tab 8: Number of clusters slider (2–8)

---

### `src/api.py` — FastAPI REST API (210 lines)

**Purpose:** 18 REST endpoints exposing all analytics and predictions as JSON.

| Endpoint | Query Params | Response |
|----------|-------------|----------|
| `GET /api/kpi` | — | `{total_sessions, total_users, ...}` |
| `GET /api/tokens/by-practice` | — | `[{user_practice, api_calls, input_tokens, ...}]` |
| `GET /api/tokens/by-model` | — | `[{model, api_calls, total_tokens, ...}]` |
| `GET /api/cost/over-time` | `granularity=hour\|day` | `[{period, cost_usd, total_tokens, api_calls}]` |
| `GET /api/sessions` | `limit=1..5000` | `[{session_id, user_practice, ...}]` |
| `GET /api/usage/by-hour` | — | `[{hour_of_day, event_count, cost_usd}]` |
| `GET /api/usage/by-weekday` | — | `[{weekday, event_count, cost_usd}]` |
| `GET /api/usage/terminal-types` | — | `[{terminal_type, sessions, users}]` |
| `GET /api/tools/usage` | — | `[{tool_name, total_uses, accepted, rejected, accept_rate_pct}]` |
| `GET /api/tools/acceptance-by-practice` | — | `[{user_practice, tool_name, uses, accept_rate_pct}]` |
| `GET /api/tools/performance` | — | `[{tool_name, executions, successes, success_rate_pct, avg_duration_ms}]` |
| `GET /api/users/top` | `limit=1..200` | `[{user_email, user_practice, sessions, total_cost_usd, ...}]` |
| `GET /api/users/prompts` | — | `[{user_practice, avg_prompt_length, ...}]` |
| `GET /api/employees/cost-by-level` | — | `[{level, sessions, users, total_cost_usd, ...}]` |
| `GET /api/employees/cost-by-location` | — | `[{location, users, total_cost_usd, ...}]` |
| `GET /api/employees/tool-acceptance-by-level` | — | `[{level, tool_name, uses, accept_rate_pct}]` |
| `GET /api/employees/cost-heatmap` | — | `[{practice, level, avg_cost_per_user}]` |
| `GET /api/predictions/cost-forecast` | `days=1..90` | `{meta: {r2, slope_per_day}, data: [...]}` |
| `GET /api/predictions/token-forecast` | `days=1..90` | `{meta: {r2}, data: [...]}` |
| `GET /api/predictions/session-anomalies` | `contamination=0.01..0.5` | `[{session_id, is_anomaly, anomaly_score, ...}]` |
| `GET /api/predictions/user-anomalies` | `contamination=0.01..0.5` | `[{user_email, is_anomaly, anomaly_score, ...}]` |

---

### `src/stream_simulator.py` — Real-time Streaming Simulator (131 lines)

**Purpose:** Replays JSONL events into SQLite with configurable timing to simulate live data ingestion.

**How it works:**
1. Opens JSONL file and reads line-by-line (same parser as `ingest.py`)
2. Assigns fresh unique IDs (`stream_{n}_{random}`) to avoid dedup by `INSERT OR IGNORE`
3. Buffers events in configurable batch sizes
4. Inserts each batch with a `time.sleep(batch_size / speed)` delay
5. Logs each batch insertion with event count and latest event type
6. Dashboard reflects new data on next page refresh

**CLI Arguments:** `--jsonl` (required), `--db`, `--speed` (events/sec, default 10), `--batch` (default 5), `--max` (default 500)

---

## ✨ Features

### Core Requirements ✅

| Requirement | Implementation |
|-------------|---------------|
| **Data Processing** | `ingest.py` — stream-parses JSONL + CSV; chunked writes; type-safe parsing; `INSERT OR IGNORE` dedup |
| **Analytics & Insights** | `analytics.py` — 20+ SQL analytics functions: token trends by practice, peak hours/weekdays, tool behavior, prompt patterns, employee-enriched breakdowns |
| **Visualization** | `dashboard.py` — 8-tab Streamlit dashboard with 30+ interactive Plotly charts, KPI cards, heatmaps, scatter plots, histograms |
| **Technical Implementation** | Error handling throughout (try/except, graceful empty-data handling); data validation (`_int`/`_float` converters, `messageType` check); clean layered architecture (ingest → analytics → predict → dashboard/api) |

### Bonus Features ✅

| Bonus | Implementation |
|-------|---------------|
| **🔮 Predictive Analytics** | `predict.py` — `LinearRegression` cost/token forecasting with R² metric; `IsolationForest` anomaly detection at session and user level |
| **🔴 Real-time Capabilities** | `stream_simulator.py` — configurable-speed event replay into SQLite; demonstrates live ingestion with batched inserts and timing delays |
| **📊 Advanced Statistical Analysis** | `analytics.py` — `scipy.stats.pearsonr` prompt–cost correlation; session duration percentile distribution; `KMeans` user engagement clustering with `StandardScaler`; cache hit-rate analysis; model cost-efficiency ratios; API error rate analysis |
| **🌐 API Access** | `api.py` — 18 FastAPI GET endpoints with query parameter validation, CORS, Swagger auto-docs at `/docs` |

---

## 📚 Dependencies

All dependencies are listed in `requirements.txt`:

| Package | Version | Purpose in This Project |
|---------|---------|------------------------|
| **streamlit** | ≥ 1.35.0 | Interactive dashboard framework — renders the 8-tab UI with widgets, metrics, and Plotly charts |
| **plotly** | ≥ 5.22.0 | Charting library — bar charts, line charts, pie charts, scatter plots, heatmaps, histograms with box marginals |
| **pandas** | ≥ 2.2.0 | Data manipulation — `read_sql_query()` for all analytics functions; DataFrame operations for pivot tables, groupby, aggregation |
| **numpy** | ≥ 1.26.0 | Numerical operations — `np.where()` for conditional columns, `np.arange()` for forecast day sequences, `np.round()` for score rounding |
| **scikit-learn** | ≥ 1.4.0 | Machine learning — `LinearRegression` (forecasting), `IsolationForest` (anomaly detection), `KMeans` (user clustering), `StandardScaler` (feature normalization) |
| **scipy** | ≥ 1.12.0 | Statistics — `scipy.stats.pearsonr` for prompt-length → cost correlation analysis |
| **fastapi** | ≥ 0.111.0 | REST API framework — 18 endpoints with auto-generated Swagger docs, query parameter validation, CORS middleware |
| **uvicorn** | ≥ 0.29.0 | ASGI server — runs the FastAPI application (`uvicorn src.api:app`) |

**Standard library modules used** (no install needed):
`json`, `sqlite3`, `csv`, `logging`, `pathlib`, `argparse`, `time`, `random`, `sys`

---

## 🚀 Setup Instructions

### Prerequisites

- **Python 3.11+** installed and available as `python` on PATH
- **pip** (comes with Python)
- **Git** (for cloning)

### Step 1: Clone the Repository

```bash
git clone <repo-url>
cd "Provectus Task"
```

### Step 2: Create a Virtual Environment (Recommended)

```bash
# Windows (PowerShell)
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs: `streamlit`, `plotly`, `pandas`, `numpy`, `scikit-learn`, `scipy`, `fastapi`, `uvicorn`.

### Step 4: Ingest the Data

```bash
# Ingest BOTH telemetry logs AND employee metadata into SQLite
python src/ingest.py --jsonl DataEntry/telemetry_logs.jsonl --csv DataEntry/employees.csv
```

**What this does:**
- Creates `db/telemetry.db` (SQLite database)
- Stream-parses `telemetry_logs.jsonl` → inserts ~454K events into the `events` table
- Reads `employees.csv` → inserts 100 rows into the `user_metadata` table
- Prints a JSON summary with `lines_processed`, `events_inserted`, `events_skipped`

**Expected output:**
```
2025-xx-xx [INFO] Database schema initialized.
2025-xx-xx [INFO] Starting ingestion: DataEntry/telemetry_logs.jsonl
2025-xx-xx [INFO]   Processed 1000 lines / XXXX events...
...
2025-xx-xx [INFO] Ingestion complete: {"lines_processed": XXXX, "events_inserted": 454428, ...}
2025-xx-xx [INFO] CSV ingestion complete: 100 rows inserted.
```

**Optional flags:**
```bash
# Test with a small subset first
python src/ingest.py --jsonl DataEntry/telemetry_logs.jsonl --limit 100

# Use a custom database path
python src/ingest.py --jsonl DataEntry/telemetry_logs.jsonl --db my_custom.db
```

### Step 5: Launch the Dashboard

```bash
streamlit run src/dashboard.py
```

Opens automatically at **http://localhost:8501**

The dashboard reads from `db/telemetry.db` (configurable in the sidebar). All 8 tabs should display data immediately.

### Step 6: Launch the API Server (Optional)

```bash
uvicorn src.api:app --reload --port 8000
```

- API available at **http://localhost:8000**
- Swagger documentation at **http://localhost:8000/docs**
- ReDoc documentation at **http://localhost:8000/redoc**

### Step 7: Simulate Real-time Streaming (Optional)

```bash
# Stream 500 events at 10 events/sec
python src/stream_simulator.py --jsonl DataEntry/telemetry_logs.jsonl --speed 10 --max 500

# Higher speed demo (50 events/sec, 1000 events)
python src/stream_simulator.py --jsonl DataEntry/telemetry_logs.jsonl --speed 50 --max 1000
```

The dashboard will reflect newly streamed data on the next page refresh.

---

## 📁 Project Structure

```
Provectus Task/
├── README.md                      ← This file
├── requirements.txt               ← Python dependencies (8 packages)
├── .gitignore                     ← Excludes db/, DataEntry/, __pycache__/
│
├── DataEntry/                     ← Raw input data
│   ├── telemetry_logs.jsonl       ← 454K+ telemetry events (JSONL)
│   └── employees.csv             ← 100 engineer records (CSV)
│
├── db/                            ← Generated database (git-ignored)
│   └── telemetry.db              ← SQLite database (~80MB)
│
└── src/                           ← Source code
    ├── ingest.py                 ← Data ingestion pipeline         (304 lines)
    ├── analytics.py              ← SQL analytics + advanced stats  (568 lines)
    ├── predict.py                ← ML predictions (forecast + anomaly) (264 lines)
    ├── dashboard.py              ← Streamlit interactive dashboard (577 lines)
    ├── api.py                    ← FastAPI REST endpoints          (210 lines)
    └── stream_simulator.py       ← Real-time streaming simulator   (131 lines)
                                                          Total: ~2,054 lines
```

---

## 🖥️ Usage

### Dashboard Tabs

| Tab | Description |
|-----|-------------|
| **💰 Cost & Tokens** | Cost by practice, token distribution (input/output/cache), cost over time, model cost share, model performance table |
| **⏱️ Usage Patterns** | Activity by hour of day, activity by weekday, top 50 sessions by cost, terminal type pie chart |
| **🛠️ Tool Behavior** | Tool usage with acceptance rate color-coding, accept vs reject grouped bars, tool success rates, avg duration, practice × tool heatmap |
| **👤 Users** | Top 15 users bar chart, full top-20 table with sessions/cost/tokens/prompts |
| **📝 Prompts** | Avg prompt length by practice, prompt count vs length scatter, full stats table |
| **🏢 Employee Insights** | Cost by seniority level, avg cost/call by level, cost by location (pie + bar), practice × level heatmap, tool acceptance by seniority heatmap |
| **🔮 Predictions** | Cost forecast line chart with R²/slope metrics, token forecast, session anomaly scatter map with stats, user anomaly bar chart, flagged anomaly tables |
| **📊 Advanced Stats** | Pearson correlation metrics, session duration histogram with box marginal, model efficiency (tokens/$ and $/1K-tokens), K-Means cluster scatter + summary table, cache hit rate bars, API error rate grouped bars |

### CLI Reference

```bash
# ─── Data Ingestion ───────────────────────────────────────────────
# Full ingestion (telemetry + employees)
python src/ingest.py --jsonl DataEntry/telemetry_logs.jsonl --csv DataEntry/employees.csv

# Telemetry only (no employee enrichment)
python src/ingest.py --jsonl DataEntry/telemetry_logs.jsonl

# Test with limited rows
python src/ingest.py --jsonl DataEntry/telemetry_logs.jsonl --limit 1000

# Custom database path
python src/ingest.py --jsonl DataEntry/telemetry_logs.jsonl --db custom/path.db

# ─── Dashboard ────────────────────────────────────────────────────
streamlit run src/dashboard.py

# ─── API Server ───────────────────────────────────────────────────
uvicorn src.api:app --reload --port 8000

# ─── Streaming Simulator ─────────────────────────────────────────
python src/stream_simulator.py --jsonl DataEntry/telemetry_logs.jsonl --speed 10 --max 500
python src/stream_simulator.py --jsonl DataEntry/telemetry_logs.jsonl --speed 50 --batch 10 --max 1000
```

---

## 🌐 API Documentation

Once the API server is running (`uvicorn src.api:app --reload`), full interactive documentation is available:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### All Endpoints

| Method | Endpoint | Query Params | Description |
|--------|----------|-------------|-------------|
| GET | `/api/kpi` | — | High-level KPI summary |
| GET | `/api/tokens/by-practice` | — | Token usage by engineering practice |
| GET | `/api/tokens/by-model` | — | Token usage by AI model |
| GET | `/api/cost/over-time` | `granularity=hour\|day` | Cost trend over time |
| GET | `/api/sessions` | `limit=1..5000` | Session statistics |
| GET | `/api/usage/by-hour` | — | Peak usage by hour of day |
| GET | `/api/usage/by-weekday` | — | Peak usage by day of week |
| GET | `/api/usage/terminal-types` | — | Terminal type distribution |
| GET | `/api/tools/usage` | — | Tool usage & acceptance rates |
| GET | `/api/tools/acceptance-by-practice` | — | Tool acceptance by practice |
| GET | `/api/tools/performance` | — | Tool execution performance |
| GET | `/api/users/top` | `limit=1..200` | Top users by cost |
| GET | `/api/users/prompts` | — | Prompt length statistics |
| GET | `/api/employees/cost-by-level` | — | Cost breakdown by seniority |
| GET | `/api/employees/cost-by-location` | — | Cost breakdown by location |
| GET | `/api/employees/tool-acceptance-by-level` | — | Tool acceptance by seniority |
| GET | `/api/employees/cost-heatmap` | — | Practice × Level cost heatmap |
| GET | `/api/predictions/cost-forecast` | `days=1..90` | Cost forecast (Linear Regression) |
| GET | `/api/predictions/token-forecast` | `days=1..90` | Token forecast |
| GET | `/api/predictions/session-anomalies` | `contamination=0.01..0.5` | Anomalous sessions (Isolation Forest) |
| GET | `/api/predictions/user-anomalies` | `contamination=0.01..0.5` | Anomalous users |

### Example Usage

```bash
# Get high-level KPIs
curl http://localhost:8000/api/kpi

# Get cost trend by day
curl "http://localhost:8000/api/cost/over-time?granularity=day"

# Get top 10 users by cost
curl "http://localhost:8000/api/users/top?limit=10"

# Get 14-day cost forecast
curl "http://localhost:8000/api/predictions/cost-forecast?days=14"

# Detect anomalous sessions (10% sensitivity)
curl "http://localhost:8000/api/predictions/session-anomalies?contamination=0.10"
```

### Example Response

```bash
curl http://localhost:8000/api/kpi
```

```json
{
  "total_sessions": 5000,
  "total_users": 100,
  "total_practices": 6,
  "total_cost_usd": 6001.43,
  "total_tokens": 103279101,
  "total_api_calls": 125432,
  "total_prompts": 34521
}
```

---

## 📊 Key Insights & Findings

Based on the analysis of **454,428 telemetry events** across **5,000 sessions** from **100 engineers**:

### 1. Cost Distribution by Practice
- ML Engineering ($1,475) and Frontend Engineering ($1,473) are the highest-spending practices
- Platform Engineering ($693) spends roughly 2× less — likely simpler or shorter code generation tasks

### 2. Model Usage & Efficiency
- Claude Haiku handles 39% of all API calls at just $186 total — delivering ~285K tokens per dollar
- Claude Opus models are ~47× more expensive per token but handle complex tasks (6K–10K tokens/$)
- Clear tiered strategy: cheap models for routine work, premium models for heavy lifting

### 3. Peak Usage Patterns
- Activity concentrates during business hours — top hours: 17:00 (43,927 events), 16:00 (42,403), 11:00 (42,083 UTC)
- Usage is relatively stable across weekdays and weekends, suggesting flexible work schedules

### 4. Tool Behavior
- Read (46K uses) and Bash (43K uses) are the most-used tools by a wide margin
- Tool acceptance rates are uniformly high across all tools (~97.7–98.3%), indicating strong trust in Claude's suggestions

### 5. Session Characteristics
- Median session: ~7 minutes; P95: ~59 minutes (long tail of intensive sessions)
- Mean of 15.5 minutes pulled up by power sessions
- ~5% of sessions (250/5,000) flagged as anomalous by Isolation Forest

### 6. User Engagement Archetypes (K-Means)
- **Power Users** — high sessions, high cost, frequent API calls
- **Moderate Users** — regular usage with balanced cost
- **Light Users** — occasional sessions, low cost footprint
- **High-Cost Specialists** — few sessions but expensive tasks (complex prompts)

---

## 🤖 LLM Usage Log

### Tools Used
- **GitHub Copilot** (in JetBrains IDE) — primary development assistant for code generation, refactoring, and documentation
- **Claude** (Anthropic) — architecture planning, complex SQL query design, statistical analysis approach

### Example Prompts & How They Helped

1. **Prompt:** *"Design a SQLite schema for flattened telemetry events from Claude Code sessions, optimized for analytics queries on cost, tokens, sessions, and tools"*
   - **Result:** Generated the `events` table schema with 27 columns and 6 indexes
   - **Validation:** Tested with sample data; verified query performance with `EXPLAIN QUERY PLAN`

2. **Prompt:** *"Create an Isolation Forest anomaly detection pipeline for session-level telemetry data with features: cost, tokens, api_calls, prompts, duration"*
   - **Result:** Generated the `detect_session_anomalies` function with configurable contamination
   - **Validation:** Verified anomaly scores distribution; cross-checked flagged sessions against raw data

3. **Prompt:** *"Build a Streamlit dashboard with Plotly charts for telemetry analytics, including KPI cards, cost over time, tool acceptance heatmaps"*
   - **Result:** Generated the 8-tab dashboard structure with 30+ charts
   - **Validation:** Ran dashboard with real data; verified all charts render correctly and are interactive

4. **Prompt:** *"Create FastAPI endpoints that expose pandas DataFrame results as JSON from analytics functions"*
   - **Result:** Generated 18 API endpoints with proper type hints and query parameters
   - **Validation:** Tested all endpoints via Swagger UI; verified JSON output structure

### Validation Approach
- **Functional testing:** Ran each analytics function independently against the ingested database
- **Visual verification:** Every chart was inspected with real data for correctness
- **Edge cases:** Tested with empty datasets, missing fields, and malformed JSON lines
- **Cross-validation:** Compared SQL query results with equivalent pandas operations

---

