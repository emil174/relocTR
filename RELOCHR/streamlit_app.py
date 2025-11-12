# streamlit_app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import re
from datetime import datetime

WD_MAP = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}

def detect_and_load_csv(file, sep=";", encoding="utf-8-sig"):
    df = pd.read_csv(file, sep=sep, encoding=encoding)
    if "date" in df.columns:
        df["_dt"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        dt_col = None
        for c in df.columns:
            if any(k in c.lower() for k in ["date", "дата", "time", "timestamp"]):
                dt_col = c
                break
        if dt_col:
            df["_dt"] = pd.to_datetime(df[dt_col], errors="coerce")
        else:
            raise ValueError("Не найдена колонка даты/времени (date).")
    df = df[df["_dt"].notna()].copy()
    df["weekday"] = df["_dt"].dt.weekday
    df["hour"] = df["_dt"].dt.hour
    df["weekday_name"] = df["weekday"].map(WD_MAP)
    # text
    txt_col = None
    for c in ["message", "text", "caption"]:
        if c in df.columns:
            txt_col = c
            break
    if txt_col is None:
        for c in df.columns:
            if re.search(r"(message|text|сообщ|текст)", c.lower()):
                txt_col = c
                break
    df["message"] = df[txt_col].astype(str).fillna("") if txt_col else ""
    # metrics
    for c in ["views", "reactions_total", "comments"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan
    df["_snippet"] = df["message"].str.replace("\n", " ").str.slice(0, 160)
    return df

def count_emoji(s):
    return len(re.findall(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", s))

def has_list(s):
    return bool(re.search(r"(^|\n)\s*(?:[-–—••]|(\d+)[\.\)])\s", s))

def has_formatting(s):
    return any(tok in s for tok in ["**", "__", "```", "`"])

def has_cta(s):
    return bool(re.search(r"(пишите|свяжитесь|заявк|подробнее|читайте|подпис|переходите|жмите|оставьте)\b", s.lower()))

def has_link(s):
    return bool(re.search(r"(https?://|t\.me/|@[\w_]+)", s))

def contains_keywords(s, kws):
    low = s.lower()
    return int(any(kw in low for kw in kws))

def enrich_features(df):
    text = df["message"].astype(str).fillna("")
    df["char_len"] = text.str.len()
    df["word_len"] = text.str.split().apply(len)
    df["emoji_cnt"] = text.apply(count_emoji)
    df["question_cnt"] = text.str.count(r"\?")
    df["exclam_cnt"] = text.str.count(r"!")
    df["digit_cnt"] = text.str.count(r"\d")
    df["has_list"] = text.apply(has_list).astype(int)
    df["has_fmt"]  = text.apply(has_formatting).astype(int)
    df["has_cta"]  = text.apply(has_cta).astype(int)
    df["has_link"] = text.apply(has_link).astype(int)
    topics = {
        "налоги": ["налог", "ndfl", "kdv", "vat", "vergi"],
        "внж/икамет": ["внж", "икaмет", "ikamet", "пмж", "виза"],
        "банк/счет": ["счёт", "счет", "банк", "iban", "swift", "аккаунт"],
        "регистрация_бизнеса": ["регистрац", "mersis", "ao", "ооо", "ип", "компания", "юрлиц"],
        "недвижимость": ["недвиж", "аренд", "ипотек", "жиль", "кадaстр"],
        "кадры/наём/sgk": ["наём", "наем", "сотрудник", "sgk", "оформлен", "кадры"],
        "платежи/санкции": ["санкц", "платеж", "эквайринг", "карты", "swift"],
        "экономика/курсы": ["курс", "инфляц", "pmi", "индекс", "экономик"],
        "кейсы/гайд": ["чек-лист", "чеклист", "шаг", "кейc", "гайд", "как "],
    }
    for tag, kws in topics.items():
        df[f"topic_{tag}"] = text.apply(lambda s: contains_keywords(s, kws))
    return df

def best_windows(df):
    counts = df.pivot_table(index="weekday_name", columns="hour", values="_dt", aggfunc="count")\
              .reindex(["Пн","Вт","Ср","Чт","Пт","Сб","Вс"])\
              .reindex(range(24), axis=1).fillna(0).astype(int)
    med = df.pivot_table(index="weekday_name", columns="hour", values="views", aggfunc="median")\
           .reindex(["Пн","Вт","Ср","Чт","Пт","Сб","Вс"])\
           .reindex(range(24), axis=1)
    min_n = max(3, int(np.nanpercentile(counts.values.flatten(), 50)))
    mask = counts >= min_n
    med_masked = med.where(mask)
    best = (
        med_masked.stack().dropna().sort_values(ascending=False).head(10)
        .rename("Медиана просмотров").reset_index()
        .rename(columns={"weekday_name":"День","hour":"Час"})
    )
    return best, counts, med

def top_tables(df):
    cols = ["_dt","views","reactions_total","comments","_snippet"]
    extra = [c for c in ["channel_url","channel_members_count"] if c in df.columns]
    view_top = df.sort_values("views", ascending=False).loc[:, cols+extra].head(30)\
                 .rename(columns={"_dt":"Дата","_snippet":"Фрагмент","reactions_total":"Реакции"})
    react_top = df.sort_values("reactions_total", ascending=False).loc[:, cols+extra].head(30)\
                 .rename(columns={"_dt":"Дата","_snippet":"Фрагмент","reactions_total":"Реакции"})
    return view_top, react_top

def compare_groups(df, key_col, metric_col):
    top = df.sort_values(metric_col, ascending=False).head(30).copy()
    rest = df.loc[~df[key_col].isin(top[key_col])].copy()
    features = ["char_len","word_len","emoji_cnt","question_cnt","exclam_cnt","digit_cnt","has_list","has_fmt","has_cta","has_link"]
    tmed = top[features].median().rename("Top мед.")
    rmed = rest[features].median().rename("Ост. мед.")
    comp = pd.concat([tmed, rmed], axis=1)
    comp["Δ к медиане ост."] = (comp["Top мед."] - comp["Ост. мед."]).round(2)

    topic_cols = [c for c in df.columns if c.startswith("topic_")]
    ttopic = top[topic_cols].mean().rename("Top доля")*100
    rtopic = rest[topic_cols].mean().rename("Остальные доля")*100
    tdelta = pd.concat([ttopic.round(1), rtopic.round(1)], axis=1)
    tdelta["Δ п.п."] = (tdelta["Top доля"] - tdelta["Остальные доля"]).round(1)
    tdelta = tdelta.sort_values("Δ п.п.", ascending=False)
    return comp.reset_index().rename(columns={"index":"фича"}), tdelta.reset_index().rename(columns={"index":"тема"})

st.set_page_config(page_title="Telegram Channel Dashboard", layout="wide")
st.title("Telegram Dashboard: частота, эффективность, ТОПы и паттерны")

st.sidebar.header("Данные")
uploaded = st.sidebar.file_uploader("Загрузите CSV", type=["csv"])
st.sidebar.caption("Колонки: date, message, views, reactions_total, comments (sep=';', UTF-8-SIG).")
tz_shift = st.sidebar.number_input("Смещение к UTC (часов)", value=0, step=1)

if uploaded is None:
    st.info("Загрузите CSV-файл слева, чтобы увидеть дашборд.")
    st.stop()

df = detect_and_load_csv(uploaded)
df = enrich_features(df)
df["_dt_local"] = df["_dt"] + pd.to_timedelta(int(tz_shift), unit="h")
min_d, max_d = df["_dt_local"].min().date(), df["_dt_local"].max().date()

st.sidebar.header("Фильтры")
date_from, date_to = st.sidebar.date_input("Диапазон дат (лок.)", (min_d, max_d))
if isinstance(date_from, tuple):
    date_from, date_to = date_from[0], date_from[1]
mask = (df["_dt_local"].dt.date >= pd.to_datetime(date_from).date()) & (df["_dt_local"].dt.date <= pd.to_datetime(date_to).date())
dff = df.loc[mask].copy()

st.caption(f"Выбран период: {date_from} — {date_to}. Постов: {len(dff)}")

tab1, tab2, tab3, tab4 = st.tabs(["Частота и эффективность", "Топ-30", "Паттерны контента", "Сырые данные"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Постов (выборка)", len(dff))
    c2.metric("Период", f"{dff['_dt'].min().date()} — {dff['_dt'].max().date()}")
    c3.metric("Медиана просмотров", int(dff["views"].median(skipna=True)))
    c4.metric("Медиана реакций", int(dff["reactions_total"].median(skipna=True)) if dff["reactions_total"].notna().any() else 0)

    posts_by_wd = dff.groupby("weekday_name")["_dt"].count().reindex(["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]).fillna(0).astype(int)
    posts_by_hr = dff.groupby(dff["_dt_local"].dt.hour)["_dt"].count().reindex(range(24)).fillna(0).astype(int)
    perf_wd = dff.groupby("weekday_name")["views"].median().reindex(["Пн","Вт","Ср","Чт","Пт","Сб","Вс"])
    perf_hr = dff.groupby(dff["_dt_local"].dt.hour)["views"].median().reindex(range(24))

    cc1, cc2 = st.columns(2)
    with cc1:
        st.subheader("Посты по дням недели")
        st.bar_chart(posts_by_wd)
        st.subheader("Медиана просмотров по дням недели")
        st.bar_chart(perf_wd)
    with cc2:
        st.subheader("Посты по часам (лок.)")
        st.bar_chart(posts_by_hr)
        st.subheader("Медиана просмотров по часам (лок.)")
        st.bar_chart(perf_hr)

    st.subheader("Лучшие окна (День×Час)")
    best, counts, med = best_windows(dff)
    st.dataframe(best, use_container_width=True)
    with st.expander("Теплокарты (counts / median views)"):
        st.write("Количество постов:")
        st.dataframe(counts.fillna(0).astype(int))
        st.write("Медиана просмотров:")
        st.dataframe(med)

with tab2:
    st.subheader("Топ-30 по просмотрам")
    topv, topr = top_tables(dff)
    st.dataframe(topv, use_container_width=True)
    st.download_button("Скачать Top-30 Views (CSV)", topv.to_csv(index=False).encode("utf-8-sig"), file_name="top30_by_views.csv")

    st.subheader("Топ-30 по реакциям")
    st.dataframe(topr, use_container_width=True)
    st.download_button("Скачать Top-30 Reactions (CSV)", topr.to_csv(index=False).encode("utf-8-sig"), file_name="top30_by_reactions.csv")

with tab3:
    st.subheader("Сравнение фич: Top-30 Views vs Остальные")
    comp_v, topics_v = compare_groups(dff, key_col="message_id", metric_col="views")
    st.dataframe(comp_v, use_container_width=True)
    st.write("Темы (доля в топе vs остальные):")
    st.dataframe(topics_v, use_container_width=True)

    st.subheader("Сравнение фич: Top-30 Reactions vs Остальные")
    comp_r, topics_r = compare_groups(dff, key_col="message_id", metric_col="reactions_total")
    st.dataframe(comp_r, use_container_width=True)
    st.write("Темы (доля в топе vs остальные):")
    st.dataframe(topics_r, use_container_width=True)

    st.subheader("Распределения длины текста")
    q = dff["char_len"].quantile([0.25,0.5,0.75]).round(0)
    st.write("Квантили длины (символы):", q.to_dict())

with tab4:
    st.dataframe(dff, use_container_width=True)
    st.download_button("Скачать выборку (CSV)", dff.to_csv(index=False).encode("utf-8-sig"), file_name="filtered_data.csv")
