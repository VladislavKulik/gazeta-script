"""Вхід в акаунт через QR-код — без коду підтвердження.
Скануєш QR телефоном: Telegram -> Налаштування -> Пристрої -> Підключити пристрій.
Після успіху з'явиться newspaper.session, і list_chats.py / export.py працюватимуть без входу."""
import asyncio
import getpass
import os
import sys

import qrcode
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
QR_FILE = "login_qr.png"


def show_qr(url: str):
    # 1) у терміналі
    q = qrcode.QRCode(border=1)
    q.add_data(url)
    q.print_ascii(invert=True)
    # 2) картинкою — якщо в терміналі QR погано видно
    qrcode.make(url).save(QR_FILE)
    if sys.platform == "win32":
        os.startfile(QR_FILE)
    print(f"\nQR також збережено у {QR_FILE}. Діє ~30 с, потім оновиться автоматично.")


async def main():
    client = TelegramClient("newspaper", API_ID, API_HASH)
    await client.connect()
    try:
        if await client.is_user_authorized():
            print("Вже авторизовано — можна запускати list_chats.py")
            return

        qr = await client.qr_login()
        while True:
            show_qr(qr.url)
            try:
                await qr.wait(timeout=30)
                break
            except asyncio.TimeoutError:
                print("QR прострочився, генерую новий...\n")
                await qr.recreate()
            except SessionPasswordNeededError:
                pw = getpass.getpass("Увімкнена двоетапна перевірка. Введи хмарний пароль: ")
                await client.sign_in(password=pw)
                break

        me = await client.get_me()
        print(f"\nУспішно! Увійшли як {me.first_name} (@{me.username})")
    finally:
        await client.disconnect()
        if os.path.exists(QR_FILE):
            try:
                os.remove(QR_FILE)
            except OSError:
                pass


if __name__ == "__main__":
    asyncio.run(main())
