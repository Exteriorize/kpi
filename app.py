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
BRAND_LABELS = {"RSTR": "Restore", "RSMX": "Restore Mix", "SMSG": "Samsung"}

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
    if prev == 0 or pd.isna(prev):
        return 0.0
    return (curr - prev) / prev * 100


def metric_card(title: str, value: str, delta: float | None = None, subtitle: str | None = None):
    delta_html = ""
    if delta is not None:
        symbol = "▲" if delta >= 0 else "▼"
        color = "#34d399" if delta >= 0 else "#f87171"
        delta_html = f"<div style='margin-top:6px;color:{color};font-size:0.95rem'>{symbol} {delta:.1f}% к предыдущей дате</div>"
    subtitle_html = ""
    if subtitle:
        subtitle_html = f"<div style='margin-top:6px;color:#9ca3af;font-size:0.88rem'>{subtitle}</div>"
    st.markdown(
        f"<div class='metric-card'><div style='color:#9ca3af;font-size:0.95rem'>{title}</div><div style='font-size:1.8rem;font-weight:700;margin-top:6px'>{value}</div>{delta_html}{subtitle_html}</div>",
        unsafe_allow_html=True,
    )


def brand_from_store(store: str) -> str:
    return str(store).split("_")[0]


def city_from_store(store: str) -> str:
    parts = str(store).split("_")
    return parts[1] if len(parts) > 1 else "UNK"


def parse_daily_sheet(file_obj, file_name: str) -> pd.DataFrame:
    raw = pd.read_excel(file_obj, sheet_name="Продажи вчера", header=0)
    raw = raw.rename(
        columns={
            raw.columns[1]: "store",
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
    raw = raw[raw["store"].astype(str).str.startswith(("RSTR_", "RSMX_", "SMSG_"))].copy()
    raw["date"] = pd.to_datetime(Path(file_name).stem, dayfirst=True, errors="coerce")
    raw["brand"] = raw["store"].map(brand_from_store)
    raw["city"] = raw["store"].map(city_from_store)
    raw["checks"] = np.where(raw["avg_check"] > 0, raw["daily_revenue"] / raw["avg_check"], 0)
    raw["checks"] = raw["checks"].fillna(0).round().astype(int)
    return raw


def parse_mtd_sheet(file_obj, file_name: str) -> pd.DataFrame:
    raw = pd.read_excel(file_obj, sheet_name="СВОД", header=None)
    sub = raw.iloc[5:, [0, 1, 2, 3, 4, 5, 8, 9, 10, 11]].copy()
    sub.columns = ["store", "mtd_revenue", "mtd_traffic", "mtd_conversion", "mtd_avg_check", "mtd_margin_pct", "acc_share", "svc_share", "sp_share", "mtd_sbp_share"]
    sub = sub[sub["store"].notna()].copy()
    sub = sub[sub["store"].astype(str).str.startswith(("RSTR_", "RSMX_", "SMSG_"))].copy()
    sub["date"] = pd.to_datetime(Path(file_name).stem, dayfirst=True, errors="coerce")
    return sub


def parse_plan_sheet(file_obj, file_name: str, sheet_name: str) -> pd.DataFrame:
    raw = pd.read_excel(file_obj, sheet_name=sheet_name, header=None)
    sub = raw.iloc[5:, [1, 2, 3, 4, 5]].copy()
    sub.columns = ["store", "month_plan", "month_fact", "month_forecast", "forecast_pct"]
    sub = sub[sub["store"].notna()].copy()
    sub = sub[sub["store"].astype(str).str.startswith(("RSTR_", "RSMX_", "SMSG_"))].copy()
    sub["date"] = pd.to_datetime(Path(file_name).stem, dayfirst=True, errors="coerce")
    return sub


def parse_archive(uploaded_file) -> pd.DataFrame:
    with zipfile.ZipFile(uploaded_file) as zf:
        names = sorted([n for n in zf.namelist() if n.lower().endswith(".xlsx") and "__macosx" not in n.lower()])
        daily_frames = []
        mtd_frames = []
        plan_frames = []
        for name in names:
            payload = zf.read(name)
            base_name = Path(name).name
            daily_frames.append(parse_daily_sheet(io.BytesIO(payload), base_name))
            mtd_frames.append(parse_mtd_sheet(io.BytesIO(payload), base_name))
            plan_frames.append(parse_plan_sheet(io.BytesIO(payload), base_name, "План.Факт.Прогноз Restore"))
            plan_frames.append(parse_plan_sheet(io.BytesIO(payload), base_name, "План.Факт.Прогноз Samsung"))

    daily = pd.concat(daily_frames, ignore_index=True)
    mtd = pd.concat(mtd_frames, ignore_index=True)
    plans = pd.concat(plan_frames, ignore_index=True)
    df = daily.merge(mtd, on=["store", "date"], how="left").merge(plans, on=["store", "date"], how="left")
    return df.sort_values(["date", "brand", "city", "store"]).reset_index(drop=True)


def load_default_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError("Нет встроенного CSV. Загрузи ZIP-архив с файлами по датам.")
    df = pd.read_csv(DATA_PATH)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def load_data(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return load_default_data()
    if uploaded_file.name.lower().endswith(".zip"):
        return parse_archive(uploaded_file)
    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    raise ValueError("Поддерживается ZIP-архив с Excel-файлами по датам или CSV.")


def get_store_group(df: pd.DataFrame, mode: str, base_store: str | None, manual: List[str], turnover_pct: int) -> List[str]:
    latest = df[df["date"] == df["date"].max()].copy()
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
st.caption("Отдельная аналитика по Restore и Samsung, реальные даты файлов и чистая выборка магазинов по коду города.")

with st.sidebar:
    st.header("Источник данных")
    uploaded_file = st.file_uploader("Загрузить ZIP-архив с KPI-файлами по датам", type=["zip", "csv"])
    st.markdown("<div class='small-note'>Даты берутся из имени файла. Например, 14.04.2026.xlsx = дата 14.04.2026 без сдвига.</div>", unsafe_allow_html=True)

try:
    df = load_data(uploaded_file)
except Exception as e:
    st.error(f"Ошибка чтения данных: {e}")
    st.stop()

num_cols = [
    "daily_revenue", "checks", "avg_check", "traffic", "conversion", "margin_pct", "gross_profit", "sbp_share",
    "mtd_revenue", "mtd_traffic", "mtd_conversion", "mtd_avg_check", "mtd_margin_pct", "acc_share", "svc_share",
    "sp_share", "mtd_sbp_share", "month_plan", "month_fact", "month_forecast", "forecast_pct"
]
for col in num_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
df = df.dropna(subset=["date", "store"]).copy()
if "brand" not in df.columns:
    df["brand"] = df["store"].map(brand_from_store)
if "city" not in df.columns:
    df["city"] = df["store"].map(city_from_store)

all_dates = sorted(df["date"].unique())
min_date, max_date = pd.Timestamp(min(all_dates)), pd.Timestamp(max(all_dates))

with st.sidebar:
    brand_codes = sorted(df["brand"].dropna().unique().tolist())
    brand = st.selectbox("Бренд", brand_codes, format_func=lambda x: BRAND_LABELS.get(x, x))

brand_df = df[df["brand"] == brand].copy()

with st.sidebar:
    date_range = st.date_input("Период", value=(min_date.date(), max_date.date()), min_value=min_date.date(), max_value=max_date.date())
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    else:
        start_date = end_date = max_date

brand_df = brand_df[(brand_df["date"] >= start_date) & (brand_df["date"] <= end_date)].copy()

with st.sidebar:
    city_options = sorted(brand_df["city"].dropna().unique().tolist())
    city = st.selectbox("Код города", city_options)

city_df = brand_df[brand_df["city"] == city].copy()
store_options = sorted(city_df["store"].dropna().unique().tolist())
if not store_options:
    st.warning("По выбранному бренду, городу и периоду магазины не найдены.")
    st.stop()

with st.sidebar:
    base_store = st.selectbox("Базовый магазин", store_options)
    compare_mode = st.radio("Режим сравнения", ["Один магазин", "Все магазины города", "Похожий оборот", "Ручной выбор"])
    turnover_pct = st.slider("Диапазон похожего оборота ±%", 5, 30, 10, 1)
    manual_selection = st.multiselect("Магазины для ручного сравнения", store_options, default=store_options[: min(4, len(store_options))])

selected_stores = get_store_group(city_df, compare_mode, base_store, manual_selection, turnover_pct)
analysis_df = city_df[city_df["store"].isin(selected_stores)].copy()
if analysis_df.empty:
    st.warning("Не удалось подобрать магазины для сравнения.")
    st.stop()

latest_date = analysis_df["date"].max()
prev_dates = sorted([d for d in analysis_df["date"].unique() if d < latest_date])
prev_date = prev_dates[-1] if prev_dates else latest_date
week_dates = sorted([d for d in analysis_df["date"].unique() if d <= latest_date - pd.Timedelta(days=7)])
week_date = week_dates[-1] if week_dates else prev_date

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
current_conv = latest_df["conversion"].mean() * 100
prev_conv = prev_df["conversion"].mean() * 100
current_mtd = latest_df["mtd_revenue"].sum()
current_plan = latest_df["month_plan"].sum()
plan_completion = current_mtd / current_plan * 100 if current_plan else 0
current_margin = latest_df["margin_pct"].mean() * 100
current_sbp = latest_df["sbp_share"].mean() * 100

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    metric_card("Продажи за день", fmt_money(current_revenue), pct_delta(current_revenue, prev_revenue))
with c2:
    metric_card("Чеки", fmt_num(current_checks), pct_delta(current_checks, prev_checks))
with c3:
    metric_card("Средний чек", fmt_money(current_avg), pct_delta(current_avg, prev_avg))
with c4:
    metric_card("Конверсия", f"{current_conv:.1f}%", pct_delta(current_conv, prev_conv))
with c5:
    metric_card("Факт МТД", fmt_money(current_mtd), subtitle=f"План {fmt_money(current_plan)}")
with c6:
    metric_card("Выполнение плана", f"{plan_completion:.1f}%", subtitle=f"Маржа {current_margin:.1f}% · СБП {current_sbp:.1f}%")

st.markdown("### Сводка")
s1, s2, s3, s4 = st.columns(4)
with s1:
    st.info(f"Бренд: **{BRAND_LABELS.get(brand, brand)}** · Город: **{city}**")
with s2:
    st.info(f"Последняя дата в фильтре: **{latest_date.strftime('%d.%m.%Y')}**")
with s3:
    st.info(f"Сравнение к: **{prev_date.strftime('%d.%m.%Y')}**")
with s4:
    st.info(f"Магазинов в выборке: **{latest_df['store'].nunique()}**")

left, right = st.columns((1.6, 1))
with left:
    st.markdown("### Динамика продаж")
    trend_df = analysis_df.groupby(["date", "store"], as_index=False)[["daily_revenue", "checks"]].sum()
    fig = px.line(trend_df, x="date", y="daily_revenue", color="store", markers=True)
    fig.update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.markdown("### Структура MTD")
    structure = pd.DataFrame({
        "Категория": ["Аксессуары", "Услуги", "СП"],
        "Доля": [latest_df["acc_share"].mean(), latest_df["svc_share"].mean(), latest_df["sp_share"].mean()],
    })
    fig2 = px.pie(structure, names="Категория", values="Доля", hole=0.55)
    fig2.update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig2, use_container_width=True)

r2a, r2b = st.columns(2)
with r2a:
    st.markdown("### Сравнение магазинов по продажам за день")
    latest_sorted = latest_df.sort_values("daily_revenue", ascending=True)
    fig3 = px.bar(latest_sorted, x="daily_revenue", y="store", orientation="h")
    fig3.update_layout(height=430, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
    st.plotly_chart(fig3, use_container_width=True)
with r2b:
    st.markdown("### Оборот / средний чек / конверсия")
    fig4 = px.scatter(latest_df, x="avg_check", y="conversion", size="daily_revenue", hover_name="store", size_max=45)
    fig4.update_layout(height=430, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
    st.plotly_chart(fig4, use_container_width=True)

r3a, r3b = st.columns(2)
with r3a:
    st.markdown("### Динамика чеков")
    fig5 = px.area(trend_df, x="date", y="checks", color="store")
    fig5.update_layout(height=390, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig5, use_container_width=True)
with r3b:
    st.markdown("### Факт MTD против плана")
    compare_mtd = latest_df[["store", "mtd_revenue", "month_plan"]].copy().sort_values("mtd_revenue", ascending=False)
    melt = compare_mtd.melt(id_vars="store", var_name="metric", value_name="value")
    fig6 = px.bar(melt, x="store", y="value", color="metric", barmode="group")
    fig6.update_layout(height=390, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")
    st.plotly_chart(fig6, use_container_width=True)

st.markdown("### Таблица сравнения")
comparison = latest_df[["store", "daily_revenue", "checks", "avg_check", "traffic", "conversion", "margin_pct", "sbp_share", "mtd_revenue", "month_plan"]].copy()
comparison["plan_completion_%"] = np.where(comparison["month_plan"] > 0, comparison["mtd_revenue"] / comparison["month_plan"] * 100, 0)
comparison["conversion"] = comparison["conversion"] * 100
comparison["margin_pct"] = comparison["margin_pct"] * 100
comparison["sbp_share"] = comparison["sbp_share"] * 100
comparison = comparison.sort_values("daily_revenue", ascending=False).rename(columns={
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
})
st.dataframe(comparison, use_container_width=True, hide_index=True)

st.caption("Исправлено: даты без сдвига, Samsung отдельно от Restore, фильтр города работает только по выбранному бренду и коду города.")
