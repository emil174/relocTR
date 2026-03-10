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
            lambda s: 1 if any(a in s.lower() for a in list_a) and any(b in s.lower
