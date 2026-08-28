"""Payer / value-based-care decision dashboard.

Built for a stakeholder, not a data scientist: no AUC/F1/SHAP-beeswarm on the
main views. Every number is dollars, member counts, or plain-language driver
names. The underlying model performance metrics still exist -- they live in
the notebooks and the README -- this app answers "who needs attention, how
much does it matter, and does the model actually help."

Reads pre-computed artifacts from data/processed/ (produced by notebooks
03/05/06/07/08) -- this app does no model inference itself, just loads and
displays results, so it runs instantly with no model/feature dependencies.

Usage:
    python dashboard/app.py
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

# ---------------------------------------------------------------- tokens ---
# validated categorical/status/sequential palette (light mode only -- this is
# a local analytics tool, not a themeable public artifact)
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
GRIDLINE = "#e1e0d9"
STATUS = {"low": "#0ca30c", "medium": "#fab219", "high": "#ec835a", "very_high": "#d03b3b"}
STRATEGY_COLOR = {"random": INK_MUTED, "prior_year_spend": ORANGE, "ml_risk_score": BLUE}
STRATEGY_LABEL = {
    "random": "Random selection",
    "prior_year_spend": "Prior-year spend (no model)",
    "ml_risk_score": "ML risk score",
}
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"

FEATURE_LABELS = {
    "inpatient_admits": "Prior-year hospital admissions",
    "outpatient_visits": "Prior-year outpatient visits",
    "carrier_claims": "Prior-year specialist/physician visits",
    "inpatient_paid": "Prior-year hospital spending",
    "outpatient_paid": "Prior-year outpatient spending",
    "carrier_paid": "Prior-year physician/specialist spending",
    "has_alzheimers": "Alzheimer's / dementia",
    "has_chf": "Congestive heart failure",
    "has_ckd": "Chronic kidney disease",
    "has_cancer": "Cancer",
    "has_copd": "COPD",
    "has_depression": "Depression",
    "has_diabetes": "Diabetes",
    "has_ihd": "Ischemic heart disease",
    "has_osteoporosis": "Osteoporosis",
    "has_ra_oa": "Rheumatoid / osteoarthritis",
    "has_stroke_tia": "Stroke / TIA",
    "has_esrd": "End-stage renal disease",
    "age": "Age",
    "is_male": "Sex: male",
    "race_black": "Race: Black",
    "race_other": "Race: other",
    "race_hispanic": "Race: Hispanic",
    "rx_fill_count": "Prior-year prescription fills",
    "rx_total_cost": "Prior-year prescription spending",
    "rx_patient_paid": "Prior-year out-of-pocket Rx spending",
    "other_payer_paid": "Spending covered by another insurer",
}

CONDITION_COLS = [
    "has_chf", "has_diabetes", "has_ckd", "has_copd", "has_cancer",
    "has_alzheimers", "has_depression", "has_ihd", "has_osteoporosis",
    "has_ra_oa", "has_stroke_tia", "has_esrd",
]

# --------------------------------------------------------------- data load --
member_scores = pd.read_parquet(DATA_DIR / "member_risk_scores.parquet")
features = pd.read_parquet(DATA_DIR / "features_labeled.parquet")
targeting = pd.read_parquet(DATA_DIR / "targeting_comparison.parquet")
shap_values = pd.read_parquet(DATA_DIR / "xgboost_high_cost_shap_values.parquet")
monthly = pd.read_parquet(DATA_DIR / "monthly_spend.parquet")
backtest = pd.read_parquet(DATA_DIR / "backtest_total_paid.parquet")
forecast = pd.read_parquet(DATA_DIR / "forecast_total_paid.parquet")

members_df = features.merge(member_scores[["desynpuf_id", "risk_score", "risk_tier"]], on="desynpuf_id")

TOTAL_MEMBERS = len(member_scores)
HIGH_COST_RATE = member_scores["high_cost_frozen"].mean()
TOTAL_SPEND_2010 = member_scores["total_paid_2010"].sum()

top1 = targeting[targeting["capacity_pct"] == 0.01].set_index("strategy")
LIFT_VS_RANDOM_TOP1 = top1.loc["ml_risk_score", "spend_share"] / top1.loc["random", "spend_share"]

tier_spend = (
    member_scores.groupby("risk_tier", observed=True)["total_paid_2010"]
    .sum()
    .reindex(["low", "medium", "high", "very_high"])
)
TIER_LABELS = {"low": "Low risk", "medium": "Medium risk", "high": "High risk", "very_high": "Very high risk"}

global_importance = (
    shap_values.drop(columns="desynpuf_id").abs().mean().sort_values(ascending=False).head(8)
)
global_importance.index = [FEATURE_LABELS.get(c, c) for c in global_importance.index]


# ------------------------------------------------------------ chart style --
def style_fig(fig, height=340):
    fig.update_layout(
        font=dict(family=FONT, color=INK_SECONDARY, size=13),
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        margin=dict(l=10, r=10, t=30, b=10),
        height=height,
        hoverlabel=dict(bgcolor=SURFACE, font=dict(family=FONT, color=INK)),
    )
    fig.update_xaxes(gridcolor=GRIDLINE, zeroline=False, linecolor=GRIDLINE)
    fig.update_yaxes(gridcolor=GRIDLINE, zeroline=False, linecolor=GRIDLINE)
    return fig


def dollars(x):
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1_000_000:
        return f"{sign}${x / 1_000_000:,.1f}M"
    return f"{sign}${x:,.0f}"


def kpi_card(value, label, sublabel=None):
    children = [
        html.Div(value, style={"fontSize": "2.1rem", "fontWeight": 700, "color": INK}),
        html.Div(label, style={"fontSize": "0.85rem", "color": INK_SECONDARY, "marginTop": "0.2rem"}),
    ]
    if sublabel:
        children.append(html.Div(sublabel, style={"fontSize": "0.75rem", "color": INK_MUTED, "marginTop": "0.15rem"}))
    return html.Div(
        children,
        style={
            "background": SURFACE, "border": f"1px solid {GRIDLINE}", "borderRadius": "10px",
            "padding": "1.1rem 1.3rem", "flex": "1", "minWidth": "160px",
        },
    )


# ------------------------------------------------------------- page: home --
def overview_page():
    fig = go.Figure(
        go.Bar(
            x=tier_spend.values,
            y=[TIER_LABELS[t] for t in tier_spend.index],
            orientation="h",
            marker_color=[STATUS[t] for t in tier_spend.index],
            text=[dollars(v) for v in tier_spend.values],
            textposition="outside",
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    fig.update_layout(title="2010 spend by risk tier")
    style_fig(fig, height=300)

    return html.Div(
        [
            html.Div(
                [
                    kpi_card(f"{TOTAL_MEMBERS:,}", "Members analyzed"),
                    kpi_card(f"{HIGH_COST_RATE:.0%}", "High-cost outcome rate", "top decile of 2010 spend"),
                    kpi_card(dollars(TOTAL_SPEND_2010), "2010 total Medicare spend", "across the analyzed cohort"),
                    kpi_card(f"{LIFT_VS_RANDOM_TOP1:.1f}x", "Spend captured, top 1% vs. random", "risk-based targeting"),
                ],
                style={"display": "flex", "gap": "1rem", "flexWrap": "wrap", "marginBottom": "1.5rem"},
            ),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
            html.P(
                f"The highest-risk 1% of members identified by the model account for "
                f"{top1.loc['ml_risk_score', 'spend_share']:.1%} of 2010 Medicare spending — "
                f"{LIFT_VS_RANDOM_TOP1:.1f}x what targeting the same number of members at "
                f"random would capture.",
                style={"fontSize": "0.95rem", "color": INK_SECONDARY, "maxWidth": "640px", "marginTop": "0.5rem"},
            ),
        ]
    )


# ------------------------------------------------------ page: targeting ----
def targeting_page():
    return html.Div(
        [
            html.Label("Care-management capacity", style={"fontWeight": 600, "color": INK}),
            dcc.RadioItems(
                id="capacity-radio",
                options=[
                    {"label": "Top 1%", "value": 0.01},
                    {"label": "Top 5%", "value": 0.05},
                    {"label": "Top 10%", "value": 0.10},
                ],
                value=0.01,
                inline=True,
                style={"margin": "0.6rem 0 1.2rem 0"},
                inputStyle={"marginRight": "0.35rem", "marginLeft": "1rem"},
            ),
            html.Div(id="targeting-kpis", style={"display": "flex", "gap": "1rem", "flexWrap": "wrap", "marginBottom": "1.2rem"}),
            dcc.Graph(id="targeting-chart", config={"displayModeBar": False}),
            html.P(
                "\"Prior-year spend\" ranks members by what they already cost in 2008-2009, "
                "with no model at all -- the simplest thing a payer could already be doing. "
                "The gap between that bar and the ML risk score is the actual return on "
                "building the model, not just on doing something instead of nothing.",
                style={"fontSize": "0.85rem", "color": INK_MUTED, "maxWidth": "640px", "marginTop": "0.8rem"},
            ),
        ]
    )


def register_targeting_callback(app):
    @app.callback(
        Output("targeting-kpis", "children"),
        Output("targeting-chart", "figure"),
        Input("capacity-radio", "value"),
    )
    def update_targeting(capacity_pct):
        subset = targeting[targeting["capacity_pct"] == capacity_pct].set_index("strategy")
        ml = subset.loc["ml_risk_score"]
        lift_random = subset.loc["ml_risk_score", "spend_share"] / subset.loc["random", "spend_share"]
        lift_prior = subset.loc["ml_risk_score", "spend_share"] / subset.loc["prior_year_spend", "spend_share"]

        kpis = [
            kpi_card(f"{int(ml['members_targeted']):,}", "Members targeted"),
            kpi_card(dollars(ml["spend_captured"]), "2010 spend captured"),
            kpi_card(f"{ml['spend_share']:.1%}", "Share of total cohort spend"),
            kpi_card(f"{lift_random:.1f}x", "Lift vs. random"),
            kpi_card(f"{lift_prior:.1f}x", "Lift vs. prior-year spend", "the number that justifies the model"),
        ]

        order = ["random", "prior_year_spend", "ml_risk_score"]
        subset = subset.reindex(order)
        fig = go.Figure(
            go.Bar(
                x=[STRATEGY_LABEL[s] for s in order],
                y=subset["spend_captured"],
                marker_color=[STRATEGY_COLOR[s] for s in order],
                text=[dollars(v) for v in subset["spend_captured"]],
                textposition="outside",
                hovertemplate="%{x}: %{text}<extra></extra>",
            )
        )
        fig.update_layout(title=f"2010 spend captured — top {capacity_pct:.0%} of members, by strategy")
        style_fig(fig)
        return kpis, fig


# ---------------------------------------------------------- page: drivers --
def drivers_page():
    fig = go.Figure(
        go.Bar(
            x=global_importance.values[::-1],
            y=global_importance.index[::-1],
            orientation="h",
            marker_color=BLUE,
            hovertemplate="%{y}<extra></extra>",
        )
    )
    fig.update_layout(title="Top drivers of predicted high-cost risk", xaxis_title="Relative influence on risk score")
    style_fig(fig, height=380)

    condition_rows = []
    for col in CONDITION_COLS:
        with_cond = members_df.loc[members_df[col] == 1, "risk_score"].mean()
        without_cond = members_df.loc[members_df[col] == 0, "risk_score"].mean()
        condition_rows.append(
            {
                "condition": FEATURE_LABELS[col],
                "avg_risk_with": with_cond,
                "avg_risk_without": without_cond,
            }
        )
    cond_df = pd.DataFrame(condition_rows).sort_values("avg_risk_with", ascending=False)

    table_rows = [
        html.Tr(
            [
                html.Td(r["condition"], style={"padding": "0.4rem 0.8rem"}),
                html.Td(f"{r['avg_risk_with']:.0%}", style={"padding": "0.4rem 0.8rem", "textAlign": "right", "fontVariantNumeric": "tabular-nums"}),
                html.Td(f"{r['avg_risk_without']:.0%}", style={"padding": "0.4rem 0.8rem", "textAlign": "right", "color": INK_MUTED, "fontVariantNumeric": "tabular-nums"}),
            ]
        )
        for _, r in cond_df.iterrows()
    ]

    return html.Div(
        [
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
            html.H4("Average predicted risk, by chronic condition", style={"marginTop": "1.8rem", "color": INK}),
            html.Table(
                [
                    html.Thead(html.Tr([html.Th("Condition"), html.Th("Members with condition"), html.Th("Members without")], style={"textAlign": "left"})),
                    html.Tbody(table_rows),
                ],
                style={"width": "100%", "maxWidth": "560px", "borderCollapse": "collapse", "fontSize": "0.9rem"},
            ),
        ]
    )


# ----------------------------------------------------------- page: trends --
def trends_page():
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[str(p) for p in monthly["year_month"]], y=monthly["total_paid"],
        mode="lines+markers", name="Actual (2008-2010)", line=dict(color=BLUE, width=2),
    ))
    fig.add_trace(go.Scatter(
        x=[str(p) for p in forecast.index], y=forecast["arima_forecast"],
        mode="lines+markers", name="ARIMA forecast (2011)", line=dict(color=ORANGE, width=2, dash="dash"),
    ))
    fig.update_layout(title="Monthly Medicare spend — actual and forward forecast", hovermode="x unified")
    style_fig(fig, height=380)

    forecast_min = forecast["arima_forecast"].min()

    return html.Div(
        [
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
            html.Div(
                [
                    html.Strong("⚠ Data quality note: ", style={"color": "#d03b3b"}),
                    html.Span(
                        "every claim type declines steadily through 2010, and the forward "
                        f"forecast goes negative by mid-2011 (as low as {dollars(forecast_min)}) "
                        "— spend cannot be negative, which is itself proof this trend is an "
                        "artifact, not real. CMS's own DE-SynPUF documentation confirms 2010 "
                        "claim volume is artificially suppressed (\"attrition from death and "
                        "some effects of disclosure treatment\"). This forecast is shown as a "
                        "demonstration of the ARIMA method, not a trustworthy prediction of "
                        "2011 spend."
                    ),
                ],
                style={
                    "background": "#fdf1ec", "border": f"1px solid {STATUS['high']}", "borderRadius": "8px",
                    "padding": "0.9rem 1.1rem", "marginTop": "1rem", "fontSize": "0.88rem",
                    "color": INK_SECONDARY, "maxWidth": "700px",
                },
            ),
        ]
    )


# ------------------------------------------------------------------- app ---
app = Dash(__name__)
app.title = "Medicare Risk & Targeting Dashboard"

app.layout = html.Div(
    [
        html.Div(
            [
                html.H2("Medicare Member Risk & Care-Management Dashboard", style={"color": INK, "marginBottom": "0.2rem"}),
                html.P(
                    "CMS DE-SynPUF Sample 1 · 2008-2009 features predicting 2010 outcomes",
                    style={"color": INK_MUTED, "marginTop": 0, "fontSize": "0.9rem"},
                ),
            ],
            style={"marginBottom": "1.2rem"},
        ),
        dcc.Tabs(
            [
                dcc.Tab(label="Executive Overview", children=[html.Div(overview_page(), style={"padding": "1.5rem 0"})]),
                dcc.Tab(label="Risk & Targeting", children=[html.Div(targeting_page(), style={"padding": "1.5rem 0"})]),
                dcc.Tab(label="What Drives Risk", children=[html.Div(drivers_page(), style={"padding": "1.5rem 0"})]),
                dcc.Tab(label="Spend Trends", children=[html.Div(trends_page(), style={"padding": "1.5rem 0"})]),
            ]
        ),
    ],
    style={
        "fontFamily": FONT, "background": PAGE, "minHeight": "100vh",
        "padding": "2rem 3rem", "color": INK,
    },
)

register_targeting_callback(app)

if __name__ == "__main__":
    app.run(debug=True)
