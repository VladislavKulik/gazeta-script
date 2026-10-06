"""Крок 5: перший вхід в акаунт + список груп, щоб знайти ID потрібного чату.
Асинхронна версія — сумісна з Python 3.11–3.14."""
import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]


async def main():
    # При першому запуску попросить номер телефону, код і пароль 2FA (якщо є).
    # Код приходить у застосунок Telegram (чат "Telegram" з синьою галочкою), а не SMS.
    client = TelegramClient("newspaper", API_ID, API_HASH)
    await client.start()
    try:
        me = await client.get_me()
        print(f"Увійшли як: {me.first_name} (@{me.username})\n")
        print("ID\t\t\tНазва")
        async for d in client.iter_dialogs():
            if d.is_group:
                print(f"{d.id}\t{d.name}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
