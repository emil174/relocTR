# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import json
import re
import plotly.express as px
from datetime import datetime

# --- НАСТРОЙКИ И МАППИНГИ ---
WD_MAP = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}

st.set_page_config(page_title="RelocationTR | Lead Intelligence", layout="wide")

# --- ЛОГИКА ОБРАБОТКИ ДАННЫХ ---
def process_telegram_json(data):
    messages = data.get('messages', [])
    rows = []
    for m in messages:
        if m.get('type') != 'message' or not m.get('text'):
            continue
        
        # Сборка текста (Телеграм иногда дробит его на объекты)
        raw = m['text']
        txt = "".join([p if isinstance(p, str) else p.get('text', '') for p in raw])
        
        dt = pd.to_datetime(m.get('date'), errors='coerce')
        if pd.isna(dt): continue

        rows.append({
            "date": dt,
            "user": m.get('from', 'Скрытый пользователь'),
            "message": txt,
            "hour": dt.hour,
            "weekday": dt.weekday(),
            "weekday_name": WD_MAP[dt.weekday()]
        })
    return pd.DataFrame(rows)

def enrich_data(df):
    text = df["message"].str.lower()
    # Базовые фичи контента
    df["char_len"] = text.str.len()
    df["word_cnt"] = text.str.split().apply(lambda x: len(x) if isinstance(x, list) else 0)
    df["question_cnt"] = text.str.count(r"\?")
    df["has_link"] = text.str.contains(r"http|t\.me|@").astype(int)
    
    # --- УМНЫЕ ТЕГИ (SMART INTERSECTION) ---
    topics = {
        "🏦 Банки": (['счет', 'банк', 'iban', 'swift', 'депозит', 'карту'], ['открыть', 'нерезидент', 'без внж', 'бизнес', 'deniz', 'vakif', 'ziraat']),
        "🏢 Регистрация": (['открыть', 'регистрац', 'оформить', 'создать'], ['ип', 'ооо', 'компани', 'бизнес', 'фирму', 'mersis', 'limited', 'адрес']),
        "⚖️ Налоги": (['налог', 'vergi', 'kdv', 'бухгалтер', 'аудит', 'ндфл'], ['консультац', 'отчет', 'декларац', 'нужен', 'помочь']),
        "🚀 Текнокент": (['технопарк', 'текнокент', 'teknokent', 'it'], ['льготы', 'вход', 'налоги', 'резидент', '0%']),
        "👤 Кадры/WP": (['сотрудник', 'нанять', 'оформить', 'разрешение'], ['рабочее', 'виза', 'sgk', 'директор']),
        "📉 Ликвидация": (['закрыть', 'ликвид', 'удалить'], ['ооо', 'фирм', 'бизнес', 'компани']),
        "🛍️ Маркетплейсы": (['trendyol', 'hepsiburada', 'amazon', 'маркетплейс'], ['выход', 'продавать', 'открыть', 'ип', 'ооо'])
    }
    
    for tag, (list_a, list_b) in topics.items():
        # Сообщение - лид, если есть слово из А И слово из Б
        df[f"topic_{tag}"] = df["message"].apply(
            lambda s: 1 if any(a in s.lower() for a in list_a) and any(b in s.lower() for b in list_b) else 0
        )
    
    # Минус-слова для чистоты
    MINUS = ['семинар', 'вебинар', 'регистрируйся', 'ищу работу', 'вакансия']
    df["is_spam"] = text.apply(lambda s: 1 if any(m in s for m in MINUS) else 0)
    
    topic_cols = [c for c in df.columns if c.startswith("topic_")]
    df["is_lead"] = ((df[topic_cols].sum(axis=1) > 0) & (df["is_spam"] == 0)).astype(int)
    
    # Категория для таблицы
    def get_main_topic(row):
        for col in topic_cols:
            if row[col] == 1: return col.replace("topic_", "")
        return "Прочее"
    df["main_category"] = df.apply(get_main_topic, axis=1)
    
    return df

# --- ИНТЕРФЕЙС ---
st.title("🛡️ RelocationTR | Lead Intelligence Dashboard")
st.markdown("Система автоматического поиска и анализа B2B-запросов в Telegram")

with st.sidebar:
    st.header("Вводные данные")
    uploaded = st.file_uploader("Загрузите JSON экспорт чата", type="json")
    tz_shift = st.number_input("Смещение времени (UTC+)", value=3)
    
    st.divider()
    st.write("### Настройки поиска")
    st.caption("Используется логика Smart Intersection (A+B) для фильтрации шума.")

if not uploaded:
    st.info("👋 Коллеги, привет! Чтобы начать анализ, выгрузите историю чата в формате JSON и перетащите её сюда.")
    st.stop()

# Загрузка и обработка
with st.spinner('Анализирую данные...'):
    raw_json = json.load(uploaded)
    df = process_telegram_json(raw_json)
    df["date"] = df["date"] + pd.to_timedelta(int(tz_shift), unit="h")
    df = enrich_data(df)

# Фильтр по периоду
min_d, max_d = df["date"].min().date(), df["date"].max().date()
date_range = st.sidebar.date_input("Период анализа", [min_d, max_d])
if len(date_range) == 2:
    df = df[(df["date"].dt.date >= date_range[0]) & (df["date"].dt.date <= date_range[1])]

# РАЗДЕЛЕНИЕ НА ВКЛАДКИ
tab1, tab2, tab3, tab4 = st.tabs(["📊 Обзор рынка", "🔥 Карта активности", "📝 Реестр лидов", "🔬 Анализ контента"])

with tab1:
    leads_df = df[df["is_lead"] == 1].copy()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Всего сообщений", len(df))
    c2.metric("Найдено лидов", len(leads_df))
    c3.metric("Конверсия чата", f"{round(len(leads_df)/len(df)*100, 2)}%")
    c4.metric("Уникальных авторов", leads_df["user"].nunique())

    st.subheader("Популярность услуг (Запросы)")
    topic_counts = leads_df[[c for c in leads_df.columns if c.startswith("topic_")]].sum().sort_values(ascending=True)
    topic_counts.index = [i.replace("topic_", "") for i in topic_counts.index]
    fig_topics = px.bar(topic_counts, orientation='h', color_discrete_sequence=['#004d40'])
    fig_topics.update_layout(showlegend=False, xaxis_title="Кол-во запросов", yaxis_title="")
    st.plotly_chart(fig_topics, use_container_width=True)

    st.subheader("Динамика лидов по дням")
    daily_leads = leads_df.set_index('date').resample('D').size().reset_index(name='Кол-во')
    st.line_chart(daily_leads.set_index('date'))

with tab2:
    st.subheader("Когда клиенты пишут чаще всего?")
    st.write("Тепловая карта распределения лидов по времени суток и дням недели.")
    
    if not leads_df.empty:
        heatmap = leads_df.pivot_table(
            index="weekday_name", 
            columns="hour", 
            values="message", 
            aggfunc="count"
        ).reindex(["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]).fillna(0)
        
        fig_heat = px.imshow(heatmap, 
                            labels=dict(x="Час", y="День", color="Лиды"),
                            x=list(range(24)),
                            color_continuous_scale="YlGnBu")
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.warning("Недостаточно данных для тепловой карты")

with tab3:
    st.subheader("Список целевых запросов")
    
    selected_topics = st.multiselect("Фильтр по нишам:", 
                                     [c.replace("topic_", "") for c in leads_df.columns if c.startswith("topic_")],
                                     default=[c.replace("topic_", "") for c in leads_df.columns if c.startswith("topic_")])
    
    if selected_topics:
        topic_mask = leads_df[[f"topic_{t}" for t in selected_topics]].sum(axis=1) > 0
        display_df = leads_df[topic_mask][["date", "user", "main_category", "message", "question_cnt"]]
        
        st.dataframe(display_df.sort_values("date", ascending=False), 
                     use_container_width=True, 
                     hide_index=True,
                     column_config={
                         "date": st.column_config.DatetimeColumn("Дата", format="D MMM, HH:mm"),
                         "message": st.column_config.TextColumn("Сообщение", width="large")
                     })
        
        st.download_button("📥 Скачать базу для CRM", 
                           display_df.to_csv(index=False).encode("utf-8-sig"), 
                           "relocation_leads.csv")

with tab4:
    st.subheader("Паттерны сообщений")
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.write("**Средняя длина сообщения (символы)**")
        avg_len = df.groupby("is_lead")["char_len"].median()
        st.bar_chart(avg_len)
        st.caption("0 - Обычный шум, 1 - Целевые лиды. Обычно лиды пишут короче и конкретнее.")
        
    with col_b:
        st.write("**Количество вопросов в запросе**")
        fig_q = px.histogram(leads_df, x="question_cnt", nbins=10, color_discrete_sequence=['#ff8f00'])
        st.plotly_chart(fig_q, use_container_width=True)

    st.divider()
    st.write("### Топ активных пользователей (потенциальные партнеры или спамеры)")
    st.write(leads_df["user"].value_counts().head(10))
