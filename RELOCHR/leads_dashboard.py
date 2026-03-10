import streamlit as st
import pandas as pd
import json
import plotly.express as px

# Настройка стиля RelocationTR
st.set_page_config(page_title="RelocationTR Lead Sandbox", layout="wide")

st.sidebar.image("https://relocationtr.com/wp-content/uploads/2023/06/logo.png", width=200) # Лого с сайта
st.sidebar.title("⚙️ Настройки поиска")

# Интерактивные настройки для коллег
st.sidebar.markdown("### Плюс-слова")
plus_input = st.sidebar.text_area("Искать эти слова (через запятую):", 
    "открыть ип, счет без депозита, регистрация компании, бухгалтер, юрист, текнокент")

st.sidebar.markdown("### Минус-слова")
minus_input = st.sidebar.text_area("Игнорировать эти слова:", 
    "семинар, вебинар, ищу работу, вакансия, под ключ")

# Превращаем текст в списки
PLUS_WORDS = [x.strip().lower() for x in plus_input.split(",")]
MINUS_WORDS = [x.strip().lower() for x in minus_input.split(",")]

st.title("🛡️ Песочница Лидогенерации")
st.info("Коллеги, загрузите JSON-экспорт чата и настройте фильтры слева, чтобы увидеть потенциал канала.")

uploaded_file = st.file_uploader("Шаг 1: Перетащите сюда result.json", type="json")

if uploaded_file:
    data = json.load(uploaded_file)
    messages = data.get('messages', [])
    
    leads = []
    for msg in messages:
        if msg.get('type') != 'message' or not msg.get('text'): continue
        
        # Сборка текста сообщения
        raw_text = msg['text']
        text = "".join([p if isinstance(p, str) else p.get('text', '') for p in raw_text])
        text_l = text.lower()
        
        # Логика фильтрации
        if any(m in text_l for m in MINUS_WORDS): continue
        
        matched = [p for p in PLUS_WORDS if p in text_l]
        if matched:
            leads.append({
                "Дата": pd.to_datetime(msg.get('date')),
                "Кто писал": msg.get('from', 'Скрыт'),
                "Слова-триггеры": ", ".join(matched),
                "Сообщение": text
            })

    df = pd.DataFrame(leads)

    if not df.empty:
        st.success(f"📈 Найдено {len(df)} потенциальных лидов!")
        
        # График для презентации
        df['Месяц'] = df['Дата'].dt.to_period('M').astype(str)
        fig = px.bar(df.groupby('Месяц').size().reset_index(name='Кол-во'), 
                     x='Месяц', y='Кол-во', title="Активность запросов по времени")
        st.plotly_chart(fig, use_container_width=True)

        # Таблица
        st.dataframe(df.sort_values("Дата", ascending=False), use_container_width=True)
        
        # Кнопка экспорта
        st.download_button("📊 Скачать результат для CRM", df.to_csv(index=False).encode('utf-8-sig'), "leads.csv")
    else:
        st.warning("С такими настройками лидов не найдено. Попробуйте упростить ключевые слова.")
