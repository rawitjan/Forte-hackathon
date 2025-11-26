import os
import requests
from requests.auth import HTTPBasicAuth
import json


def get_auth_headers():
    url = os.getenv("CONFLUENCE_URL")
    username = os.getenv("CONFLUENCE_USER")
    api_token = os.getenv("CONFLUENCE_API_TOKEN")

    if not url or not username or not api_token:
        return None, None, None

    if not url.endswith('/wiki'):
        base_url = f"{url}/wiki"
    else:
        base_url = url

    auth = HTTPBasicAuth(username, api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    return base_url, auth, headers


def get_space_pages():
    base_url, auth, headers = get_auth_headers()
    space_key = os.getenv("CONFLUENCE_SPACE", "DS")

    if not base_url:
        return {"⚠️ Демо режим (Нет ключей)": None}

    try:
        api_url = f"{base_url}/rest/api/content"
        params = {
            "spaceKey": space_key,
            "type": "page",
            "limit": 20,
            "orderby": "history.createdDate desc",
            "expand": "version"
        }

        response = requests.get(api_url, auth=auth, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            pages = {}
            pages[f"📂 Корень пространства"] = None

            for page in data.get('results', []):
                pages[f"📄 {page['title']}"] = page['id']
            return pages
        else:
            print(f"Ошибка получения страниц: {response.status_code} - {response.text}")
            return {f"❌ Ошибка {response.status_code}": None}

    except Exception as e:
        return {f"❌ Ошибка сети: {e}": None}


def publish_to_confluence(title, html_content, parent_id=None):
    base_url, auth, headers = get_auth_headers()
    space_key = os.getenv("CONFLUENCE_SPACE", "DS")

    if not base_url:
        return "⚠️ Демо режим: API ключи не настроены."

    api_url = f"{base_url}/rest/api/content"

    payload = {
        "title": title,
        "type": "page",
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": html_content,
                "representation": "storage"
            }
        }
    }

    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]

    try:
        response = requests.post(api_url, auth=auth, headers=headers, json=payload)

        if response.status_code == 200:
            data = response.json()
            link = base_url + data['_links']['webui']
            return f"✅ Успешно создано! [Открыть в Confluence]({link})"

        elif "title already exists" in response.text.lower():
            return "⚠️ Ошибка: Страница с таким названием уже существует. Измените заголовок или тему."

        else:
            return f"❌ Ошибка API {response.status_code}: {response.text[:200]}"

    except Exception as e:
        return f"❌ Критическая ошибка: {str(e)}"