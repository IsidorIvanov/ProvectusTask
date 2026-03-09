

import sys
from pathlib import Path

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Allow running from project root
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
    prompt_cost_correlation,
    session_duration_stats,
    cost_efficiency_by_model,
    user_engagement_clusters,
    cache_efficiency,
    api_error_analysis,
)
from predict import (
    cost_forecast,
    token_forecast,
    detect_session_anomalies,
    detect_cost_anomalies_by_user,
)

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Claude Code Analytics",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── DB path ──────────────────────────────────────────────────────────────────
DEFAULT_DB = Path(__file__).parent.parent / "db" / "telemetry.db"

with st.sidebar:
    st.image("https://www.anthropic.com/favicon.ico", width=32)
    st.title("⚙️ Settings")
    db_path = st.text_input("DB Path", value=str(DEFAULT_DB))

    if not Path(db_path).exists():
        st.error("Database not found. Run ingest.py first.")
        st.stop()

    st.success("✅ Database connected")
    st.divider()
    granularity = st.selectbox("Time granularity", ["hour", "day"], index=1)
    st.divider()
    st.caption("Claude Code Analytics Platform v1.0")

# ─── Header ───────────────────────────────────────────────────────────────────
st.title("🤖 Claude Code Usage Analytics")
st.caption("End-to-end telemetry analytics for developer behavior insights")

# ─── KPI Cards ────────────────────────────────────────────────────────────────
kpi = kpi_summary(db_path)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Sessions",   f"{kpi['total_sessions']:,}")
col2.metric("Total Users",      f"{kpi['total_users']:,}")
col3.metric("API Calls",        f"{kpi['total_api_calls']:,}")
col4.metric("Total Cost",       f"${kpi['total_cost_usd']:,.2f}")
col5.metric("Total Tokens",     f"{kpi['total_tokens']:,}")

st.divider()

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "💰 Cost & Tokens",
    "⏱️ Usage Patterns",
    "🛠️ Tool Behavior",
    "👤 Users",
    "📝 Prompts",
    "🏢 Employee Insights",
    "🔮 Predictions",
    "📊 Advanced Stats",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – Cost & Tokens
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Cost by Engineering Practice")
        df_practice = token_usage_by_practice(db_path)
        if not df_practice.empty:
            fig = px.bar(
                df_practice,
                x="user_practice",
                y="total_cost_usd",
                color="user_practice",
                text_auto=".3f",
                labels={"total_cost_usd": "Cost (USD)", "user_practice": "Practice"},
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available.")

    with col_right:
        st.subheader("Token Distribution by Practice")
        if not df_practice.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(name="Input", x=df_practice["user_practice"], y=df_practice["input_tokens"]))
            fig2.add_trace(go.Bar(name="Output", x=df_practice["user_practice"], y=df_practice["output_tokens"]))
            fig2.add_trace(go.Bar(name="Cache Read", x=df_practice["user_practice"], y=df_practice["cache_read_tokens"]))
            fig2.update_layout(barmode="stack", xaxis_title="Practice", yaxis_title="Tokens")
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Cost Over Time")
    df_time = cost_over_time(db_path, granularity=granularity)
    if not df_time.empty:
        fig3 = px.line(
            df_time, x="period", y="cost_usd",
            title=f"Daily Cost Trend (granularity: {granularity})",
            labels={"period": "Time", "cost_usd": "Cost (USD)"},
            markers=True,
        )
        st.plotly_chart(fig3, use_container_width=True)

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        st.subheader("Model Usage & Cost")
        df_model = token_usage_by_model(db_path)
        if not df_model.empty:
            fig4 = px.pie(df_model, names="model", values="total_cost_usd", title="Cost Share by Model")
            st.plotly_chart(fig4, use_container_width=True)

    with col_r2:
        st.subheader("Model Performance")
        if not df_model.empty:
            st.dataframe(
                df_model.rename(columns={
                    "model": "Model",
                    "api_calls": "API Calls",
                    "total_tokens": "Total Tokens",
                    "total_cost_usd": "Cost (USD)",
                    "avg_duration_ms": "Avg Latency (ms)",
                }),
                use_container_width=True,
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – Usage Patterns
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Activity by Hour of Day")
        df_hour = peak_usage_by_hour(db_path)
        if not df_hour.empty:
            fig = px.bar(
                df_hour, x="hour_of_day", y="event_count",
                labels={"hour_of_day": "Hour (UTC)", "event_count": "Events"},
                color="event_count",
                color_continuous_scale="Blues",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Activity by Day of Week")
        df_week = peak_usage_by_weekday(db_path)
        if not df_week.empty:
            fig2 = px.bar(
                df_week, x="weekday", y="event_count",
                labels={"weekday": "Day", "event_count": "Events"},
                color="cost_usd",
                color_continuous_scale="Oranges",
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Session Overview (Top 50 by cost)")
    df_sess = session_stats(db_path).head(50)
    if not df_sess.empty:
        st.dataframe(df_sess, use_container_width=True)

    st.subheader("Terminal Type Distribution")
    df_term = terminal_type_distribution(db_path)
    if not df_term.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            fig3 = px.pie(df_term, names="terminal_type", values="sessions", title="Sessions by Terminal")
            st.plotly_chart(fig3, use_container_width=True)
        with col_b:
            st.dataframe(df_term, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – Tool Behavior
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Tool Usage & Acceptance Rates")
    df_tool = tool_usage_stats(db_path)
    if not df_tool.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(
                df_tool, x="tool_name", y="total_uses",
                color="accept_rate_pct",
                color_continuous_scale="RdYlGn",
                text_auto=True,
                labels={"tool_name": "Tool", "total_uses": "Uses", "accept_rate_pct": "Accept Rate (%)"},
            )
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(name="Accepted", x=df_tool["tool_name"], y=df_tool["accepted"], marker_color="green"))
            fig2.add_trace(go.Bar(name="Rejected", x=df_tool["tool_name"], y=df_tool["rejected"], marker_color="red"))
            fig2.update_layout(barmode="group", title="Accept vs Reject per Tool")
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Tool Execution Performance")
    df_perf = tool_result_performance(db_path)
    if not df_perf.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            fig3 = px.bar(
                df_perf, x="tool_name", y="success_rate_pct",
                color="success_rate_pct",
                color_continuous_scale="Greens",
                range_y=[0, 100],
                labels={"success_rate_pct": "Success Rate (%)", "tool_name": "Tool"},
            )
            st.plotly_chart(fig3, use_container_width=True)
        with col_b:
            fig4 = px.bar(
                df_perf, x="tool_name", y="avg_duration_ms",
                labels={"avg_duration_ms": "Avg Duration (ms)", "tool_name": "Tool"},
                color="avg_duration_ms", color_continuous_scale="Reds",
            )
            st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Tool Acceptance by Practice")
    df_tap = tool_accept_by_practice(db_path)
    if not df_tap.empty:
        fig5 = px.density_heatmap(
            df_tap, x="tool_name", y="user_practice", z="accept_rate_pct",
            color_continuous_scale="RdYlGn",
            labels={"accept_rate_pct": "Accept Rate (%)"},
        )
        st.plotly_chart(fig5, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 – Users
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Top Users by Cost")
    df_users = top_users_by_cost(db_path)
    if not df_users.empty:
        fig = px.bar(
            df_users.head(15), x="user_email", y="total_cost_usd",
            color="user_practice",
            labels={"user_email": "User", "total_cost_usd": "Cost (USD)"},
        )
        fig.update_xaxes(tickangle=45)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_users, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 – Prompts
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("Prompt Length by Practice")
    df_prompts = prompt_length_distribution(db_path)
    if not df_prompts.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(
                df_prompts, x="user_practice", y="avg_prompt_length",
                error_y=None,
                color="avg_prompt_length",
                color_continuous_scale="Purples",
                labels={"avg_prompt_length": "Avg Prompt Length (chars)", "user_practice": "Practice"},
            )
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig2 = px.scatter(
                df_prompts, x="prompt_count", y="avg_prompt_length",
                size="prompt_count",
                color="user_practice",
                hover_name="user_practice",
                labels={"prompt_count": "Number of Prompts", "avg_prompt_length": "Avg Length"},
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.dataframe(df_prompts, use_container_width=True)
    else:
        st.info("No prompt data available.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 – Employee Insights (CSV enrichment)
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("Cost by Seniority Level")
    df_level = cost_by_level(db_path)
    if not df_level.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(
                df_level, x="level", y="total_cost_usd",
                color="total_cost_usd", color_continuous_scale="Blues",
                text_auto=".3f",
                labels={"level": "Seniority Level", "total_cost_usd": "Total Cost (USD)"},
            )
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig2 = px.bar(
                df_level, x="level", y="avg_cost_per_call",
                color="avg_cost_per_call", color_continuous_scale="Oranges",
                text_auto=".5f",
                labels={"level": "Seniority Level", "avg_cost_per_call": "Avg Cost per API Call (USD)"},
                title="Avg Cost per Call – Senior vs Junior",
            )
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No data – make sure employees.csv is ingested and emails match.")

    st.subheader("Cost & Usage by Location")
    df_loc = cost_by_location(db_path)
    if not df_loc.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            fig3 = px.pie(df_loc, names="location", values="total_cost_usd",
                          title="Cost Share by Office Location")
            st.plotly_chart(fig3, use_container_width=True)
        with col_b:
            fig4 = px.bar(df_loc, x="location", y="users",
                          color="api_calls", color_continuous_scale="Teal",
                          labels={"location": "Location", "users": "Active Users"},
                          title="Active Users per Location")
            st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Avg Cost per User – Practice × Level Heatmap")
    df_heat = avg_cost_per_user_by_practice_level(db_path)
    if not df_heat.empty:
        df_pivot = df_heat.pivot(index="practice", columns="level", values="avg_cost_per_user").fillna(0)
        fig5 = px.imshow(
            df_pivot,
            color_continuous_scale="YlOrRd",
            labels={"color": "Avg Cost/User (USD)"},
            title="Which practice × level combination spends most?",
            aspect="auto",
        )
        st.plotly_chart(fig5, use_container_width=True)

    st.subheader("Tool Acceptance Rate by Seniority")
    df_tlevel = tool_acceptance_by_level(db_path)
    if not df_tlevel.empty:
        fig6 = px.density_heatmap(
            df_tlevel, x="level", y="tool_name", z="accept_rate_pct",
            color_continuous_scale="RdYlGn",
            labels={"accept_rate_pct": "Accept Rate (%)"},
            title="Do senior engineers trust Claude's tools more?",
        )
        st.plotly_chart(fig6, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 – Predictions (ML)
# ══════════════════════════════════════════════════════════════════════════════
with tab7:
    st.subheader("📈 Cost Forecast (Linear Regression)")
    forecast_days = st.slider("Forecast horizon (days)", 3, 30, 7, key="fc_days")
    df_fc = cost_forecast(db_path, forecast_days=forecast_days)
    if not df_fc.empty:
        r2 = df_fc.attrs.get("r2", "N/A")
        slope = df_fc.attrs.get("slope_per_day", "N/A")
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Model R²", f"{r2}")
        col_m2.metric("Daily Trend (USD/day)", f"${slope}")

        fig_fc = px.line(
            df_fc, x="date", y="cost_usd", color="type",
            title="Daily Cost – Actual vs Forecast",
            labels={"date": "Date", "cost_usd": "Cost (USD)", "type": ""},
            color_discrete_map={"actual": "#636EFA", "forecast": "#EF553B"},
            markers=True,
        )
        st.plotly_chart(fig_fc, use_container_width=True)
    else:
        st.info("Not enough data for forecasting.")

    st.subheader("📈 Token Forecast")
    df_tf = token_forecast(db_path, forecast_days=forecast_days)
    if not df_tf.empty:
        fig_tf = px.line(
            df_tf, x="date", y="total_tokens", color="type",
            title="Daily Tokens – Actual vs Forecast",
            labels={"date": "Date", "total_tokens": "Tokens"},
            color_discrete_map={"actual": "#636EFA", "forecast": "#EF553B"},
            markers=True,
        )
        st.plotly_chart(fig_tf, use_container_width=True)

    st.divider()
    st.subheader("🚨 Anomaly Detection – Sessions (Isolation Forest)")
    contamination = st.slider("Anomaly sensitivity", 0.01, 0.20, 0.05, 0.01, key="anom_s")
    df_anom = detect_session_anomalies(db_path, contamination=contamination)
    anomalies = df_anom[df_anom["is_anomaly"]]
    normal = df_anom[~df_anom["is_anomaly"]]

    col_a1, col_a2, col_a3 = st.columns(3)
    col_a1.metric("Total Sessions", f"{len(df_anom):,}")
    col_a2.metric("Anomalies Detected", f"{len(anomalies):,}")
    col_a3.metric("Anomaly %", f"{100 * len(anomalies) / max(len(df_anom), 1):.1f}%")

    if not df_anom.empty:
        fig_anom = px.scatter(
            df_anom, x="total_cost", y="total_tokens",
            color="is_anomaly",
            color_discrete_map={True: "red", False: "#636EFA"},
            hover_data=["session_id", "user_email", "anomaly_score"],
            title="Session Anomaly Map (cost vs tokens)",
            labels={"total_cost": "Session Cost (USD)", "total_tokens": "Session Tokens"},
        )
        st.plotly_chart(fig_anom, use_container_width=True)

    if not anomalies.empty:
        st.write("**Flagged anomalous sessions:**")
        st.dataframe(anomalies, use_container_width=True)

    st.subheader("🚨 Anomaly Detection – Users")
    df_uanom = detect_cost_anomalies_by_user(db_path, contamination=contamination)
    user_anomalies = df_uanom[df_uanom["is_anomaly"]]
    if not user_anomalies.empty:
        fig_ua = px.bar(
            user_anomalies.sort_values("total_cost", ascending=False),
            x="user_email", y="total_cost",
            color="anomaly_score", color_continuous_scale="Reds_r",
            title="Anomalous Users by Total Cost",
            labels={"total_cost": "Total Cost (USD)", "user_email": "User"},
        )
        fig_ua.update_xaxes(tickangle=45)
        st.plotly_chart(fig_ua, use_container_width=True)
        st.dataframe(user_anomalies, use_container_width=True)
    else:
        st.success("No anomalous users detected at this sensitivity level.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 – Advanced Statistical Analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab8:
    st.subheader("🔗 Prompt Length → Cost Correlation")
    corr = prompt_cost_correlation(db_path)
    if corr["correlation"] is not None:
        col_c1, col_c2, col_c3 = st.columns(3)
        col_c1.metric("Pearson r", f"{corr['correlation']}")
        col_c2.metric("p-value", f"{corr['p_value']}")
        col_c3.metric("Interpretation", corr["interpretation"])
        st.caption(f"Based on {corr['n']} sessions with both prompts and API costs.")
    else:
        st.info("Not enough data for correlation analysis.")

    st.divider()
    st.subheader("⏳ Session Duration Distribution")
    dur = session_duration_stats(db_path)
    if dur["stats"]:
        s = dur["stats"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mean (min)", f"{s['mean']}")
        c2.metric("Median (min)", f"{s['median']}")
        c3.metric("P90 (min)", f"{s['p90']}")
        c4.metric("P95 (min)", f"{s['p95']}")

        df_dur = dur["data"]
        fig_dur = px.histogram(
            df_dur, x="duration_min", nbins=50,
            color="user_practice",
            title="Session Duration Distribution",
            labels={"duration_min": "Duration (minutes)"},
            marginal="box",
        )
        st.plotly_chart(fig_dur, use_container_width=True)

    st.divider()
    st.subheader("⚡ Model Cost Efficiency")
    df_eff = cost_efficiency_by_model(db_path)
    if not df_eff.empty:
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            fig_eff = px.bar(
                df_eff, x="model", y="tokens_per_dollar",
                color="tokens_per_dollar", color_continuous_scale="Greens",
                text_auto=True,
                title="Tokens per Dollar (higher = cheaper)",
                labels={"tokens_per_dollar": "Tokens/$", "model": "Model"},
            )
            st.plotly_chart(fig_eff, use_container_width=True)
        with col_e2:
            fig_cpt = px.bar(
                df_eff, x="model", y="cost_per_1k_tokens",
                color="cost_per_1k_tokens", color_continuous_scale="Reds",
                text_auto=".5f",
                title="Cost per 1K Tokens (lower = cheaper)",
                labels={"cost_per_1k_tokens": "$/1K tokens", "model": "Model"},
            )
            st.plotly_chart(fig_cpt, use_container_width=True)
        st.dataframe(df_eff, use_container_width=True)

    st.divider()
    st.subheader("🎯 User Engagement Clusters (K-Means)")
    n_clusters = st.slider("Number of clusters", 2, 8, 4, key="n_cl")
    df_clusters = user_engagement_clusters(db_path, n_clusters=n_clusters)
    if not df_clusters.empty:
        fig_cl = px.scatter(
            df_clusters, x="total_cost", y="api_calls",
            color="cluster", symbol="user_practice",
            size="prompts",
            hover_data=["user_email", "sessions"],
            title="User Engagement Clusters",
            labels={"total_cost": "Total Cost (USD)", "api_calls": "API Calls"},
            color_continuous_scale="Viridis",
        )
        st.plotly_chart(fig_cl, use_container_width=True)

        # Cluster summary
        cluster_summary = df_clusters.groupby("cluster").agg(
            users=("user_email", "count"),
            avg_cost=("total_cost", "mean"),
            avg_sessions=("sessions", "mean"),
            avg_api_calls=("api_calls", "mean"),
            avg_prompts=("prompts", "mean"),
        ).round(2)
        st.write("**Cluster Summary:**")
        st.dataframe(cluster_summary, use_container_width=True)

    st.divider()
    st.subheader("💾 Cache Efficiency by Practice")
    df_cache = cache_efficiency(db_path)
    if not df_cache.empty:
        fig_cache = px.bar(
            df_cache, x="user_practice", y="cache_hit_rate_pct",
            color="cache_hit_rate_pct", color_continuous_scale="Greens",
            text_auto=".1f",
            title="Cache Hit Rate by Practice (%)",
            labels={"cache_hit_rate_pct": "Cache Hit Rate (%)", "user_practice": "Practice"},
        )
        st.plotly_chart(fig_cache, use_container_width=True)
        st.dataframe(df_cache, use_container_width=True)

    st.divider()
    st.subheader("❌ API Error Rate Analysis")
    df_err = api_error_analysis(db_path)
    if not df_err.empty:
        fig_err = px.bar(
            df_err, x="user_practice", y="error_rate_pct",
            color="model", barmode="group",
            title="API Error Rate by Practice & Model",
            labels={"error_rate_pct": "Error Rate (%)", "user_practice": "Practice"},
        )
        st.plotly_chart(fig_err, use_container_width=True)
        st.dataframe(df_err, use_container_width=True)
    else:
        st.info("No significant error data available.")

