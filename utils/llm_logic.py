import os
import re
import base64
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
import PyPDF2
from docx import Document
import uuid
from supabase import create_client, Client
from datetime import date

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"⚠️ Ошибка инициализации Supabase: {e}")
else:
    print("⚠️ Supabase ключи не найдены. История не будет сохраняться.")

def process_uploaded_file(uploaded_file):
    try:
        text = ""
        if uploaded_file.name.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        elif uploaded_file.name.endswith('.docx'):
            doc = Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif uploaded_file.name.endswith('.txt') or uploaded_file.name.endswith('.md'):
            text = uploaded_file.read().decode("utf-8")
        return text
    except Exception as e:
        return f"Ошибка чтения файла: {e}"

TODAY = date.today()

BASE_SYSTEM_PROMPT = """
Ты — Senior Business Analyst в банке ForteBank.
Твоя задача — создавать полную техническую документацию (BRD), сочетающую бизнесовый (Agile) и технический (Waterfall) подходы.
Ты обязан уделять приоритетное внимание вопросам информационной безопасности (InfoSec).
"""

PROMPT_TEMPLATES = {
    "Новый продукт (MVP)": """
    ФОКУС: Клиентский путь и функции приложения.
    ВАЖНО: Описывай User Stories для понимания ценности, а FR для технической реализации.
    """,

    "Интеграция API": """
    ФОКУС: Системное взаимодействие.
    ВАЖНО: User Stories здесь описывают потребности систем (как System A, я хочу отправить запрос...), а FR - контракты.
    """,

    "Отчетность и Аналитика": """
    ФОКУС: Данные и формулы.
    ВАЖНО: User Stories описывают потребности бизнес-пользователей в инсайтах.
    """
}

BEHAVIOR_INSTRUCTIONS = """
### ИНСТРУКЦИИ
1. **Step-by-Step:** Задавай по 1-2 вопроса за раз.
2. **Context:** Помни про безопасность банка (ForteBank).
3. **Output:** Не генерируй документ, пока не получишь команду SYSTEM_GENERATE.
"""

GENERATION_PROMPT = f"""
КОМАНДА: SYSTEM_GENERATE.

Сформируй документ BRD, строго следуя шаблону ниже.

# Business Requirements Document (BRD): [Название проекта]
**Проект:** [Название]
**Дата:** {TODAY}
**Автор:** Forte AI Analyst

## 1. Введение
### 1.1. Бизнес-цель
(Зачем мы это делаем? Ожидаемый эффект)

### 1.2. Границы проекта (Scope)
* **Входит в MVP:** ...
* **Не входит в MVP:** ...

## 2. Пользовательские истории (User Stories)
*Опиши потребности пользователей в формате Agile.*

| ID | Роль | Хочу (Action) | Чтобы (Value) |
|---|---|---|---|
| US.001 | [Роль] | ... | ... |
| US.002 | [Роль] | ... | ... |
*(Добавь минимум 3-5 историй)*

## 3. Функциональные требования (Functional Requirements)
*Техническая детализация требований. Каждое требование должно иметь уникальный ID (FR.xxx).*

* **FR.001:** Система должна...
* **FR.002:** При нажатии кнопки X, система выполняет Y...
* **FR.003:** [Опиши валидацию полей]...
* **FR.004:** [Опиши логику обработки]...

## 4. Логика и Процессы
### 4.1. Основной сценарий (Happy Path)
(Пошаговое описание)

### 4.2. Обработка ошибок (Edge Cases)
(Что делать, если сервис недоступен?)

## 5. KPI по Безопасности и Compliance (ОБЯЗАТЕЛЬНО)
* **Аутентификация:** (2FA, FaceID, SMS для сумм > 50 000 KZT)
* **Разграничение доступа (RBAC):** (Роли, матрицы доступа)
* **Защита данных:** (Шифрование TLS 1.2+, маскирование PAN/PII)
* **Лимиты и Антифрод:** (Ограничения сумм, проверка дублей)
* **Логирование:** (Аудит-лог действий)

## 6. Нефункциональные требования (NFR)
* **NFR.001 (Производительность):** Время отклика API не более 3 секунд.
* **NFR.002 (Доступность):** SLA 99.9%.
* **NFR.003 (Масштабируемость):** ...

## 7. Диаграмма процесса (Mermaid State Diagram)
Вставь код диаграммы ниже. Используй **stateDiagram-v2**.

**ПРАВИЛА MERMAID:**
1. `stateDiagram-v2`
2. ID состояний ТОЛЬКО английскими буквами без пробелов (например `CheckLimit`).
3. Текст пиши после двоеточия.

Пример:
```mermaid
stateDiagram-v2
    [*] --> Init
    Init --> Process : Start
    Process --> Success : OK
```
"""

CRITIQUE_PROMPT = """
[РЕЖИМ САМОКРИТИКИ]
Ты — Lead Architect. Проверь документ.

1. **User Stories:** Есть ли раздел 2 с User Stories?
2. **FR/NFR:** Используются ли коды FR.xxx и NFR.xxx?
3. **Безопасность:** Заполнен ли раздел 5?
4. **Mermaid:** Проверь синтаксис `stateDiagram-v2`.

🔴 ВЕРНИ ТОЛЬКО ИСПРАВЛЕННЫЙ ТЕКСТ ДОКУМЕНТА В МАРКЕРАХ:
___START_DOCUMENT___
...текст...
___END_DOCUMENT___
"""


class BusinessAnalystAI:
    def __init__(self, template_type="Новый продукт (MVP)", session_id=None):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key and "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
        if not api_key:
            raise ValueError("Не найден GOOGLE_API_KEY")

        self.chat_model = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.3,
            google_api_key=api_key,
            convert_system_message_to_human=True
        )

        specific_instruction = PROMPT_TEMPLATES.get(template_type, PROMPT_TEMPLATES["Новый продукт (MVP)"])
        self.full_system_prompt = f"{BASE_SYSTEM_PROMPT}\n\n### РЕЖИМ РАБОТЫ: {template_type}\n{specific_instruction}\n\n{BEHAVIOR_INSTRUCTIONS}"

        self.session_id = session_id if session_id else str(uuid.uuid4())

    def save_message_to_db(self, role, content):
        """Сохраняет или обновляет массив сообщений в Supabase"""
        if supabase:
            try:
                response = supabase.table("chat_sessions").select("messages").eq("id", self.session_id).execute()

                current_messages = []
                if response.data:
                    current_messages = response.data[0].get("messages", [])

                title_update = {}
                if len(current_messages) == 0 and role == 'user':
                    clean_title = content.replace("#", "").replace("*", "").strip()[:40]
                    title_update = {"title": clean_title + "..."}

                new_message = {
                    "role": role,
                    "content": content,
                    "timestamp": str(uuid.uuid4())
                }
                current_messages.append(new_message)

                data = {
                    "id": self.session_id,
                    "messages": current_messages,
                    **title_update
                }
                supabase.table("chat_sessions").upsert(data).execute()

            except Exception as e:
                print(f"Ошибка сохранения в Supabase: {e}")

    def load_history_from_db(self):
        if supabase:
            try:
                response = supabase.table("chat_sessions").select("messages").eq("id", self.session_id).execute()
                if response.data:
                    return response.data[0].get("messages", [])
            except Exception as e:
                print(f"Ошибка загрузки из Supabase: {e}")
        return []

    def get_user_sessions(self):
        if supabase:
            try:
                response = supabase.table("chat_sessions") \
                    .select("id, title, created_at") \
                    .order("created_at", desc=True) \
                    .limit(20) \
                    .execute()
                return response.data
            except Exception as e:
                print(f"Ошибка получения списка сессий: {e}")
        return []

    def transcribe_audio(self, audio_bytes):
        try:
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            message = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": "Транскрибируй аудио. Верни только текст."
                    },
                    {
                        "type": "media",
                        "mime_type": "audio/wav",
                        "data": audio_b64
                    }
                ]
            )
            response = self.chat_model.invoke([message])
            return response.content
        except Exception as e:
            return f"Ошибка: {e}"

    def get_response(self, history):
        messages = [SystemMessage(content=self.full_system_prompt)]
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        response_content = self.chat_model.invoke(messages).content

        self.save_message_to_db("assistant", response_content)

        return response_content

    def generate_requirements_doc(self, history, on_status_update=None):
        def update_status(msg):
            if on_status_update:
                on_status_update(msg)

        update_status("🔍 Анализ данных...")
        messages = [SystemMessage(content=self.full_system_prompt)]
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        update_status("🏗️ Формирование User Stories и требований...")
        messages_for_draft = messages.copy()
        messages_for_draft.append(HumanMessage(content=GENERATION_PROMPT))
        draft_response = self.chat_model.invoke(messages_for_draft)

        update_status("🛡️ Валидация безопасности и стандартов...")
        messages_for_critique = messages_for_draft.copy()
        messages_for_critique.append(AIMessage(content=draft_response.content))
        messages_for_critique.append(HumanMessage(content=CRITIQUE_PROMPT))

        final_response = self.chat_model.invoke(messages_for_critique)
        raw_text = final_response.content

        update_status("✨ Финализация...")
        cleaned_text = self._clean_output(raw_text)

        # Можно сохранить факт генерации документа в базу
        # self.save_message_to_db("system", "Документ сгенерирован")

        return cleaned_text

    def _clean_output(self, text):
        pattern = r"___START_DOCUMENT___(.*?)___END_DOCUMENT___"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r'^#+\s', text, re.MULTILINE)
        if match:
            start_index = match.start()
            return text[start_index:]
        return text