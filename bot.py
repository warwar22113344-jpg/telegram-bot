import time
import random
import sqlite3
import threading
import telebot
from telebot import types

# =========================
# НАСТРОЙКИ БОТА
# =========================

TOKEN = "8761618655:AAFKc3bdwnK9WlCINaHjA_zG8DflMu68KYg"
ADMINS = {6838372946}

bot = telebot.TeleBot(TOKEN)

# =========================
# БАЗА ДАННЫХ
# =========================

db = sqlite3.connect("bot.db", check_same_thread=False)
cursor = db.cursor()
db_lock = threading.RLock()

with db_lock:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        balance INTEGER DEFAULT 1000,
        stash INTEGER DEFAULT 0,
        is_partner INTEGER DEFAULT 0,
        last_work REAL DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_businesses (
        user_id INTEGER,
        biz_id TEXT,
        stock INTEGER DEFAULT 0,
        selling INTEGER DEFAULT 0,
        lvl_storage INTEGER DEFAULT 0,
        lvl_profit INTEGER DEFAULT 0,
        lvl_speed INTEGER DEFAULT 0,
        last_process_time REAL DEFAULT 0,
        PRIMARY KEY (user_id, biz_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        owner_id INTEGER,
        reward INTEGER,
        uses_left INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promo_uses (
        user_id INTEGER,
        code TEXT,
        PRIMARY KEY (user_id, code)
    )
    """)

    db.commit()


# =========================
# БИЗНЕСЫ И РУЛЕТКА КОНФИГ
# =========================

BIZ_CONFIG = {
    "bakery": {"name": "Хлебобулочный завод", "buy_price": 50000, "base_storage": 120, "buy_raw_cost": 150, "base_income": 160, "base_speed": 10},
    "bar": {"name": "Бар (Стр#пуха)", "buy_price": 250000, "base_storage": 100, "buy_raw_cost": 300, "base_income": 330, "base_speed": 8},
    "kiosk": {"name": "Ларек", "buy_price": 12500, "base_storage": 100, "buy_raw_cost": 50, "base_income": 57, "base_speed": 10},
    "distillery": {"name": "Завод чекушек", "buy_price": 500000, "base_storage": 80, "buy_raw_cost": 600, "base_income": 680, "base_speed": 6}
}

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def format_money(amount):
    return f"{amount:,}".replace(",", ".")

def parse_amount(text, user_balance=0):
    text = text.lower().strip()
    if text in ["all", "алл", "вб", "все", "всё"]:
        return user_balance
    try:
        if text.endswith("ккк"):
            return int(float(text[:-3]) * 1_000_000_000)
        elif text.endswith("кк"):
            return int(float(text[:-2]) * 1_000_000)
        elif text.endswith("к"):
            return int(float(text[:-1]) * 1_000)
        return int(text)
    except ValueError:
        return None

def is_partner(user_id):
    if user_id in ADMINS:
        return True
    with db_lock:
        cursor.execute("SELECT is_partner FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return bool(res and res[0] == 1)

def get_user_data(user_id, first_name=None, username=None):
    with db_lock:
        cursor.execute("SELECT balance, stash, first_name, username, last_work FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        safe_name = telebot.formatting.escape_html(first_name or "Игрок")
        clean_username = username.lstrip("@").lower() if username else ""

        if user is None:
            cursor.execute(
                "INSERT INTO users (user_id, first_name, username, balance, stash, last_work) VALUES (?, ?, ?, 1000, 0, 0)",
                (user_id, safe_name, clean_username)
            )
            db.commit()
            return {"balance": 1000, "stash": 0, "first_name": safe_name, "last_work": 0}
        else:
            cursor.execute("UPDATE users SET first_name = ?, username = ? WHERE user_id = ?", (safe_name, clean_username, user_id))
            db.commit()
            return {"balance": user[0], "stash": user[1], "first_name": user[2], "last_work": user[4]}

def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Работы", "Заначка")
    markup.row("Бизнесы", "Казино")
    
    if is_partner(user_id):
        markup.row("Перевод", "Профиль", "Топ")
        markup.row("🤝 Партнёрка")
    else:
        markup.row("Перевод", "Профиль", "Топ")
        
    return markup


# =========================
# ОСНОВНЫЕ КОМАНДЫ
# =========================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    get_user_data(message.from_user.id, message.from_user.first_name, message.from_user.username)
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать!",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# Посмотреть свой баланс ("я", "баланс", "б")
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ["я", "баланс", "б"])
def my_balance_cmd(message):
    user_id = message.from_user.id
    u_data = get_user_data(user_id, message.from_user.first_name, message.from_user.username)
    partner_status = " (🤝 Партнёр)" if is_partner(user_id) else ""
    
    msg = (
        f"👤 <b>{u_data['first_name']}</b>{partner_status}\n"
        f"💰 <b>Баланс:</b> {format_money(u_data['balance'])}₸\n"
        f"📦 <b>Заначка:</b> {format_money(u_data['stash'])}₸"
    )
    bot.send_message(message.chat.id, msg, parse_mode="HTML")


# =========================
# АДМИНКА (ВЫДАЧА И СНЯТИЕ ПАРТНЁРКИ, ДЕНЬГИ)
# =========================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("выдать партнерку"))
def give_partner_status(message):
    user_id = message.from_user.id

    if user_id not in ADMINS:
        bot.send_message(message.chat.id, "❌ <b>У вас нет прав администратора!</b>", parse_mode="HTML")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.send_message(
            message.chat.id,
            "❌ <b>Использование:</b> <code>выдать партнерку @username</code> или <code>выдать партнерку ID</code>",
            parse_mode="HTML"
        )
        return

    target_input = parts[2].strip()

    with db_lock:
        if target_input.isdigit():
            target_id = int(target_input)
            cursor.execute("SELECT user_id, first_name, is_partner FROM users WHERE user_id = ?", (target_id,))
        else:
            clean_username = target_input.replace("@", "").lower()
            cursor.execute("SELECT user_id, first_name, is_partner FROM users WHERE LOWER(username) = ?", (clean_username,))
        
        target_user = cursor.fetchone()

        if not target_user:
            bot.send_message(
                message.chat.id,
                f"❌ Пользователь <b>{target_input}</b> не найден в базе данных!\n"
                f"<i>Убедитесь, что он нажал /start в боте.</i>",
                parse_mode="HTML"
            )
            return

        t_id, t_name, is_part = target_user

        if is_part:
            bot.send_message(message.chat.id, f"⚠️ Пользователь <b>{t_name}</b> уже имеет статус партнёра!", parse_mode="HTML")
            return

        cursor.execute("UPDATE users SET is_partner = 1 WHERE user_id = ?", (t_id,))
        db.commit()

    bot.send_message(
        message.chat.id,
        f"✅ Пользователю <b>{t_name}</b> (<code>{t_id}</code>) успешно выдан статус <b>🤝 Партнёр</b>!",
        parse_mode="HTML"
    )

    try:
        bot.send_message(
            t_id,
            "🎉 <b>Поздравляем!</b> Вам выдан статус <b>🤝 Партнёр</b>.\n"
            "Теперь вам доступна функция создания промокодов!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(t_id)
        )
    except Exception:
        pass


@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("убрать партнерку"))
def remove_partner_status(message):
    user_id = message.from_user.id

    if user_id not in ADMINS:
        bot.send_message(message.chat.id, "❌ <b>У вас нет прав администратора!</b>", parse_mode="HTML")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.send_message(
            message.chat.id,
            "❌ <b>Использование:</b> <code>убрать партнерку @username</code> или <code>убрать партнерку ID</code>",
            parse_mode="HTML"
        )
        return

    target_input = parts[2].strip()

    with db_lock:
        if target_input.isdigit():
            target_id = int(target_input)
            cursor.execute("SELECT user_id, first_name, is_partner FROM users WHERE user_id = ?", (target_id,))
        else:
            clean_username = target_input.replace("@", "").lower()
            cursor.execute("SELECT user_id, first_name, is_partner FROM users WHERE LOWER(username) = ?", (clean_username,))
        
        target_user = cursor.fetchone()

        if not target_user:
            bot.send_message(
                message.chat.id,
                f"❌ Пользователь <b>{target_input}</b> не найден в базе данных!",
                parse_mode="HTML"
            )
            return

        t_id, t_name, is_part = target_user

        if not is_part:
            bot.send_message(message.chat.id, f"⚠️ У пользователя <b>{t_name}</b> и так нет статуса партнёра.", parse_mode="HTML")
            return

        cursor.execute("UPDATE users SET is_partner = 0 WHERE user_id = ?", (t_id,))
        db.commit()

    bot.send_message(
        message.chat.id,
        f"✅ У пользователя <b>{t_name}</b> (<code>{t_id}</code>) успешно снят статус партнёра.",
        parse_mode="HTML"
    )

    try:
        bot.send_message(
            t_id,
            "⚠️ Ваш статус <b>🤝 Партнёр</b> был аннулирован администратором.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(t_id)
        )
    except Exception:
        pass


@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("выдать ") and not m.text.lower().startswith("выдать партнерку"))
def give_money(message):
    if message.from_user.id not in ADMINS:
        bot.send_message(message.chat.id, "❌ У вас нет прав администратора.")
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.send_message(message.chat.id, "❌ Использование: <code>выдать [@username/ID] [сумма]</code>", parse_mode="HTML")
        return

    target = parts[1]
    u_data = get_user_data(message.from_user.id)
    amount = parse_amount(parts[2], u_data["balance"])

    if amount is None or amount <= 0:
        bot.send_message(message.chat.id, "❌ Неверная сумма.")
        return

    with db_lock:
        if target.isdigit():
            target_id = int(target)
            cursor.execute("SELECT first_name, balance FROM users WHERE user_id = ?", (target_id,))
        else:
            username = target.lstrip("@").lower()
            cursor.execute("SELECT first_name, balance, user_id FROM users WHERE LOWER(username) = ? OR LOWER(first_name) = ?", (username, username))
        
        user = cursor.fetchone()
        if user is None:
            bot.send_message(message.chat.id, f"❌ Пользователь {target} не найден.")
            return

        if len(user) == 3:
            name, old_balance, target_id = user[0], user[1], user[2]
        else:
            name, old_balance = user[0], user[1]
            target_id = int(target)

        new_balance = old_balance + amount
        cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, target_id))
        db.commit()

    bot.send_message(
        message.chat.id,
        f"✅ Выдано игроку <b>{name}</b>: +{format_money(amount)}₸\n💰 Новый баланс: {format_money(new_balance)}₸",
        parse_mode="HTML"
    )


# =========================
# ПРОМОКОДЫ
# =========================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("промо "))
def use_promocode(message):
    user_id = message.from_user.id
    u_data = get_user_data(user_id, message.from_user.first_name, message.from_user.username)
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ <b>Использование:</b> <code>промо [название]</code>", parse_mode="HTML")
        return

    code = parts[1].strip().upper()

    with db_lock:
        cursor.execute("SELECT reward, uses_left FROM promocodes WHERE code = ?", (code,))
        promo = cursor.fetchone()

        if not promo:
            bot.send_message(message.chat.id, "❌ Промокод не найден или был удалён.", parse_mode="HTML")
            return

        reward, uses_left = promo[0], promo[1]

        if uses_left <= 0:
            bot.send_message(message.chat.id, "❌ У этого промокода закончились активации!", parse_mode="HTML")
            return

        cursor.execute("SELECT 1 FROM promo_uses WHERE user_id = ? AND code = ?", (user_id, code))
        if cursor.fetchone():
            bot.send_message(message.chat.id, "❌ Вы уже активировали этот промокод!", parse_mode="HTML")
            return

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))
        cursor.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        cursor.execute("INSERT INTO promo_uses (user_id, code) VALUES (?, ?)", (user_id, code))
        db.commit()

        new_balance = u_data["balance"] + reward

    bot.send_message(
        message.chat.id,
        f"🎉 <b>Промокод активирован!</b>\n\n"
        f"💰 Вам начислено: <b>+{format_money(reward)}₸</b>\n"
        f"💳 Ваш баланс: <b>{format_money(new_balance)}₸</b>",
        parse_mode="HTML"
    )


@bot.message_handler(func=lambda m: m.text and m.text.strip() == "🤝 Партнёрка")
def partner_panel(message):
    user_id = message.from_user.id
    if not is_partner(user_id):
        bot.send_message(message.chat.id, "❌ Нет доступа.")
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎁 Создать промокод", callback_data="partner_create_promo"))
    bot.send_message(message.chat.id, "🤝 <b>Панель партнёра</b>\n\nСоздавайте промокоды для игроков!", parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "partner_create_promo")
def start_promo_creation(call):
    if not is_partner(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Доступ запрещён!", show_alert=True)
        return

    msg = bot.send_message(call.message.chat.id, "✏️ <b>Шаг 1 из 3:</b> Введите название промокода:", parse_mode="HTML")
    bot.register_next_step_handler(msg, step_promo_code)
    bot.answer_callback_query(call.id)

def step_promo_code(message):
    code = message.text.strip().upper()
    with db_lock:
        cursor.execute("SELECT code FROM promocodes WHERE code = ?", (code,))
        if cursor.fetchone():
            bot.send_message(message.chat.id, "❌ Такой код уже существует!")
            return

    msg = bot.send_message(message.chat.id, f"💰 <b>Шаг 2 из 3:</b> Введите сумму награды:", parse_mode="HTML")
    bot.register_next_step_handler(msg, step_promo_reward, code)

def step_promo_reward(message, code):
    u_data = get_user_data(message.from_user.id)
    reward = parse_amount(message.text, u_data["balance"])
    if reward is None or reward <= 0:
        bot.send_message(message.chat.id, "❌ Ошибка в сумме.")
        return

    msg = bot.send_message(message.chat.id, "👥 <b>Шаг 3 из 3:</b> Введите количество человек (активаций):", parse_mode="HTML")
    bot.register_next_step_handler(msg, step_promo_uses, code, reward)

def step_promo_uses(message, code, reward):
    try:
        uses = int(message.text.strip())
    except ValueError:
        uses = None

    if uses is None or uses <= 0:
        bot.send_message(message.chat.id, "❌ Ошибка в количестве.")
        return

    with db_lock:
        cursor.execute("INSERT INTO promocodes (code, owner_id, reward, uses_left) VALUES (?, ?, ?, ?)", (code, message.from_user.id, reward, uses))
        db.commit()

    bot.send_message(message.chat.id, f"🎉 <b>Промокод создан!</b>\n\n🎁 Код: <code>{code}</code>\n💰 Награда: {format_money(reward)}₸\n👥 Активаций: {uses}", parse_mode="HTML")


# =========================
# РУЛЕТКА
# =========================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("рул "))
def roulette_game(message):
    user_id = message.from_user.id
    u_data = get_user_data(user_id, message.from_user.first_name, message.from_user.username)

    parts = message.text.split()
    if len(parts) < 3:
        bot.send_message(message.chat.id, "❌ Формат: <code>рул [ставка] [сумма]</code>\nПример: <code>рул кра 5000</code>", parse_mode="HTML")
        return

    if len(parts) == 4 and parts[1].lower() in ["кра", "красное", "чер", "черное", "чёрное"]:
        raw_bet = parts[2].lower()
        raw_amount = parts[3]
    else:
        raw_bet = parts[1].lower()
        raw_amount = parts[2]

    amount = parse_amount(raw_amount, u_data["balance"])

    if amount is None or amount <= 0:
        bot.send_message(message.chat.id, "❌ Укажите корректную сумму ставки!")
        return

    if u_data["balance"] < amount:
        bot.send_message(message.chat.id, f"❌ Недостаточно средств! Твой баланс: {format_money(u_data['balance'])}₸")
        return

    winning_num = random.randint(0, 36)
    
    if winning_num == 0:
        color_str = "🟢 Зеро (0)"
    elif winning_num in RED_NUMBERS:
        color_str = f"🔴 {winning_num} (Красное)"
    else:
        color_str = f"⚫ {winning_num} (Чёрное)"

    is_win = False
    multiplier = 0

    if raw_bet.isdigit() and 0 <= int(raw_bet) <= 36:
        if winning_num == int(raw_bet):
            is_win = True
            multiplier = 20
    elif raw_bet in ["зеро", "0"]:
        if winning_num == 0:
            is_win = True
            multiplier = 20
    elif raw_bet in ["красное", "кра", "red"]:
        if winning_num in RED_NUMBERS:
            is_win = True
            multiplier = 2
    elif raw_bet in ["чёрное", "черное", "чер", "black"]:
        if winning_num in BLACK_NUMBERS:
            is_win = True
            multiplier = 2
    elif raw_bet in ["чёт", "чет", "even"]:
        if winning_num != 0 and winning_num % 2 == 0:
            is_win = True
            multiplier = 2
    elif raw_bet in ["нечёт", "нечет", "odd"]:
        if winning_num % 2 != 0:
            is_win = True
            multiplier = 2
    elif raw_bet in ["маленькое", "мал", "1-18"]:
        if 1 <= winning_num <= 18:
            is_win = True
            multiplier = 2
    elif raw_bet in ["большое", "бол", "19-36"]:
        if 19 <= winning_num <= 36:
            is_win = True
            multiplier = 2
    elif raw_bet in ["1-12", "112"]:
        if 1 <= winning_num <= 12:
            is_win = True
            multiplier = 3
    elif raw_bet in ["13-24", "1324"]:
        if 13 <= winning_num <= 24:
            is_win = True
            multiplier = 3
    elif raw_bet in ["25-36", "2536"]:
        if 25 <= winning_num <= 36:
            is_win = True
            multiplier = 3
    elif raw_bet in ["1ряд", "ряд1", "1-ряд"]:
        if winning_num != 0 and winning_num % 3 == 1:
            is_win = True
            multiplier = 3
    elif raw_bet in ["2ряд", "ряд2", "2-ряд"]:
        if winning_num != 0 and winning_num % 3 == 2:
            is_win = True
            multiplier = 3
    elif raw_bet in ["3ряд", "ряд3", "3-ряд"]:
        if winning_num != 0 and winning_num % 3 == 0:
            is_win = True
            multiplier = 3
    else:
        bot.send_message(message.chat.id, "❌ Неизвестная ставка! Нажмите на <b>Казино</b> для справки.", parse_mode="HTML")
        return

    with db_lock:
        if is_win:
            win_amount = amount * multiplier
            profit = win_amount - amount
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (profit, user_id))
            db.commit()
            new_bal = u_data["balance"] + profit

            msg = (
                f"🎰 <b>Рулетка</b>\n\n"
                f"Выпало: <b>{color_str}</b>\n"
                f"🎉 Вы выиграли <b>+{format_money(win_amount)}₸</b> (x{multiplier})!\n"
                f"💰 Ваш баланс: {format_money(new_bal)}₸"
            )
        else:
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            db.commit()
            new_bal = u_data["balance"] - amount

            msg = (
                f"🎰 <b>Рулетка</b>\n\n"
                f"Выпало: <b>{color_str}</b>\n"
                f"❌ Вы проиграли <b>-{format_money(amount)}₸</b>\n"
                f"💰 Ваш баланс: {format_money(new_bal)}₸"
            )

    bot.send_message(message.chat.id, msg, parse_mode="HTML")


# =========================
# КНОПКИ МЕНЮ
# =========================

@bot.message_handler(func=lambda m: m.text in ["Работы", "Заначка", "Бизнесы", "Казино", "Перевод", "Профиль", "Топ"])
def handle_text_buttons(message):
    user_id = message.from_user.id
    text = message.text
    data = get_user_data(user_id, message.from_user.first_name, message.from_user.username)

    if text == "Профиль":
        partner_status = " (🤝 Партнёр)" if is_partner(user_id) else ""
        msg = (
            f"👤 <b>Твой профиль:</b>\n\n"
            f"🏷 <b>Ник:</b> {data['first_name']}{partner_status}\n"
            f"💰 <b>Баланс:</b> {format_money(data['balance'])}₸\n"
            f"📦 <b>Заначка:</b> {format_money(data['stash'])}₸"
        )
        bot.send_message(message.chat.id, msg, parse_mode="HTML")

    elif text == "Казино":
        casino_msg = (
            "🎰 <b>Рулетка</b>\n\n"
            "📌 <b>Используй:</b> <code>рул [ставка] [сумма]</code>\n\n"
            "<b>Ставки:</b>\n"
            "• 🔴 <code>красное</code> / <code>кра</code> — x2\n"
            "• ⚫ <code>чёрное</code> / <code>чер</code> — x2\n"
            "• 🟢 <code>зеро</code> — x20\n"
            "• 🎯 <code>число 0–36</code> — x20\n"
            "• ⚪ <code>чёт</code> / <code>нечёт</code> — x2\n"
            "• 🔽 <code>мал</code> (1–18) — x2\n"
            "• 🔼 <code>бол</code> (19–36) — x2\n"
            "• 🔢 <code>1-12</code> / <code>13-24</code> / <code>25-36</code> — x3\n"
            "• 1️⃣ <code>1ряд</code> — x3\n"
            "• 2️⃣ <code>2ряд</code> — x3\n"
            "• 3️⃣ <code>3ряд</code> — x3\n\n"
            "💡 <b>Примеры:</b>\n"
            "<code>рул кра 15кк</code>\n"
            "<code>рул 17 5кк</code>\n"
            "<code>рул 1-12 10к</code>\n"
            "<code>рул чер вб</code>"
        )
        bot.send_message(message.chat.id, casino_msg, parse_mode="HTML")

    elif text == "Работы":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Работать", callback_data="work_do"))
        bot.send_message(message.chat.id, "🛠 <b>Работы</b>\n\n• Работа — 10.000–15.000₸ (КД 30 сек)", parse_mode="HTML", reply_markup=markup)

    elif text == "Заначка":
        bot.send_message(message.chat.id, f"📦 <b>Заначка</b>\n\nВ кармане: {format_money(data['balance'])}₸\nВ заначке: {format_money(data['stash'])}₸", parse_mode="HTML")

    elif text == "Бизнесы":
        show_businesses_menu(message)

    elif text == "Перевод":
        bot.send_message(message.chat.id, "💸 <b>Перевод</b>\n\nОтветьте на сообщение игрока командой:\n<code>перевод [сумма]</code>", parse_mode="HTML")

    elif text == "Топ":
        with db_lock:
            cursor.execute("SELECT first_name, balance FROM users ORDER BY balance DESC LIMIT 10")
            players = cursor.fetchall()

        msg = "🏆 <b>ТОП-10 игроков:</b>\n\n"
        for i, (name, bal) in enumerate(players, 1):
            msg += f"{i}. <b>{name}</b> — {format_money(bal)}₸\n"
        bot.send_message(message.chat.id, msg, parse_mode="HTML")


# =========================
# МЕНЮ БИЗНЕСОВ
# =========================

def show_businesses_menu(message):
    user_id = message.from_user.id
    markup = types.InlineKeyboardMarkup()
    for b_id, b_info in BIZ_CONFIG.items():
        user_b = get_user_biz(user_id, b_id)
        status = "— твоё" if user_b else f"— {format_money(b_info['buy_price'])}₸"
        markup.add(types.InlineKeyboardButton(f"{b_info['name']} {status}", callback_data=f"biz_open_{b_id}"))

    msg = "🏢 <b>Бизнесы</b>\n\nЗакупай сырьё и запускай продажи.\nДеньги приходят постепенно."
    bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=markup)

def get_user_biz(user_id, biz_id):
    with db_lock:
        cursor.execute("SELECT stock, selling, lvl_storage, lvl_profit, lvl_speed, last_process_time FROM user_businesses WHERE user_id = ? AND biz_id = ?", (user_id, biz_id))
        res = cursor.fetchone()
        if not res: return None
        return {"stock": res[0], "selling": res[1], "lvl_storage": res[2], "lvl_profit": res[3], "lvl_speed": res[4], "last_process_time": res[5]}

def process_business_sales(user_id, biz_id):
    biz = get_user_biz(user_id, biz_id)
    if not biz or biz["selling"] <= 0: return biz
    config = BIZ_CONFIG[biz_id]
    speed = max(1, config["base_speed"] - biz["lvl_speed"])
    now = time.time()
    elapsed = now - biz["last_process_time"]
    items_sold = int(elapsed // speed)

    if items_sold > 0:
        actual_sold = min(items_sold, biz["selling"])
        income_per_item = config["base_income"] + (biz["lvl_profit"] * 2)
        total_earned = actual_sold * income_per_item
        new_selling = biz["selling"] - actual_sold
        new_process_time = biz["last_process_time"] + (actual_sold * speed)

        with db_lock:
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_earned, user_id))
            cursor.execute("UPDATE user_businesses SET selling = ?, last_process_time = ? WHERE user_id = ? AND biz_id = ?", (new_selling, new_process_time, user_id, biz_id))
            db.commit()

        biz["selling"] = new_selling
        biz["last_process_time"] = new_process_time
    return biz

def render_biz_page(chat_id, message_id, user_id, biz_id):
    config = BIZ_CONFIG.get(biz_id)
    if not config: return

    biz = process_business_sales(user_id, biz_id)
    
    if not biz:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"Купить — {format_money(config['buy_price'])}₸", callback_data=f"biz_buy_{biz_id}"))
        bot.edit_message_text(f"🏪 <b>{config['name']}</b>\n\nУ вас еще нет этого бизнеса.", chat_id, message_id, parse_mode="HTML", reply_markup=markup)
        return

    max_storage = config["base_storage"] + (biz["lvl_storage"] * 20)
    income_per_item = config["base_income"] + (biz["lvl_profit"] * 2)
    profit_diff = income_per_item - config["buy_raw_cost"]
    speed = max(1, config["base_speed"] - biz["lvl_speed"])

    msg_text = (
        f"🏪 <b>{config['name']}</b>\n\n"
        f"Сырья на складе: <b>{biz['stock']} / {max_storage}</b>\n"
        f"Сейчас продаётся: <b>{biz['selling']} шт.</b>\n\n"
        f"Закупка: {config['buy_raw_cost']}₸ / шт.\n"
        f"Доход с продажи: {income_per_item}₸ / шт.\n"
        f"Прибыль: +{profit_diff}₸ / шт.\n\n"
        f"Скорость продажи: 1 шт. / {speed} сек.\n"
        f"Улучшения: склад ур.{biz['lvl_storage']} • прибыль ур.{biz['lvl_profit']} • скорость ур.{biz['lvl_speed']}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📦 Купить сырьё", callback_data=f"biz_raw_{biz_id}"))
    markup.add(types.InlineKeyboardButton("🚀 Запустить продажу", callback_data=f"biz_start_{biz_id}"))
    markup.add(types.InlineKeyboardButton("🔄 Обновить", callback_data=f"biz_open_{biz_id}"))
    
    try:
        bot.edit_message_text(msg_text, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data.startswith(("biz_", "work_")))
def handle_callbacks(call):
    user_id = call.from_user.id

    if call.data == "work_do":
        data = get_user_data(user_id)
        now = time.time()
        cd_left = int(30 - (now - data["last_work"]))
        if cd_left > 0:
            bot.answer_callback_query(call.id, f"⏳ Отдохни еще {cd_left} сек.!", show_alert=True)
            return

        earned = random.randint(10000, 15000)
        with db_lock:
            cursor.execute("UPDATE users SET balance = balance + ?, last_work = ? WHERE user_id = ?", (earned, now, user_id))
            db.commit()

        bot.answer_callback_query(call.id, f"✅ Ты заработал +{format_money(earned)}₸!", show_alert=True)
        return

    if call.data.startswith("biz_"):
        parts = call.data.split("_")
        action = parts[1]
        biz_id = parts[2]
        config = BIZ_CONFIG.get(biz_id)
        if not config: return

        if action == "open":
            render_biz_page(call.message.chat.id, call.message.message_id, user_id, biz_id)
            bot.answer_callback_query(call.id)

        elif action == "buy":
            biz = get_user_biz(user_id, biz_id)
            if biz:
                bot.answer_callback_query(call.id, "У вас уже есть этот бизнес!", show_alert=True)
                return

            u_data = get_user_data(user_id)
            if u_data["balance"] < config["buy_price"]:
                bot.answer_callback_query(call.id, f"❌ Недостаточно средств! Нужно {format_money(config['buy_price'])}₸", show_alert=True)
                return

            with db_lock:
                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (config["buy_price"], user_id))
                cursor.execute("INSERT INTO user_businesses (user_id, biz_id, last_process_time) VALUES (?, ?, ?)", (user_id, biz_id, time.time()))
                db.commit()

            bot.answer_callback_query(call.id, "🎉 Поздравляем с покупкой бизнеса!", show_alert=True)
            render_biz_page(call.message.chat.id, call.message.message_id, user_id, biz_id)

        elif action == "raw":
            biz = get_user_biz(user_id, biz_id)
            if not biz: return

            max_storage = config["base_storage"] + (biz["lvl_storage"] * 20)
            space_left = max_storage - biz["stock"]

            if space_left <= 0:
                bot.answer_callback_query(call.id, "📦 Склад полон!", show_alert=True)
                return

            u_data = get_user_data(user_id)
            can_afford = u_data["balance"] // config["buy_raw_cost"]
            to_buy = min(space_left, can_afford)

            if to_buy <= 0:
                bot.answer_callback_query(call.id, f"❌ Недостаточно денег! 1 шт. стоит {config['buy_raw_cost']}₸", show_alert=True)
                return

            total_cost = to_buy * config["buy_raw_cost"]

            with db_lock:
                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_cost, user_id))
                cursor.execute("UPDATE user_businesses SET stock = stock + ? WHERE user_id = ? AND biz_id = ?", (to_buy, user_id, biz_id))
                db.commit()

            bot.answer_callback_query(call.id, f"✅ Куплено {to_buy} шт. сырья за {format_money(total_cost)}₸", show_alert=True)
            render_biz_page(call.message.chat.id, call.message.message_id, user_id, biz_id)

        elif action == "start":
            biz = process_business_sales(user_id, biz_id)
            if not biz: return

            if biz["stock"] <= 0:
                bot.answer_callback_query(call.id, "❌ На складе нет сырья для продажи!", show_alert=True)
                return

            stock_to_sell = biz["stock"]

            with db_lock:
                cursor.execute("UPDATE user_businesses SET stock = 0, selling = selling + ?, last_process_time = ? WHERE user_id = ? AND biz_id = ?", (stock_to_sell, time.time(), user_id, biz_id))
                db.commit()

            bot.answer_callback_query(call.id, f"🚀 Отправлено в продажу: {stock_to_sell} шт.", show_alert=True)
            render_biz_page(call.message.chat.id, call.message.message_id, user_id, biz_id)


# =========================
# ЗАПУСК БОТА
# =========================

if __name__ == "__main__":
    print("Бот успешно запущен!")
    bot.infinity_polling(skip_pending=True)
	
