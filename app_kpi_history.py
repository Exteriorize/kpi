
import io
import sqlite3
from pathlib import Path
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="KPI Dashboard", layout="wide")

DB_PATH = Path("kpi_dashboard.db")

SUMMARY_COLS = [
    "Магазин", "Оборот", "Трафик", "Конвертация", "Средний чек",
    "Маржа", "UPT общий", "UPT товарный", "Доля аксессуаров",
    "Доля услуг", "Доля СП", "СБП"
]

YESTERDAY_COLS = [
    "Магазин", "Продажи вчера", "Средний чек вчера", "Среднее кол-во шт в чеке вчера",
    "Трафик вчера", "Конвертация вчера", "Маржа вчера", "Валовая прибыль вчера", "СБП вчера"
]

KPI_COLS = [
    "РД", "Магазин", "Оборот оффлайн 2025", "Оборот оффлайн 2026",
    "Прогноз, руб", "L4L, %", "План конверсии", "Факт конверсии",
    "План среднего чека", "Факт среднего чека"
]


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS summary (
            report_date TEXT,
            store TEXT,
            turnover REAL,
            traffic REAL,
            conversion REAL,
            avg_check REAL,
            margin REAL,
            upt_total REAL,
            upt_goods REAL,
            accessories_share REAL,
            services_share REAL,
            sp_share REAL,
            sbp REAL,
            source_file TEXT,
            inserted_at TEXT,
            PRIMARY KEY (report_date, store)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS yesterday_sales (
            report_date TEXT,
            store TEXT,
            sales_yesterday REAL,
            avg_check_yesterday REAL,
            items_per_check_yesterday REAL,
            traffic_yesterday REAL,
            conversion_yesterday REAL,
            margin_yesterday REAL,
            gross_profit_yesterday REAL,
            sbp_yesterday REAL,
            source_file TEXT,
            inserted_at TEXT,
            PRIMARY KEY (report_date, store)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kpi (
            report_date TEXT,
            brand TEXT,
            rd TEXT,
            store TEXT,
            turnover_2025 REAL,
            turnover_2026 REAL,
            forecast_rub REAL,
            l4l REAL,
            plan_conversion REAL,
            fact_conversion REAL,
            plan_avg_check REAL,
            fact_avg_check REAL,
            source_file TEXT,
            inserted_at TEXT,
            PRIMARY KEY (report_date, brand, store)
        )
    """)
    conn.commit()
    conn.close()


def to_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def parse_excel(file_bytes: bytes):
    svod = pd.read_excel(io.BytesIO(file_bytes), sheet_name="СВОД", header=None)
    summary = svod.iloc[5:, 0:12].copy()
    summary.columns = SUMMARY_COLS
    summary = summary[summary["Магазин"].notna()]
    summary = summary[summary["Магазин"].astype(str).str.strip() != ""]
    summary = summary[~summary["Магазин"].astype(str).str.contains("Общий итог", case=False, na=False)]
    summary = to_numeric(summary, SUMMARY_COLS[1:])

    sales_y = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Продажи вчера", header=None)
    yesterday = sales_y.iloc[1:, 1:10].copy()
    yesterday.columns = YESTERDAY_COLS
    yesterday = yesterday[yesterday["Магазин"].notna()]
    yesterday = yesterday[yesterday["Магазин"].astype(str).str.strip() != ""]
    yesterday = to_numeric(yesterday, YESTERDAY_COLS[1:])

    kpi_restore = pd.read_excel(io.BytesIO(file_bytes), sheet_name="KPI Restore", header=None)
    kpi_restore = kpi_restore.iloc[5:, 0:10].copy()
    kpi_restore.columns = KPI_COLS
    kpi_restore["Бренд"] = "Restore"

    kpi_samsung = pd.read_excel(io.BytesIO(file_bytes), sheet_name="KPI Samsung", header=None)
    kpi_samsung = kpi_samsung.iloc[5:, 0:10].copy()
    kpi_samsung.columns = KPI_COLS
    kpi_samsung["Бренд"] = "Samsung"

    kpi_all = pd.concat([kpi_restore, kpi_samsung], ignore_index=True)
    kpi_all = kpi_all[kpi_all["Магазин"].notna()]
    kpi_all = kpi_all[kpi_all["Магазин"].astype(str).str.strip() != ""]
    kpi_all = to_numeric(kpi_all, KPI_COLS[2:])

    stores = sorted(set(summary["Магазин"].astype(str).tolist()))
    return {"summary": summary, "yesterday": yesterday, "kpi": kpi_all, "stores": stores}


def upsert_upload(parsed: dict, report_date: str, source_file: str):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM summary WHERE report_date = ?", (report_date,))
    cur.execute("DELETE FROM yesterday_sales WHERE report_date = ?", (report_date,))
    cur.execute("DELETE FROM kpi WHERE report_date = ?", (report_date,))
    conn.commit()

    summary = parsed["summary"].copy()
    pd.DataFrame({
        "report_date": report_date,
        "store": summary["Магазин"].astype(str),
        "turnover": summary["Оборот"],
        "traffic": summary["Трафик"],
        "conversion": summary["Конвертация"],
        "avg_check": summary["Средний чек"],
        "margin": summary["Маржа"],
        "upt_total": summary["UPT общий"],
        "upt_goods": summary["UPT товарный"],
        "accessories_share": summary["Доля аксессуаров"],
        "services_share": summary["Доля услуг"],
        "sp_share": summary["Доля СП"],
        "sbp": summary["СБП"],
        "source_file": source_file,
        "inserted_at": now,
    }).to_sql("summary", conn, if_exists="append", index=False)

    yesterday = parsed["yesterday"].copy()
    if not yesterday.empty:
        pd.DataFrame({
            "report_date": report_date,
            "store": yesterday["Магазин"].astype(str),
            "sales_yesterday": yesterday["Продажи вчера"],
            "avg_check_yesterday": yesterday["Средний чек вчера"],
            "items_per_check_yesterday": yesterday["Среднее кол-во шт в чеке вчера"],
            "traffic_yesterday": yesterday["Трафик вчера"],
            "conversion_yesterday": yesterday["Конвертация вчера"],
            "margin_yesterday": yesterday["Маржа вчера"],
            "gross_profit_yesterday": yesterday["Валовая прибыль вчера"],
            "sbp_yesterday": yesterday["СБП вчера"],
            "source_file": source_file,
            "inserted_at": now,
        }).to_sql("yesterday_sales", conn, if_exists="append", index=False)

    kpi = parsed["kpi"].copy()
    if not kpi.empty:
        pd.DataFrame({
            "report_date": report_date,
            "brand": kpi["Бренд"].astype(str),
            "rd": kpi["РД"].astype(str),
            "store": kpi["Магазин"].astype(str),
            "turnover_2025": kpi["Оборот оффлайн 2025"],
            "turnover_2026": kpi["Оборот оффлайн 2026"],
            "forecast_rub": kpi["Прогноз, руб"],
            "l4l": kpi["L4L, %"],
            "plan_conversion": kpi["План конверсии"],
            "fact_conversion": kpi["Факт конверсии"],
            "plan_avg_check": kpi["План среднего чека"],
            "fact_avg_check": kpi["Факт среднего чека"],
            "source_file": source_file,
            "inserted_at": now,
        }).to_sql("kpi", conn, if_exists="append", index=False)

    conn.close()


@st.cache_data(ttl=60)
def load_history():
    conn = get_conn()
    summary = pd.read_sql_query("SELECT * FROM summary", conn)
    yesterday = pd.read_sql_query("SELECT * FROM yesterday_sales", conn)
    kpi = pd.read_sql_query("SELECT * FROM kpi", conn)
    conn.close()

    for df in [summary, yesterday, kpi]:
        if not df.empty:
            df["report_date"] = pd.to_datetime(df["report_date"]).dt.date
    return summary, yesterday, kpi


def fmt_num(value, percent=False):
    if pd.isna(value):
        return "—"
    if percent:
        return f"{value * 100:.2f}%"
    return f"{value:,.0f}".replace(",", " ")


init_db()
st.title("KPI Dashboard")
st.caption("Загружай ежедневный Excel, сохраняй его по дате, и сайт будет обновлять историю автоматически.")

with st.sidebar:
    st.header("Загрузка файла")
    uploaded = st.file_uploader("Excel KPI", type=["xlsx"])
    report_date = st.date_input("Дата отчёта", value=date.today(), format="DD.MM.YYYY")
    save_clicked = st.button("Сохранить в историю", type="primary", use_container_width=True)
    st.markdown("---")
    section = st.radio("Раздел", ["Обзор магазина", "Динамика по датам", "Сырые таблицы"], index=0)

parsed_live = None
if uploaded is not None:
    try:
        file_bytes = uploaded.read()
        parsed_live = parse_excel(file_bytes)
        st.success(f"Файл открыт: {uploaded.name}. Магазинов: {len(parsed_live['stores'])}")
        if save_clicked:
            upsert_upload(parsed_live, report_date.isoformat(), uploaded.name)
            st.cache_data.clear()
            st.success(f"Данные за {report_date.strftime('%d.%m.%Y')} сохранены в историю.")
    except Exception as e:
        st.error(f"Ошибка чтения файла: {e}")

summary_hist, yesterday_hist, kpi_hist = load_history()

if summary_hist.empty and parsed_live is None:
    st.info("Сначала загрузи KPI-файл и нажми «Сохранить в историю».")
    st.stop()

store_list = sorted(summary_hist["store"].astype(str).unique()) if not summary_hist.empty else parsed_live["stores"]
dates = sorted(pd.to_datetime(summary_hist["report_date"]).dt.date.unique())[::-1] if not summary_hist.empty else [report_date]

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    selected_store = st.selectbox("Магазин", store_list)
with col2:
    selected_date = st.selectbox("Дата отчёта", dates)
with col3:
    compare_mode = st.selectbox("Сравнение", ["Со средней по сети", "С прошлой датой"])

current_df = summary_hist[(summary_hist["store"] == selected_store) & (summary_hist["report_date"] == pd.to_datetime(selected_date).date())].copy()
store_hist = summary_hist[summary_hist["store"] == selected_store].sort_values("report_date").copy()

if current_df.empty:
    st.warning("Для выбранного магазина на эту дату данных нет.")
    st.stop()

row = current_df.iloc[0]
network_current = summary_hist[summary_hist["report_date"] == pd.to_datetime(selected_date).date()]
network_avg = network_current.mean(numeric_only=True) if not network_current.empty else pd.Series(dtype=float)

prev_row = None
prev_candidates = store_hist[store_hist["report_date"] < pd.to_datetime(selected_date).date()]
if not prev_candidates.empty:
    prev_row = prev_candidates.iloc[-1]

if section == "Обзор магазина":
    a, b, c, d = st.columns(4)
    a.metric("Оборот", fmt_num(row["turnover"]))
    b.metric("Трафик", fmt_num(row["traffic"]))
    c.metric("Конвертация", fmt_num(row["conversion"], percent=True))
    d.metric("Средний чек", fmt_num(row["avg_check"]))

    e, f, g, h = st.columns(4)
    e.metric("Маржа", fmt_num(row["margin"], percent=True))
    f.metric("Доля аксессуаров", fmt_num(row["accessories_share"], percent=True))
    g.metric("Доля услуг", fmt_num(row["services_share"], percent=True))
    h.metric("СБП", fmt_num(row["sbp"], percent=True))

    fields = [
        ("turnover", "Оборот"),
        ("traffic", "Трафик"),
        ("conversion", "Конвертация"),
        ("avg_check", "Средний чек"),
        ("margin", "Маржа"),
        ("accessories_share", "Аксессуары"),
        ("services_share", "Услуги"),
        ("sbp", "СБП"),
    ]
    percent_fields = {"conversion", "margin", "accessories_share", "services_share", "sbp"}

    st.markdown("### Сравнение")
    if compare_mode == "Со средней по сети" and not network_current.empty:
        comp = pd.DataFrame({
            "Метрика": [label for field, label in fields],
            "Магазин": [row[field] * 100 if field in percent_fields else row[field] for field, label in fields],
            "Сеть": [network_avg[field] * 100 if field in percent_fields else network_avg[field] for field, label in fields],
        })
        fig = px.bar(comp.melt(id_vars="Метрика", value_vars=["Магазин", "Сеть"], var_name="Серия", value_name="Значение"),
                     x="Метрика", y="Значение", barmode="group")
        st.plotly_chart(fig, use_container_width=True)
    elif prev_row is not None:
        comp = pd.DataFrame({
            "Метрика": [label for field, label in fields],
            "Текущая дата": [row[field] * 100 if field in percent_fields else row[field] for field, label in fields],
            "Прошлая дата": [prev_row[field] * 100 if field in percent_fields else prev_row[field] for field, label in fields],
        })
        fig = px.bar(comp.melt(id_vars="Метрика", value_vars=["Текущая дата", "Прошлая дата"], var_name="Серия", value_name="Значение"),
                     x="Метрика", y="Значение", barmode="group")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Нужно хотя бы 2 даты в истории.")

elif section == "Динамика по датам":
    st.markdown(f"## Динамика: {selected_store}")
    if len(store_hist) < 2:
        st.info("Пока мало истории. Загрузи ещё файлы за другие даты.")
    else:
        metric_map = {
            "Оборот": "turnover",
            "Трафик": "traffic",
            "Конвертация": "conversion",
            "Средний чек": "avg_check",
            "Маржа": "margin",
            "Доля аксессуаров": "accessories_share",
            "Доля услуг": "services_share",
            "СБП": "sbp",
        }
        metric_name = st.selectbox("Метрика", list(metric_map.keys()))
        field = metric_map[metric_name]
        plot_df = store_hist[["report_date", field]].dropna().copy()
        plot_df["plot_value"] = plot_df[field] * 100 if field in {"conversion", "margin", "accessories_share", "services_share", "sbp"} else plot_df[field]
        fig = px.line(plot_df, x="report_date", y="plot_value", markers=True)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(store_hist, use_container_width=True, hide_index=True)

else:
    st.write("### Summary")
    st.dataframe(summary_hist.sort_values(["report_date", "store"], ascending=[False, True]), use_container_width=True, hide_index=True)
    st.write("### Yesterday sales")
    st.dataframe(yesterday_hist.sort_values(["report_date", "store"], ascending=[False, True]), use_container_width=True, hide_index=True)
    st.write("### KPI")
    st.dataframe(kpi_hist.sort_values(["report_date", "brand", "store"], ascending=[False, True, True]), use_container_width=True, hide_index=True)
