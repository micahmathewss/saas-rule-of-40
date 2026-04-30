import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="SaaS Rule of 40 Tracker", layout="wide")

st.title("📊 SaaS Rule of 40 & Valuation Tracker")
st.markdown("""
**The Rule of 40** is a key metric in software Private Equity and VC. A healthy SaaS company's
**Revenue Growth Rate + Free Cash Flow Margin should equal or exceed 40%**.
This dashboard tracks public B2B SaaS companies, calculates their Rule of 40, and maps it
against their EV/Revenue multiple to surface valuation premiums and disconnects.
""")

# ── SIDEBAR ──────────────────────────────────────────────────────────────────

st.sidebar.header("Configuration")

DEFAULT_TICKERS = ['SNOW', 'DDOG', 'CRM', 'CRWD', 'PANW', 'MDB', 'ZS', 'NET', 'HUBS', 'TEAM', 'WDAY', 'MNDY']

selected = st.sidebar.multiselect("Default universe", options=DEFAULT_TICKERS, default=DEFAULT_TICKERS)

custom_input = st.sidebar.text_input("Add custom tickers (comma-separated)", placeholder="e.g. BILL, GTLB, SMAR")
if custom_input:
    custom = [t.strip().upper() for t in custom_input.split(',') if t.strip()]
    tickers = list(dict.fromkeys(selected + custom))
else:
    tickers = selected

st.sidebar.markdown("---")
st.sidebar.subheader("Weighted Rule of 40")
st.sidebar.caption(
    "Standard formula weights growth and FCF equally (1.0x each). "
    "In software PE, high-growth companies often command a premium — slide right to reflect that."
)
growth_weight = st.sidebar.slider("Growth weight", min_value=0.5, max_value=1.5, value=1.0, step=0.1)
fcf_weight = round(2.0 - growth_weight, 1)
st.sidebar.markdown(f"Formula: **{growth_weight}x** Revenue Growth + **{fcf_weight}x** FCF Margin")

# ── DATA FETCHING ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)
def fetch_snapshot(tickers: tuple) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            rev_growth = info.get('revenueGrowth')
            fcf = info.get('freeCashflow', info.get('operatingCashflow'))
            revenue = info.get('totalRevenue')
            ev_rev = info.get('enterpriseToRevenue')
            if None in (rev_growth, fcf, revenue, ev_rev):
                continue
            fcf_margin = fcf / revenue
            rows.append({
                'Ticker': ticker,
                'Rev Growth (%)': round(rev_growth * 100, 1),
                'FCF Margin (%)': round(fcf_margin * 100, 1),
                'EV / Revenue': round(ev_rev, 1),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


@st.cache_data(ttl=86400)
def fetch_historical(ticker: str) -> pd.DataFrame:
    try:
        stock = yf.Ticker(ticker)
        income = stock.financials
        cashflow = stock.cash_flow
        if income.empty or cashflow.empty:
            return pd.DataFrame()

        rev_row = next((income.loc[l] for l in ['Total Revenue', 'Revenue'] if l in income.index), None)
        fcf_row = next((cashflow.loc[l] for l in ['Free Cash Flow', 'Operating Cash Flow',
                        'Total Cash From Operating Activities'] if l in cashflow.index), None)
        if rev_row is None or fcf_row is None:
            return pd.DataFrame()

        dates = rev_row.index.intersection(fcf_row.index).sort_values(ascending=False)[:4]
        rev = rev_row[dates].sort_index()
        fcf = fcf_row[dates].sort_index()

        rows = []
        for i in range(1, len(dates)):
            curr, prev = sorted(dates)[i], sorted(dates)[i - 1]
            if rev[prev] == 0 or rev[curr] == 0:
                continue
            g = (rev[curr] - rev[prev]) / abs(rev[prev])
            m = fcf[curr] / rev[curr]
            rows.append({
                'Year': curr.year,
                'Rev Growth (%)': round(g * 100, 1),
                'FCF Margin (%)': round(m * 100, 1),
                'Rule of 40 (%)': round((g + m) * 100, 1),
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()

# ── TABS ──────────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["📍 Current Snapshot", "📈 Historical Trend"])

with tab1:
    with st.spinner("Fetching live data from Yahoo Finance..."):
        df = fetch_snapshot(tuple(tickers))

    if df.empty:
        st.error("Could not fetch data. Yahoo Finance may be rate-limiting — try again shortly.")
        st.stop()

    # Apply weighting
    df['Weighted Ro40 (%)'] = (
        growth_weight * df['Rev Growth (%)'] / 100 +
        fcf_weight    * df['FCF Margin (%)'] / 100
    ) * 100
    df['Weighted Ro40 (%)'] = df['Weighted Ro40 (%)'].round(1)

    plot_col = 'Weighted Ro40 (%)' if growth_weight != 1.0 else 'Rev Growth (%)'
    x_col = 'Weighted Ro40 (%)' if growth_weight != 1.0 else 'Rule of 40 (%)'

    # Build the standard Rule of 40 for display
    df['Rule of 40 (%)'] = (df['Rev Growth (%)'] / 100 + df['FCF Margin (%)'] / 100) * 100
    df['Rule of 40 (%)'] = df['Rule of 40 (%)'].round(1)

    x_axis = 'Weighted Ro40 (%)' if growth_weight != 1.0 else 'Rule of 40 (%)'

    st.subheader("Rule of 40 vs. Valuation Multiple")
    if growth_weight != 1.0:
        st.caption(f"Showing weighted Rule of 40: {growth_weight}x Growth + {fcf_weight}x FCF Margin")

    median_x = df[x_axis].median()
    median_y = df['EV / Revenue'].median()

    fig = px.scatter(
        df,
        x=x_axis,
        y='EV / Revenue',
        text='Ticker',
        size='EV / Revenue',
        color=x_axis,
        color_continuous_scale='RdYlGn',
        trendline="ols",
        hover_data=['Rev Growth (%)', 'FCF Margin (%)'],
    )

    # Rule of 40 = 40 threshold
    fig.add_vline(x=40, line_dash="dash", line_color="gray",
                  annotation_text="Ro40 = 40%", annotation_position="top right")

    # Quadrant median lines
    fig.add_vline(x=median_x, line_dash="dot", line_color="steelblue", line_width=1)
    fig.add_hline(y=median_y, line_dash="dot", line_color="steelblue", line_width=1)

    # Quadrant labels (positioned relative to medians)
    x_lo = df[x_axis].min() - 3
    y_hi = df['EV / Revenue'].max() + 1
    quadrants = [
        (x_lo,        y_hi,       "Low Growth / High Multiple", "Value Trap",   "left",  "top"),
        (median_x+1,  y_hi,       "High Growth / High Multiple","Compounder",   "left",  "top"),
        (x_lo,        median_y+0.2,"Low Growth / Low Multiple", "Distressed",   "left",  "bottom"),
        (median_x+1,  median_y+0.2,"High Growth / Low Multiple","Undervalued",  "left",  "bottom"),
    ]
    for (x, y, label, sublabel, xanc, yanc) in quadrants:
        fig.add_annotation(
            x=x, y=y,
            text=f"<b>{label}</b><br><i style='color:gray'>{sublabel}</i>",
            showarrow=False,
            font=dict(size=9, color="gray"),
            xanchor=xanc, yanchor=yanc,
            bgcolor="rgba(255,255,255,0.6)",
        )

    fig.update_traces(textposition='top center', marker=dict(line=dict(width=1, color='DarkSlateGrey')))
    fig.update_layout(height=620, template="plotly_white", xaxis_title="Growth")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Underlying Data")
    display_cols = ['Ticker', 'Rev Growth (%)', 'FCF Margin (%)', 'Rule of 40 (%)', 'Weighted Ro40 (%)', 'EV / Revenue']
    df_sorted = df[display_cols].sort_values('Rule of 40 (%)', ascending=False).reset_index(drop=True)
    st.dataframe(df_sorted, use_container_width=True)

with tab2:
    st.subheader("3-Year Rule of 40 Trend")
    st.caption("Annual data pulled from Yahoo Finance financials. Shows how trajectory — not just the snapshot — drives valuation.")

    if df.empty:
        st.info("Load snapshot data first.")
    else:
        company = st.selectbox("Select company", options=sorted(df['Ticker'].tolist()))
        with st.spinner(f"Fetching historical data for {company}..."):
            hist = fetch_historical(company)

        if hist.empty:
            st.warning(f"Not enough historical data available for {company}.")
        else:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=hist['Year'], y=hist['Rule of 40 (%)'],
                mode='lines+markers+text',
                name='Rule of 40',
                text=hist['Rule of 40 (%)'].astype(str) + '%',
                textposition='top center',
                line=dict(color='seagreen', width=3),
                marker=dict(size=10),
            ))
            fig2.add_trace(go.Scatter(
                x=hist['Year'], y=hist['Rev Growth (%)'],
                mode='lines+markers', name='Rev Growth (%)',
                line=dict(dash='dot', color='royalblue'),
            ))
            fig2.add_trace(go.Scatter(
                x=hist['Year'], y=hist['FCF Margin (%)'],
                mode='lines+markers', name='FCF Margin (%)',
                line=dict(dash='dot', color='darkorange'),
            ))
            fig2.add_hline(y=40, line_dash="dash", line_color="gray",
                           annotation_text="Ro40 = 40%", annotation_position="right")
            fig2.update_layout(
                height=460,
                template="plotly_white",
                title=f"{company} — Rule of 40 Trajectory",
                xaxis=dict(title="Fiscal Year", tickmode='linear', dtick=1),
                yaxis_title="(%)",
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
            )
            st.plotly_chart(fig2, use_container_width=True)
            st.dataframe(hist, use_container_width=True)
