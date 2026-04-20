import discord
from discord.ext import commands
import os
import sqlite3
import datetime
import io
import re
import requests
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- ЗАГРУЗКА НАСТРОЕК ---
# Все токены должны быть прописаны в Environment Variables на Render
load_dotenv()
TOKEN = os.getenv('MTQ4NjczNzczNjYyNTk1MDg2MA.GW0WTM.PG1BOuqJiv0IwdBmYLpc9Hx6GosFtld7pkKc-o')
ADMIN_ID = os.getenv('ADMIN_ID')
VK_TOKEN = os.getenv('vk1.a.gg0A2uqhaeJR4Q0rQroAOrKxLtlld-zpDhUuNRsLph2tyJZzoyIioGN8vNs_AzCfepKFqTdigONU-ydz1VZnL68Ns7qZ0HcgUhmEOE_F1ZI26awIwunbGfzTpn-xmEEXAueaaBR5lb-ew_z478YoxYuNlAEHHfGBddR9u10-MJae6l1UUC4C3eKWD28ugFy7hhguP-Ihcxsb42Fbq_SPsw')

if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- БАЗА ДАННЫХ (SQLite) ---
db = sqlite3.connect('osint_system.db')
cursor = db.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
               (user_id INTEGER PRIMARY KEY, sub_until TEXT, requests_today INTEGER, last_req_date TEXT)''')
db.commit()

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (Защита от засыпания и ошибок порта) ---
app = Flask('')
@app.route('/')
def home(): return "OSINT Bot Status: Online"

def run():
    # Render автоматически назначает порт, мы его считываем
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- МОДУЛИ ПОИСКА (РЕАЛЬНЫЕ ДАННЫЕ) ---

def get_ip_info(ip):
    try:
        # Используем расширенные поля ip-api
        res = requests.get(f"http://ip-api.com/json/{ip}?fields=66846719").json()
        if res.get('status') == 'fail': 
            return f"❌ Ошибка: {res.get('message', 'IP не найден')}"
        
        report = f"""
╔══════════════════════════════════════════╗
         OSINT REPORT: IP ADDRESS
╚══════════════════════════════════════════╝

[+] ОСНОВНАЯ ИНФОРМАЦИЯ
    ● IP: {ip}
    ● Статус: Активен
    ● Тип: IPv4

[+] ГЕОЛОКАЦИЯ
    ● Страна: {res.get('country', 'Н/Д')} ({res.get('countryCode', '??')})
    ● Регион: {res.get('regionName', 'Н/Д')}
    ● Город: {res.get('city', 'Н/Д')}
    ● Индекс: {res.get('zip', 'Н/Д')}
    ● Координаты: {res.get('lat')}, {res.get('lon')}
    ● Таймзона: {res.get('timezone')}

[+] ПРОВАЙДЕР И СЕТЬ
    ● ISP: {res.get('isp', 'Н/Д')}
    ● Организация: {res.get('org', 'Н/Д')}
    ● AS: {res.get('as', 'Н/Д')}

[+] БЕЗОПАСНОСТЬ И РИСКИ
    ● Использование Proxy: {'⚠️ ОБНАРУЖЕНО' if res.get('proxy') else '✅ Чисто'}
    ● Мобильная сеть: {'Да' if res.get('mobile') else 'Нет'}
    ● Хостинг/Сервер: {'Да' if res.get('hosting') else 'Нет'}

[+] ДОПОЛНИТЕЛЬНО
    ● Сгенерировано: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
============================================
"""
        return report
    except Exception as e: 
        return f"Критическая ошибка модуля IP: {str(e)}"

def get_vk_info(target):
    user_id = target.split('/')[-1] if '/' in target else target
    try:
        params = {
            "user_ids": user_id, 
            "fields": "bdate,city,counters,last_seen,verified,followers_count,status,connections", 
            "access_token": VK_TOKEN, 
            "v": "5.131"
        }
        res = requests.get("https://api.vk.com/method/users.get", params=params).json()
        
        if 'error' in res: 
            return f"❌ Ошибка ВК: {res['error']['error_msg']}"
        
        d = res['response'][0]
        ls_text = "Скрыто"
        if 'last_seen' in d:
            ls_time = datetime.datetime.fromtimestamp(d['last_seen']['time'])
            ls_text = ls_time.strftime('%d.%m.%Y %H:%M:%S')

        report = f"""
╔══════════════════════════════════════════╗
         OSINT REPORT: VKONTAKTE
╚══════════════════════════════════════════╝

[+] ПРОФИЛЬ
    ● Имя Фамилия: {d.get('first_name')} {d.get('last_name')}
    ● ID: {d.get('id')}
    ● Ссылка: https://vk.com/id{d.get('id')}
    ● Верификация: {'✅ Подтвержден' if d.get('verified') else 'Нет'}

[+] ПЕРСОНАЛЬНЫЕ ДАННЫЕ
    ● День рождения: {d.get('bdate', 'Скрыт')}
    ● Город: {d.get('city', {}).get('title', 'Не указан')}
    ● Статус: {d.get('status', 'Пусто')}

[+] СТАТИСТИКА
    ● Друзей: {d.get('counters', {}).get('friends', 0)}
    ● Подписчиков: {d.get('followers_count', 0)}
    ● Фото: {d.get('counters', {}).get('photos', 0)}

[+] АКТИВНОСТЬ
    ● Последний вход: {ls_text}
    ● Устройство: {'Мобильное' if d.get('last_seen', {}).get('platform') in [1,2,3,4,5] else 'Компьютер'}

[+] СВЯЗИ (УТЕЧКИ)
    ● Skype: {d.get('skype', 'Н/Д')}
    ● Instagram: {d.get('instagram', 'Н/Д')}
    ● Twitter: {d.get('twitter', 'Н/Д')}

[+] ДОПОЛНИТЕЛЬНО
    ● Дата отчета: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
============================================
"""
        return report
    except Exception as e: 
        return f"Критическая ошибка модуля VK: {str(e)}"

# --- КОМАНДЫ БОТА ---

@bot.command()
async def search(ctx, *, target: str):
    user_id = ctx.author.id
    today = str(datetime.date.today())
    
    # Работа с базой и лимитами
    cursor.execute("SELECT sub_until, requests_today, last_req_date FROM users WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    
    if not data:
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (user_id, "2000-01-01", 0, today))
        db.commit()
        data = ("2000-01-01", 0, today)

    sub_until, req_count, last_date = data
    is_prem = datetime.datetime.strptime(sub_until, '%Y-%m-%d').date() >= datetime.date.today()
    
    # Установка лимитов: 50 для према, 2 для обычных
    limit = 50 if is_prem else 2

    if last_date != today:
        req_count = 0

    if req_count >= limit:
        return await ctx.send(f"⚠️ Лимит запросов исчерпан ({req_count}/{limit}).")

    await ctx.send("🔍 Сканирование баз данных...")
    
    # Определение типа запроса
    if re.match(r'^(?:\d{1,3}\.){3}\d{1,3}$', target):
        result_text = get_ip_info(target)
    else:
        result_text = get_vk_info(target)

    # Генерация и отправка файла
    file_bytes = io.BytesIO(result_text.encode('utf-8'))
    discord_file = discord.File(file_bytes, filename=f"REPORT_{target}.txt")
    
    try:
        await ctx.author.send(content=f"📄 Ваш отчет по запросу: `{target}`", file=discord_file)
        await ctx.send(f"✅ Отчет успешно отправлен в ЛС! (Использовано: {req_count + 1}/{limit})")
    except discord.Forbidden:
        await ctx.send("❌ Не могу отправить файл! Откройте личные сообщения в настройках сервера.")

    # Обновление лимитов в БД
    cursor.execute("UPDATE users SET requests_today = ?, last_req_date = ? WHERE user_id = ?", (req_count + 1, today, user_id))
    db.commit()

@bot.command()
async def add_sub(ctx, member: discord.Member, days: int):
    if ctx.author.id != ADMIN_ID:
        return await ctx.send("❌ Доступ запрещен.")
    
    new_date = str(datetime.date.today() + datetime.timedelta(days=days))
    cursor.execute("UPDATE users SET sub_until = ? WHERE user_id = ?", (new_date, member.id))
    db.commit()
    await ctx.send(f"💎 Пользователю {member.mention} выдана подписка до **{new_date}**")

@bot.event
async def on_ready():
    print(f">>> Бот {bot.user} успешно запущен!")
    print(f">>> Админ ID: {ADMIN_ID}")

# --- ЗАПУСК ---
keep_alive()

if TOKEN:
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")
else:
    print("КРИТИЧЕСКАЯ ОШИБКА: DISCORD_TOKEN не задан!")
