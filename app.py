import streamlit as st
import streamlit.components.v1 as components
import re
from dotenv import load_dotenv
import markdown
import time

from utils.llm_logic import BusinessAnalystAI, process_uploaded_file
from utils.confluence import publish_to_confluence, get_space_pages
from utils.export import create_docx, create_chat_pdf

load_dotenv()

FORTE_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/e/e3/Fortebank_Logo.png"

st.set_page_config(
    page_title="Forte AI Analyst",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(f"""
<style>
    /* Основной фон */
    .stApp {{
        background-color: #F4F6F8;
    }}

    /* Заголовки */
    h1, h2, h3 {{
        color: #9F2349;
        font-family: 'Segoe UI', Roboto, sans-serif;
    }}

    /* Акцентный цвет (Forte Cherry) */
    .highlight-red {{
        color: #9F2349;
        font-weight: bold;
    }}

    /* СТИЛИЗАЦИЯ КНОПОК */
    div.stButton > button:first-child {{
        background-color: #9F2349;
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: 600;
        box-shadow: 0 2px 4px rgba(159, 35, 73, 0.2);
        transition: all 0.2s ease;
    }}

    div.stButton > button:first-child:hover {{
        background-color: #7D1B3A; /* Темнее при наведении */
        color: white;
        transform: translateY(-1px);
        box-shadow: 0 4px 6px rgba(159, 35, 73, 0.3);
    }}

    div.stButton > button:first-child:active {{
        transform: translateY(1px);
    }}

    /* Вторичные кнопки (для истории в сайдбаре) */
    div[data-testid="stSidebar"] div.stButton > button {{
        background-color: white;
        color: #333;
        border: 1px solid #ddd;
        box-shadow: none;
        text-align: left;
        justify-content: flex-start;
    }}

    div[data-testid="stSidebar"] div.stButton > button:hover {{
        background-color: #f0f0f0;
        color: #9F2349;
        border-color: #9F2349;
    }}

    /* Чат-сообщения */
    .stChatMessage {{
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        border: 1px solid #EAEAEA;
        margin-bottom: 10px;
    }}

    /* Аватарки */
    .stChatMessage .st-emotion-cache-1p1m4t1 {{
        background-color: #FEEFF2;
        color: #9F2349;
    }}

    /* Боковая панель */
    [data-testid="stSidebar"] {{
        background-color: #FFFFFF;
        border-right: 1px solid #E0E0E0;
    }}

    /* Статус-бар (индикатор мыслей) */
    [data-testid="stStatusWidget"] {{
        border: 1px solid #9F2349;
        background-color: #FEEFF2;
    }}

    /* Текстовый редактор */
    .stTextArea textarea {{
        font-family: 'Courier New', monospace;
        background-color: #fff;
        border: 1px solid #ddd;
    }}

    /* Скрываем плеер после записи */
    audio {{ width: 100%; margin-top: 10px; }}
</style>
""", unsafe_allow_html=True)


def render_mermaid(code: str):
    html_code = f"""
    <div class="mermaid" style="display: flex; justify-content: center; margin-top: 20px; margin-bottom: 20px;">
        {code}
    </div>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ 
            startOnLoad: true, 
            theme: 'base', 
            themeVariables: {{ 
                primaryColor: '#FEEFF2', 
                primaryBorderColor: '#9F2349', 
                lineColor: '#555',
                edgeLabelBackground: '#fff', 
                tertiaryColor: '#fff' 
            }} 
        }});
    </script>
    """
    components.html(html_code, height=600, scrolling=True)


def display_document_with_diagrams(text: str):
    pattern = r"```mermaid\n(.*?)\n```"
    parts = re.split(pattern, text, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part.strip():
                st.markdown(part)
        else:
            st.caption("👇 *Схема бизнес-процесса*")
            render_mermaid(part)


def handle_user_input(user_text):
    if "analyst_bot" in st.session_state:
        st.session_state.messages.append({"role": "user", "content": user_text})

        if hasattr(st.session_state.analyst_bot, 'save_message_to_db'):
            st.session_state.analyst_bot.save_message_to_db("user", user_text)

        with st.chat_message("user", avatar="👤"):
            st.markdown(user_text)

        with st.chat_message("assistant", avatar="🏦"):
            with st.spinner("Forte AI думает..."):
                response = st.session_state.analyst_bot.get_response(st.session_state.messages)
                st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})

with st.sidebar:
    st.image(FORTE_LOGO_URL, width=180)
    st.markdown("<br>", unsafe_allow_html=True)

    st.subheader("⚙️ Настройки задачи")

    mode_options = ["Новый продукт (MVP)", "Интеграция API", "Отчетность и Аналитика"]
    selected_mode = st.selectbox("Режим работы AI:", mode_options, index=0)

if "current_mode" not in st.session_state:
    st.session_state.current_mode = selected_mode

if st.session_state.current_mode != selected_mode:
    st.session_state.current_mode = selected_mode
    st.session_state.analyst_bot = BusinessAnalystAI(template_type=selected_mode)

    st.session_state.messages = [
        {"role": "assistant", "content": f"Режим переключен на **{selected_mode}**. Готов к работе!"}]
    st.session_state.final_doc = None
    st.session_state.uploaded_files_cache = []
    st.rerun()

if "analyst_bot" not in st.session_state:
    try:
        st.session_state.analyst_bot = BusinessAnalystAI(template_type=selected_mode)
    except Exception as e:
        st.error(f"Ошибка: {e}. Проверьте .env")

if "messages" not in st.session_state:
    db_history = []
    if hasattr(st.session_state.analyst_bot, 'load_history_from_db'):
        db_history = st.session_state.analyst_bot.load_history_from_db()

    if db_history:
        st.session_state.messages = db_history
        st.toast("📜 История чата восстановлена из облака!")
    else:
        st.session_state.messages = [
            {"role": "assistant",
             "content": "Привет! Я **Forte AI Analyst**. \nВы можете писать текстом, использовать **голосовой ввод** или загружать документы."}
        ]

if "final_doc" not in st.session_state:
    st.session_state.final_doc = None

with st.sidebar:
    st.markdown("---")

    if hasattr(st.session_state.analyst_bot, 'get_user_sessions'):
        st.subheader("🗄️ История чатов")

        if "history_sessions" not in st.session_state:
            st.session_state.history_sessions = st.session_state.analyst_bot.get_user_sessions()

        if st.button("🔄 Обновить список"):
            st.session_state.history_sessions = st.session_state.analyst_bot.get_user_sessions()
            st.rerun()

        for s in st.session_state.history_sessions:
            title = s.get('title') or s.get('created_at', 'Без названия')[:16]
            if st.button(f"📄 {title}", key=s['id'], use_container_width=True):
                st.session_state.analyst_bot = BusinessAnalystAI(template_type=selected_mode, session_id=s['id'])
                history = st.session_state.analyst_bot.load_history_from_db()
                if history:
                    st.session_state.messages = history
                    st.session_state.final_doc = None
                    st.toast(f"Загружен чат: {title}")
                    time.sleep(0.5)
                    st.rerun()
        st.markdown("---")

    if st.button("🆕 Новый чат", use_container_width=True):
        st.session_state.analyst_bot = BusinessAnalystAI(template_type=selected_mode)
        st.session_state.messages = [{"role": "assistant", "content": "Начнем с чистого листа. Опишите новую задачу."}]
        st.session_state.final_doc = None
        st.session_state.uploaded_files_cache = []
        st.rerun()

    st.markdown("---")
    st.subheader("Действия")

    audio_value = st.audio_input("Микрофон")

    st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)
    with st.expander("📂 Документы"):
        uploaded_file = st.file_uploader("Загрузить PDF/DOCX", type=["pdf", "docx", "txt", "md"])

    if "uploaded_files_cache" not in st.session_state:
        st.session_state.uploaded_files_cache = []

    if uploaded_file is not None:
        if uploaded_file.name not in st.session_state.uploaded_files_cache:
            with st.spinner("Читаю документ..."):
                file_text = process_uploaded_file(uploaded_file)
                if "Ошибка" not in file_text:
                    context_msg = f"📎 [СИСТЕМА: ПОЛЬЗОВАТЕЛЬ ЗАГРУЗИЛ ФАЙЛ '{uploaded_file.name}']\n\nСОДЕРЖАНИЕ:\n{file_text[:50000]}..."

                    st.session_state.messages.append({"role": "user", "content": context_msg})
                    if hasattr(st.session_state.analyst_bot, 'save_message_to_db'):
                        st.session_state.analyst_bot.save_message_to_db("user", context_msg)

                    ai_confirm = f"📂 Я изучил документ **{uploaded_file.name}**. Буду учитывать его при сборе требований."
                    st.session_state.messages.append({"role": "assistant", "content": ai_confirm})
                    if hasattr(st.session_state.analyst_bot, 'save_message_to_db'):
                        st.session_state.analyst_bot.save_message_to_db("assistant", ai_confirm)

                    st.session_state.uploaded_files_cache.append(uploaded_file.name)
                    st.toast(f"Файл {uploaded_file.name} обработан!")
                    st.rerun()
                else:
                    st.error(file_text)

    st.markdown("---")

    if st.button("📑 Сформировать ТЗ (BRD)", type="primary", use_container_width=True):
        if "analyst_bot" in st.session_state:
            with st.status("🧠 Forte AI работает...", expanded=True) as status:
                def update_status_label(text):
                    st.write(text)


                doc = st.session_state.analyst_bot.generate_requirements_doc(
                    st.session_state.messages,
                    on_status_update=update_status_label
                )
                status.update(label="✅ Документ успешно сформирован!", state="complete", expanded=False)
            st.session_state.final_doc = doc
            st.rerun()

    if len(st.session_state.messages) > 1:
        chat_pdf = create_chat_pdf(st.session_state.messages)
        if chat_pdf:
            st.download_button(
                label="📥 Скачать историю чата (PDF)",
                data=chat_pdf,
                file_name="Chat_History.pdf",
                mime="application/pdf",
                use_container_width=True,
                help="Скачать полный протокол переписки"
            )

    st.markdown("---")
    st.caption(f"Version 3.1 | Supabase & ReportLab")

col1, col2 = st.columns([0.8, 10])
with col2:
    st.markdown(f"# Forte <span class='highlight-red'>AI Analyst</span>", unsafe_allow_html=True)
    st.caption(f"Automated Business Requirements System | Mode: **{selected_mode}**")

st.markdown("<br>", unsafe_allow_html=True)

chat_container = st.container()
with chat_container:
    for msg in st.session_state.messages:
        if "СИСТЕМА: ПОЛЬЗОВАТЕЛЬ ЗАГРУЗИЛ ФАЙЛ" in msg["content"]:
            with st.chat_message("user", avatar="📎"):
                st.caption(f"Загружен файл: {msg['content'].split(']')[0].split('File ')[-1]}")
        else:
            with st.chat_message(msg["role"], avatar="🏦" if msg["role"] == "assistant" else "👤"):
                st.markdown(msg["content"])

st.markdown("###### Быстрые ответы:")
suggestions = ["✅ Да, все верно", "🔒 Добавь про безопасность", "❌ Нет, нужно исправить", "📱 Уточнить про мобайл"]
cols = st.columns(4)
for i, suggestion in enumerate(suggestions):
    if cols[i].button(suggestion, use_container_width=True):
        handle_user_input(suggestion)
        st.rerun()

if audio_value:
    if "analyst_bot" in st.session_state:
        audio_hash = hash(audio_value)
        if "last_audio_hash" not in st.session_state or st.session_state.last_audio_hash != audio_hash:
            with st.spinner("🎤 Слушаю и распознаю..."):
                audio_bytes = audio_value.getvalue()
                transcribed_text = st.session_state.analyst_bot.transcribe_audio(audio_bytes)
                st.toast(f"Распознано: {transcribed_text[:50]}...")
                handle_user_input(transcribed_text)
                st.session_state.last_audio_hash = audio_hash
                st.rerun()

if prompt := st.chat_input("Опишите требования..."):
    handle_user_input(prompt)

if st.session_state.final_doc:
    st.divider()
    st.success("✅ Документ готов! Проверьте содержимое перед отправкой.")

    tab_view, tab_edit = st.tabs(["👁️ Просмотр (Preview)", "✏️ Редактор (Source)"])

    with tab_edit:
        st.info("💡 Здесь вы можете вручную исправить текст.")
        edited_text = st.text_area(
            "Редактирование Markdown кода",
            value=st.session_state.final_doc,
            height=600,
            label_visibility="collapsed"
        )
        if edited_text != st.session_state.final_doc:
            st.session_state.final_doc = edited_text
            st.rerun()

    with tab_view:
        display_document_with_diagrams(st.session_state.final_doc)

    st.divider()

    st.write("### 📤 Экспорт и Публикация")

    if "confluence_pages" not in st.session_state:
        with st.spinner("Подключаюсь к Confluence..."):
            st.session_state.confluence_pages = get_space_pages()

    col_word, col_conf_set = st.columns([2.5, 2.5])

    with col_word:
        docx_file = create_docx(st.session_state.final_doc)
        st.download_button(
            label="📝 Скачать Word",
            data=docx_file,
            file_name="Business_Requirements.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )

    with col_conf_set:
        with st.container(border=True):
            st.write("**Confluence Integration**")

            page_options = list(st.session_state.confluence_pages.keys())
            if page_options:
                selected_parent_name = st.selectbox(
                    "Родительская страница:",
                    page_options,
                    index=0,
                    help="Выберите страницу, под которой будет создан этот документ"
                )
                selected_parent_id = st.session_state.confluence_pages[selected_parent_name]
            else:
                st.warning("Не удалось получить список страниц. Будет создано в корне.")
                selected_parent_id = None

            if st.button("🚀 Опубликовать в Confluence", type="primary", use_container_width=True):
                html_body = markdown.markdown(st.session_state.final_doc)
                title_candidate = "BRD - New Project"
                try:
                    match = re.search(r'^#\s+(.+)$', st.session_state.final_doc, re.MULTILINE)
                    if match:
                        title_candidate = match.group(1).strip()
                    else:
                        title_candidate = f"BRD - {st.session_state.messages[-2]['content'][:30]}..."
                except:
                    pass

                msg = publish_to_confluence(title_candidate, html_body, parent_id=selected_parent_id)

                if "✅" in msg:
                    st.balloons()
                    st.success(msg)
                else:
                    st.error(msg)