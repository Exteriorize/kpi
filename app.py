import io
from datetime import datetime, timedelta
from typing import List

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title='KPI Dashboard', page_icon='📊', layout='wide')

# ---------- Styling ----------
st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg, #0b1020 0%, #111827 100%); }
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1500px; }
    h1,h2,h3 { letter-spacing: -0.02em; }
    .metric-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 14px 16px;
        backdrop-filter: blur(8px);
        box-shadow: 0 10px 30px rgba(0,0,0,0.18);
    }
    .small-note { color: #9ca3af; font-size: 0.92rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Demo data ----------
def build_demo_data() -> pd.DataFrame:
    np.random.seed(42)
    cities = {
        "Новосибирск": ["Restore Галерея", "Restore Аура", "Restore Ройял Парк", "Restore Мега"],
        "Красноярск": ["Restore Планета", "Restore Июнь", "Restore Комсомолл"],
        "Томск": ["Restore Изумрудный", "Restore Лето"],
    }

    end_date = pd.Timestamp.today().normalize()
    dates = pd.date_range(end=end_date, periods=28, freq="D")
    rows = []

    for city, stores in cities.items():
        for i, store in enumerate(stores, start=1):
            base = 900_000 + i * 180_000 + (120_000 if city == "Новосибирск" else 0)
            for d in dates:
                revenue = max(250_000, np.random.normal(base, base * 0.12))
                checks = max(35, int(np.random.normal(95 + i * 6, 12)))
                avg_check = revenue / checks
                conversion = min(22.0, max(4.0, np.random.normal(10.5 + i * 0.45, 1.2)))
                services = revenue * np.random.uniform(0.12, 0.24)
                accessories = revenue * np.random.uniform(0.16, 0.30)
                warranty = revenue * np.random.uniform(0.04, 0.11)
                plan = base * np.random.uniform(0.95, 1.08)
                rows.append(
                    {
                        "date": d,
                        "city": city,
                        "store": store,
                        "revenue": round(revenue, 0),
                        "checks": checks,
                        "avg_check": round(avg_check, 0),
                        "conversion": round(conversion, 2),
                        "services": round(services, 0),
                        "accessories": round(accessories, 0),
                        "warranty": round(warranty, 0),
                        "plan": round(plan, 0),
                    }
                )
    df = pd.DataFrame(rows)
    return df


# ---------- Parsing ----------
ALIASES = {
    "date": ["date", "дата", "day"],
    "city": ["city", "город"],
    "store": ["store", "shop", "магазин", "торговая точка"],
    "revenue": ["revenue", "sales", "выручка", "оборот", "продажи"],
    "checks": ["checks", "receipts", "чеки", "количество чеков"],
    "avg_check": ["avg_check", "average check", "средний чек"],
    "conversion": ["conversion", "конверсия"],
    "services": ["services", "услуги", "сервисы"],
    "accessories": ["accessories", "аксессуары"],
    "warranty": ["warranty", "гарантия", "спгарантия", "сп/гарантия"],
    "plan": ["plan", "план"],
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    original = {c: str(c).strip() for c in df.columns}
    lowered = {c: str(c).strip().lower() for c in df.columns}
    rename_map = {}
    for target, variants in ALIASES.items():
        for col, low in lowered.items():
            if low == target or low in variants:
                rename_map[col] = target
                break
    df = df.rename(columns=rename_map).copy()
    return df


def parse_uploaded_file(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return build_demo_data()

    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        excel = pd.ExcelFile(uploaded_file)
        df = pd.read_excel(excel, sheet_name=excel.sheet_names[0])

    df = normalize_columns(df)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        raise ValueError("В файле не найдена колонка с датой.")

    if "store" not in df.columns:
        raise ValueError("В файле не найдена колонка с магазином.")

    if "city" not in df.columns:
        df["city"] = "Не указан"

    numeric_cols = ["revenue", "checks", "avg_check", "conversion", "services", "accessories", "warranty", "plan"]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = df.dropna(subset=["date"]).copy()
    df["date"] = df["date"].dt.normalize()
    return df


# ---------- Helpers ----------
def fmt_money(v: float) -> str:
    return f"{v:,.0f} ₽".replace(",", " ")


def fmt_num(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def pct_delta(curr: float, prev: float) -> float:
    if prev == 0:
        return 0.0
    return (curr - prev) / prev * 100


def kpi_card(title: str, value: str, delta: float | None = None):
    delta_text = ""
    if delta is not None:
        symbol = "▲" if delta >= 0 else "▼"
        color = "#34d399" if delta >= 0 else "#f87171"
        delta_text = f"<div style='margin-top:6px;color:{color};font-size:0.95rem'>{symbol} {delta:.1f}% к прошлому дню</div>"
    st.markdown(
        f"<div class='metric-card'><div style='color:#9ca3af;font-size:0.95rem'>{title}</div><div style='font-size:1.8rem;font-weight:700;margin-top:6px'>{value}</div>{delta_text}</div>",
        unsafe_allow_html=True,
    )


def get_store_group(df: pd.DataFrame, mode: str, base_store: str | None, city: str, manual: List[str], turnover_pct: int) -> List[str]:
    city_df = df if city == "Все города" else df[df["city"] == city]
    latest = city_df[city_df["date"] == city_df["date"].max()].copy()
    if latest.empty:
        return []
    if mode == "Один магазин":
        return [base_store] if base_store else []
    if mode == "Все магазины города":
        return sorted(latest["store"].unique().tolist())
    if mode == "Ручной выбор":
        return manual
    if mode == "Похожий оборот" and base_store:
        store_rev = latest.loc[latest["store"] == base_store, "revenue"]
        if store_rev.empty:
            return [base_store]
        target = float(store_rev.iloc[0])
        lower = target * (1 - turnover_pct / 100)
        upper = target * (1 + turnover_pct / 100)
        matched = latest[(latest["revenue"] >= lower) & (latest["revenue"] <= upper)]["store"].tolist()
        return sorted(set(matched + [base_store]))
    return []


# ---------- App ----------
st.title("KPI Dashboard")
st.caption("Сравнение магазинов, динамика, продажи за вчера и современная визуальная аналитика")

with st.sidebar:
    st.header("Фильтры")
    uploaded_file = st.file_uploader("Загрузить KPI-файл", type=["xlsx", "xls", "csv"])
    st.markdown("<div class='small-note'>Если файл не загружен, используются демонстрационные данные.</div>", unsafe_allow_html=True)

try:
    df = parse_uploaded_file(uploaded_file)
except Exception as e:
    st.error(f"Ошибка чтения файла: {e}")
    st.stop()

all_dates = sorted(df["date"].dropna().unique())
min_date, max_date = pd.Timestamp(min(all_dates)), pd.Timestamp(max(all_dates))

with st.sidebar:
    date_range = st.date_input("Период", value=(min_date.date(), max_date.date()), min_value=min_date.date(), max_value=max_date.date())
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    else:
        start_date = end_date = max_date

    cities = ["Все города"] + sorted(df["city"].dropna().unique().tolist())
    city = st.selectbox("Город", cities)

filtered = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy()
if city != "Все города":
    filtered = filtered[filtered["city"] == city]

store_options = sorted(filtered["store"].dropna().unique().tolist())
if not store_options:
    st.warning("Нет данных по выбранным фильтрам.")
    st.stop()

with st.sidebar:
    base_store = st.selectbox("Базовый магазин", store_options)
    compare_mode = st.radio(
        "Режим сравнения",
        ["Один магазин", "Все магазины города", "Похожий оборот", "Ручной выбор"],
    )
    turnover_pct = st.slider("Диапазон похожего оборота ±%", 5, 30, 10, 1)
    manual_selection = st.multiselect("Магазины для ручного сравнения", store_options, default=store_options[: min(3, len(store_options))])

selected_stores = get_store_group(filtered, compare_mode, base_store, city, manual_selection, turnover_pct)
analysis_df = filtered[filtered["store"] .isin(selected_stores)].copy()

if analysis_df.empty:
    st.warning("Не удалось подобрать магазины для сравнения.")
    st.stop()

latest_date = analysis_df["date"].max()
prev_date = latest_date - pd.Timedelta(days=1)
week_date = latest_date - pd.Timedelta(days=7)

latest_df = analysis_df[analysis_df["date"] == latest_date].copy()
prev_df = analysis_df[analysis_df["date"] == prev_date].copy()
week_df = analysis_df[analysis_df["date"] == week_date].copy()

current_revenue = latest_df["revenue"].sum()
prev_revenue = prev_df["revenue"].sum()
week_revenue = week_df["revenue"].sum()
current_checks = latest_df["checks"].sum()
prev_checks = prev_df["checks"].sum()
current_avg = latest_df["avg_check"].mean()
prev_avg = prev_df["avg_check"].mean()
current_conv = latest_df["conversion"].mean()
prev_conv = prev_df["conversion"].mean()
current_plan = latest_df["plan"].sum()
plan_completion = (current_revenue / current_plan * 100) if current_plan else 0

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    kpi_card("Выручка", fmt_money(current_revenue), pct_delta(current_revenue, prev_revenue))
with col2:
    kpi_card("Чеки", fmt_num(current_checks), pct_delta(current_checks, prev_checks))
with col3:
    kpi_card("Средний чек", fmt_money(current_avg), pct_delta(current_avg, prev_avg))
with col4:
    kpi_card("Конверсия", f"{current_conv:.1f}%", pct_delta(current_conv, prev_conv))
with col5:
    kpi_card("Выполнение плана", f"{plan_completion:.1f}%")

st.markdown("### Вчера / тренд")
trend1, trend2, trend3, trend4 = st.columns(4)
with trend1:
    st.info(f"Продажи за {latest_date.strftime('%d.%m.%Y')}: **{fmt_money(current_revenue)}**")
with trend2:
    st.info(f"К предыдущему дню: **{pct_delta(current_revenue, prev_revenue):.1f}%**")
with trend3:
    st.info(f"К прошлой неделе: **{pct_delta(current_revenue, week_revenue):.1f}%**")
with trend4:
    best = latest_df.sort_values("revenue", ascending=False).head(1)
    if not best.empty:
        st.info(f"Лидер дня: **{best.iloc[0]['store']}**")

left, right = st.columns((1.6, 1))
with left:
    st.markdown("### Динамика продаж")
    daily = (
        analysis_df.groupby(["date", "store"], as_index=False)[["revenue", "plan", "checks", "avg_check"]].sum()
    )
    fig = px.line(daily, x="date", y="revenue", color="store", markers=True)
    fig.update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.markdown("### Структура продаж")
    structure = pd.DataFrame(
        {
            "Категория": ["Услуги", "Аксессуары", "Гарантия"],
            "Сумма": [latest_df["services"].sum(), latest_df["accessories"].sum(), latest_df["warranty"].sum()],
        }
    )
    fig2 = px.pie(structure, names="Категория", values="Сумма", hole=0.55)
    fig2.update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig2, use_container_width=True)

row2a, row2b = st.columns(2)
with row2a:
    st.markdown("### Сравнение магазинов по выручке")
    latest_sorted = latest_df.sort_values("revenue", ascending=True)
    fig3 = px.bar(latest_sorted, x="revenue", y="store", color="city", orientation="h")
    fig3.update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig3, use_container_width=True)

with row2b:
    st.markdown("### Оборот / средний чек / конверсия")
    fig4 = px.scatter(
        latest_df,
        x="avg_check",
        y="conversion",
        size="revenue",
        color="city",
        hover_name="store",
        size_max=45,
    )
    fig4.update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig4, use_container_width=True)

row3a, row3b = st.columns(2)
with row3a:
    st.markdown("### Динамика чеков")
    checks_daily = analysis_df.groupby(["date", "store"], as_index=False)["checks"].sum()
    fig5 = px.area(checks_daily, x="date", y="checks", color="store")
    fig5.update_layout(height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig5, use_container_width=True)

with row3b:
    st.markdown("### Доля категорий по магазинам")
    melt_df = latest_df[["store", "services", "accessories", "warranty"]].melt(id_vars="store", var_name="category", value_name="value")
    fig6 = px.bar(melt_df, x="store", y="value", color="category")
    fig6.update_layout(height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig6, use_container_width=True)

st.markdown("### Таблица сравнения")
comparison = latest_df[["city", "store", "revenue", "checks", "avg_check", "conversion", "services", "accessories", "warranty", "plan"]].copy()
comparison["plan_completion_%"] = np.where(comparison["plan"] > 0, comparison["revenue"] / comparison["plan"] * 100, 0)
comparison = comparison.sort_values("revenue", ascending=False)
comparison = comparison.rename(
    columns={
        "city": "Город",
        "store": "Магазин",
        "revenue": "Выручка",
        "checks": "Чеки",
        "avg_check": "Средний чек",
        "conversion": "Конверсия %",
        "services": "Услуги",
        "accessories": "Аксессуары",
        "warranty": "Гарантия",
        "plan": "План",
        "plan_completion_%": "Выполнение плана %",
    }
)
st.dataframe(comparison, use_container_width=True, hide_index=True)

st.markdown("### Инсайты")
insight_cols = st.columns(3)
leader = latest_df.sort_values("revenue", ascending=False).head(1)
lagger = latest_df.sort_values("revenue", ascending=True).head(1)
best_conv = latest_df.sort_values("conversion", ascending=False).head(1)
with insight_cols[0]:
    if not leader.empty:
        st.success(f"Лидер по выручке — **{leader.iloc[0]['store']}** ({fmt_money(leader.iloc[0]['revenue'])})")
with insight_cols[1]:
    if not lagger.empty:
        st.warning(f"Самая слабая выручка — **{lagger.iloc[0]['store']}** ({fmt_money(lagger.iloc[0]['revenue'])})")
with insight_cols[2]:
    if not best_conv.empty:
        st.info(f"Лучшая конверсия — **{best_conv.iloc[0]['store']}** ({best_conv.iloc[0]['conversion']:.1f}%)")

st.caption("Следующий шаг: подогнать распознавание колонок точно под ваш реальный KPI-файл и добавить больше бизнес-метрик из вашей выгрузки.")
