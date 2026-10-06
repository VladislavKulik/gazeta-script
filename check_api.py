"""Перевірка підключення до Ollama API: ключ, список моделей, тестовий запит.
Запуск: python check_api.py"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("OLLAMA_API_KEY", "").strip()
HOST = os.getenv("OLLAMA_HOST", "https://ollama.com").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b")

if not KEY:
    sys.exit("✗ OLLAMA_API_KEY не задано у .env")
headers = {"Authorization": f"Bearer {KEY}"}

# 1. Список доступних моделей
r = requests.get(f"{HOST}/api/tags", headers=headers, timeout=30)
if r.status_code != 200:
    sys.exit(f"✗ Не вдалося отримати список моделей: HTTP {r.status_code} {r.text[:300]}")
names = sorted(m["name"] for m in r.json().get("models", []))
print(f"✓ З'єднання є, доступно моделей: {len(names)}")
print("  " + ", ".join(names))
if MODEL not in names:
    print(f"\n! Модель '{MODEL}' не знайдена у списку — перевір OLLAMA_MODEL у .env")

# 2. Тестовий запит
print(f"\nТестовий запит до {MODEL}...")
r = requests.post(f"{HOST}/api/chat", headers=headers, timeout=120, json={
    "model": MODEL,
    "stream": False,
    "messages": [{"role": "user", "content": "Напиши одне жартівливе речення українською про груповий чат друзів."}],
})
if r.status_code == 401:
    sys.exit("✗ 401: ключ невірний або відкликаний")
if r.status_code != 200:
    sys.exit(f"✗ HTTP {r.status_code}: {r.text[:500]}")
print("✓ Відповідь моделі:", r.json()["message"]["content"].strip())
print("\nВсе працює — можна запускати generate.py")
