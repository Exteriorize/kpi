import io
import zipfile
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="KPI Dashboard", page_icon="📊", layout="wide")

DATA_PATH = Path(__file__).parent / "data" / "real_kpi_history.csv"

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


def fmt_money(v: float) -> str:
    return f"{v:,.0f} ₽".replace(",", " ")


def fmt_num(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def pct_delta(curr: float, prev: float) -> float:
    if prev == 0:
        return 0.0
    return (curr - prev) / prev * 100


def metric_card(title: str, value: str, delta: float | None = None, subtitle: str | None = None):
    delta_html = ""
    if delta is not None:
        symbol = "▲" if delta >= 0 else "▼"
        color = "#34d399" if delta >= 0 else "#f87171"
        delta_html = f"<div style='margin-top:6px;color:{color};font-size:0.95rem'>{symbol} {delta:.1f}% к предыдущему дню</div>"
    subtitle_html = ""
    if subtitle:
        subtitle_html = f"<div style='margin-top:6px;color:#9ca3af;font-size:0.88rem'>{subtitle}</div>"
    st.markdown(
        f"<div class='metric-card'><div style='color:#9ca3af;font-size:0.95rem'>{title}</div><div style='font-size:1.8rem;font-weight:700;margin-top:6px'>{value}</div>{delta_html}{subtitle_html}</div>",
        unsafe_allow_html=True,
    )


def city_from_store(store: str) -> str:
    parts = str(store).split("_")
    return parts[1] if len(parts) > 1 else "UNK"


def parse_daily_sheet(file_obj, file_name: str) -> pd.DataFrame:
    raw = pd.read_excel(file_obj, sheet_name="Продажи вчера", header=0)
    columns = list(raw.columns)
    raw = raw.rename(
        columns={
            columns[1]: "store",
            "Продажи - руб": "daily_revenue",
            "Средний чек, руб": "avg_check",
            "Трафик": "traffic",
            "Конвертация (%) Offline": "conversion",
            "Продажи МаржаФактическая(%)\n без НДС": "margin_pct",
            "ВаловаяПрибыль - руб \nбез НДС": "gross_profit",
            "Доля СБП от эквайринга": "sbp_share",
        }
    )
    keep = ["store", "daily_revenue", "avg_check", "traffic", "conversion", "margin_pct", "gross_profit", "sbp_share"]
    raw = raw[keep].copy()
    raw = raw[raw["store"].notna()].copy()
    raw = raw[raw["store"].astype(str).str.startswith(("RSTR_", "RSMX_"))].copy()
    file_date = pd.to_datetime(Path(file_name).stem, dayfirst=True, errors="coerce")
    if pd.isna(file_date):
        raise ValueError(f"Не удалось распознать дату из имени файла: {file_name}")
    raw["date"] = file_date - pd.Timedelta(days=1)
    raw["city"] = raw["store"].map(city_from_store)
    raw["checks"] = np.where(raw["avg_check"] > 0, raw["daily_revenue"] / raw["avg_check"], 0).round().astype(int)
    return raw


def parse_month_sheet(file_obj, file_name: str) -> pd.DataFrame:
    raw = pd.read_excel(file_obj, sheet_name="СВОД", header=None)
    sub = raw.iloc[5:, [0, 1, 2, 3, 4, 5, 8, 9, 10, 11]].copy()
    sub.columns = ["store", "mtd_revenue", "mtd_traffic", "mtd_conversion", "mtd_avg_check", "mtd_margin_pct", "acc_share", "svc_share", "sp_share", "mtd_sbp_share"]
    sub = sub[sub["store"].notna()].copy()
    sub = sub[sub["store"].astype(str).str.startswith(("RSTR_", "RSMX_"))].copy()
    sub["snapshot_date"] = pd.to_datetime(Path(file_name).stem, dayfirst=True, errors="coerce")
    return sub


def parse_plan_sheet(file_obj, file_name: str) -> pd.DataFrame:
    raw = pd.read_excel(file_obj, sheet_name="План.Факт.Прогноз Restore", header=None)
    sub = raw.iloc[5:, [1, 2, 3, 4, 5]].copy()
    sub.columns = ["store", "month_plan", "month_fact", "month_forecast", "forecast_pct"]
    sub = sub[sub["store"].notna()].copy()
    sub = sub[sub["store"].astype(str).str.startswith(("RSTR_", "RSMX_"))].copy()
    sub["snapshot_date"] = pd.to_datetime(Path(file_name).stem, dayfirst=True, errors="coerce")
    return sub


def parse_archive(uploaded_file) -> pd.DataFrame:
    with zipfile.ZipFile(uploaded_file) as zf:
        names = [name for name in zf.namelist() if name.lower().endswith(".xlsx") and "__macosx" not in name.lower()]
        daily_frames = []
        mtd_frames = []
        plan_frames = []
        for name in names:
            data = zf.read(name)
            daily_frames.append(parse_daily_sheet(io.BytesIO(data), Path(name).name))
            mtd_frames.append(parse_month_sheet(io.BytesIO(data), Path(name).name))
            plan_frames.append(parse_plan_sheet(io.BytesIO(data), Path(name).name))
    daily = pd.concat(daily_frames, ignore_index=True)
    daily["file_date"] = daily["date"] + pd.Timedelta(days=1)
    mtd = pd.concat(mtd_frames, ignore_index=True)
    plan = pd.concat(plan_frames, ignore_index=True)
    merged = daily.merge(mtd, left_on=["store", "file_date"], right_on=["store", "snapshot_date"], how="left")
    merged = merged.merge(plan, on=["store", "snapshot_date"], how="left")
    merged = merged.drop(columns=["file_date", "snapshot_date"])
    return merged.sort_values(["date", "store"]).reset_index(drop=True)


def load_default_data() -> pd.DataFrame:
    if DATA_PATH.exists():
        df = pd.read_csv(DATA_PATH)
        df["date"] = pd.to_datetime(df["date"])
        if "city_code" in df.columns and "city" not in df.columns:
            df["city"] = df["city_code"]
        return df
    raise FileNotFoundError("Файл data/real_kpi_history.csv не найден. Загрузи ZIP-архив в боковой панели.")


def load_data(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return load_default_data()

    name = uploaded_file.name.lower()
    if name.endswith(".zip"):
        return parse_archive(uploaded_file)
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "city_code" in df.columns and "city" not in df.columns:
            df["city"] = df["city_code"]
        return df
    raise ValueError("Загрузи ZIP-архив с ежедневными KPI-файлами или подготовленный CSV.")


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
        store_rev = latest.loc[latest["store"] == base_store, "daily_revenue"]
        if store_rev.empty:
            return [base_store]
        target = float(store_rev.iloc[0])
        lower = target * (1 - turnover_pct / 100)
        upper = target * (1 + turnover_pct / 100)
        matched = latest[(latest["daily_revenue"] >= lower) & (latest["daily_revenue"] <= upper)]["store"].tolist()
        return sorted(set(matched + [base_store]))
    return []


st.title("KPI Dashboard")
st.caption("Реальные KPI из ежедневных файлов: сравнение магазинов, продажи за вчера, месячный факт и современная аналитика.")

with st.sidebar:
    st.header("Источник данных")
    uploaded_file = st.file_uploader("Загрузить ZIP-архив с датированными KPI-файлами", type=["zip", "csv"])
    st.markdown(
        "<div class='small-note'>Можно загрузить архив с файлами по датам. Если архив не загружен, приложение попробует открыть встроенный CSV.</div>",
        unsafe_allow_html=True,
    )

try:
    df = load_data(uploaded_file)
except Exception as e:
    st.error(f"Ошибка чтения данных: {e}")
    st.stop()

numeric_cols = [
    "daily_revenue", "checks", "avg_check", "traffic", "conversion", "gross_profit", "margin_pct",
    "sbp_share", "mtd_revenue", "mtd_traffic", "mtd_conversion", "mtd_avg_check", "mtd_margin_pct",
    "acc_share", "svc_share", "sp_share", "month_plan", "month_fact", "month_forecast", "forecast_pct"
]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

df["date"] = pd.to_datetime(df["date"]).dt.normalize()
df["city"] = df["city"].fillna("UNK")
df["store"] = df["store"].astype(str)

all_dates = sorted(df["date"].dropna().unique())
min_date, max_date = pd.Timestamp(min(all_dates)), pd.Timestamp(max(all_dates))

with st.sidebar:
    date_range = st.date_input(
        "Период",
        value=(min_date.date(), max_date.date()),
        min_value=min_date.date(),
        max_value=max_date.date(),
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    else:
        start_date = end_date = max_date

filtered = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy()

with st.sidebar:
    city_options = ["Все города"] + sorted(filtered["city"].dropna().unique().tolist())
    city = st.selectbox("Город / код города", city_options)

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
    manual_default = store_options[: min(4, len(store_options))]
    manual_selection = st.multiselect("Магазины для ручного сравнения", store_options, default=manual_default)

selected_stores = get_store_group(filtered, compare_mode, base_store, city, manual_selection, turnover_pct)
analysis_df = filtered[filtered["store"].isin(selected_stores)].copy()

if analysis_df.empty:
    st.warning("Не удалось подобрать магазины для сравнения.")
    st.stop()

latest_date = analysis_df["date"].max()
prev_date = latest_date - pd.Timedelta(days=1)
week_date = latest_date - pd.Timedelta(days=7)

latest_df = analysis_df[analysis_df["date"] == latest_date].copy()
prev_df = analysis_df[analysis_df["date"] == prev_date].copy()
week_df = analysis_df[analysis_df["date"] == week_date].copy()

current_revenue = latest_df["daily_revenue"].sum()
prev_revenue = prev_df["daily_revenue"].sum()
week_revenue = week_df["daily_revenue"].sum()
current_checks = latest_df["checks"].sum()
prev_checks = prev_df["checks"].sum()
current_avg = latest_df["avg_check"].replace(0, np.nan).mean()
prev_avg = prev_df["avg_check"].replace(0, np.nan).mean()
current_conv = latest_df["conversion"].mean()
prev_conv = prev_df["conversion"].mean()
current_mtd = latest_df["mtd_revenue"].sum()
current_plan = latest_df["month_plan"].sum()
plan_completion = current_mtd / current_plan * 100 if current_plan else 0
current_margin = latest_df["margin_pct"].mean() * 100
current_sbp = latest_df["sbp_share"].mean() * 100

col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    metric_card("Продажи за день", fmt_money(current_revenue), pct_delta(current_revenue, prev_revenue))
with col2:
    metric_card("Чеки", fmt_num(current_checks), pct_delta(current_checks, prev_checks))
with col3:
    metric_card("Средний чек", fmt_money(current_avg), pct_delta(current_avg, prev_avg))
with col4:
    metric_card("Конверсия", f"{current_conv * 100:.1f}%", pct_delta(current_conv, prev_conv))
with col5:
    metric_card("Факт МТД", fmt_money(current_mtd), subtitle=f"План {fmt_money(current_plan)}")
with col6:
    metric_card("Выполнение плана", f"{plan_completion:.1f}%", subtitle=f"Маржа {current_margin:.1f}% · СБП {current_sbp:.1f}%")

st.markdown("### Сводка по последнему дню")
t1, t2, t3, t4 = st.columns(4)
with t1:
    st.info(f"Последний день в данных: **{latest_date.strftime('%d.%m.%Y')}**")
with t2:
    st.info(f"К предыдущему дню: **{pct_delta(current_revenue, prev_revenue):.1f}%**")
with t3:
    st.info(f"К неделе назад: **{pct_delta(current_revenue, week_revenue):.1f}%**")
with t4:
    best = latest_df.sort_values("daily_revenue", ascending=False).head(1)
    if not best.empty:
        st.info(f"Лидер дня: **{best.iloc[0]['store']}**")

left, right = st.columns((1.65, 1))
with left:
    st.markdown("### Динамика продаж по дням")
    trend_df = analysis_df.groupby(["date", "store"], as_index=False)[["daily_revenue", "checks"]].sum()
    fig = px.line(trend_df, x="date", y="daily_revenue", color="store", markers=True)
    fig.update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.markdown("### Структура MTD")
    structure = pd.DataFrame(
        {
            "Категория": ["Аксессуары", "Услуги", "СП"],
            "Доля": [latest_df["acc_share"].mean(), latest_df["svc_share"].mean(), latest_df["sp_share"].mean()],
        }
    )
    fig2 = px.pie(structure, names="Категория", values="Доля", hole=0.55)
    fig2.update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig2, use_container_width=True)

row2a, row2b = st.columns(2)
with row2a:
    st.markdown("### Сравнение магазинов по дневным продажам")
    latest_sorted = latest_df.sort_values("daily_revenue", ascending=True)
    fig3 = px.bar(latest_sorted, x="daily_revenue", y="store", color="city", orientation="h")
    fig3.update_layout(height=430, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig3, use_container_width=True)

with row2b:
    st.markdown("### Оборот / средний чек / конверсия")
    fig4 = px.scatter(
        latest_df,
        x="avg_check",
        y="conversion",
        size="daily_revenue",
        color="city",
        hover_name="store",
        size_max=45,
    )
    fig4.update_layout(height=430, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig4, use_container_width=True)

row3a, row3b = st.columns(2)
with row3a:
    st.markdown("### Динамика чеков")
    fig5 = px.area(trend_df, x="date", y="checks", color="store")
    fig5.update_layout(height=390, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig5, use_container_width=True)

with row3b:
    st.markdown("### Факт MTD против плана")
    compare_mtd = latest_df.sort_values("mtd_revenue", ascending=False).copy()
    compare_mtd = compare_mtd[["store", "mtd_revenue", "month_plan"]]
    melt = compare_mtd.melt(id_vars="store", var_name="metric", value_name="value")
    fig6 = px.bar(melt, x="store", y="value", color="metric", barmode="group")
    fig6.update_layout(height=390, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig6, use_container_width=True)

st.markdown("### Таблица сравнения")
comparison = latest_df[["city", "store", "daily_revenue", "checks", "avg_check", "traffic", "conversion", "margin_pct", "sbp_share", "mtd_revenue", "month_plan"]].copy()
comparison["plan_completion_%"] = np.where(comparison["month_plan"] > 0, comparison["mtd_revenue"] / comparison["month_plan"] * 100, 0)
comparison["conversion"] = comparison["conversion"] * 100
comparison["margin_pct"] = comparison["margin_pct"] * 100
comparison["sbp_share"] = comparison["sbp_share"] * 100
comparison = comparison.sort_values("daily_revenue", ascending=False).rename(
    columns={
        "city": "Город",
        "store": "Магазин",
        "daily_revenue": "Продажи за день",
        "checks": "Чеки",
        "avg_check": "Средний чек",
        "traffic": "Трафик",
        "conversion": "Конверсия %",
        "margin_pct": "Маржа %",
        "sbp_share": "СБП %",
        "mtd_revenue": "Факт МТД",
        "month_plan": "План месяца",
        "plan_completion_%": "Выполнение плана %",
    }
)
st.dataframe(comparison, use_container_width=True, hide_index=True)

st.markdown("### Инсайты")
c1, c2, c3 = st.columns(3)
leader = latest_df.sort_values("daily_revenue", ascending=False).head(1)
lagger = latest_df.sort_values("daily_revenue", ascending=True).head(1)
best_conv = latest_df.sort_values("conversion", ascending=False).head(1)
with c1:
    if not leader.empty:
        st.success(f"Лидер по дневным продажам — **{leader.iloc[0]['store']}** ({fmt_money(leader.iloc[0]['daily_revenue'])})")
with c2:
    if not lagger.empty:
        st.warning(f"Самый слабый день — **{lagger.iloc[0]['store']}** ({fmt_money(lagger.iloc[0]['daily_revenue'])})")
with c3:
    if not best_conv.empty:
        st.info(f"Лучшая конверсия — **{best_conv.iloc[0]['store']}** ({best_conv.iloc[0]['conversion'] * 100:.1f}%)")

st.caption("Дашборд умеет читать ZIP-архив с ежедневными файлами по датам и автоматически собирать историю KPI.")
