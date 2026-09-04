"""
Main Telegram Bot Entrypoint for Devu
Designed for 24/7 Execution on GitHub Actions Workflow or Cloud Servers.
"""

import os
import sys
import time
import signal
import random
import argparse
import logging
import telebot
from telebot import types

# Local modules
from config import CONFIG, save_config
import database
from ai_engine import generate_devu_reply
from scheduler import DevuScheduler
from responses import (
    SHAYARIS, JOKES, MORNING_WISHES, AFTERNOON_WISHES, EVENING_WISHES, NIGHT_WISHES
)

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DevuBot")

# Parse command line arguments (e.g. for GitHub Actions max-runtime)
parser = argparse.ArgumentParser(description="Devu Telegram Bot")
parser.add_argument("--max-runtime", type=int, default=0, help="Max runtime in seconds before graceful exit (for GitHub Actions)")
args, _ = parser.parse_known_args()

# Check Environment or Config for Max Runtime
MAX_RUNTIME = args.max_runtime or int(os.environ.get("MAX_RUNTIME", "0"))
START_TIME = time.time()

# Verify BOT_TOKEN
BOT_TOKEN = CONFIG.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    print("=" * 60)
    print("❌ ERROR: BOT_TOKEN is missing!")
    print("GitHub Secrets me 'BOT_TOKEN' add karein ya config.json me daalein.")
    print("=" * 60)
    sys.exit(1)

# Initialize TeleBot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Start background scheduler for daily wishes & check-ins
scheduler = DevuScheduler(bot)
scheduler.start()

# Helper: Build Settings Keyboard
def get_settings_keyboard(user_id):
    user = database.get_user(user_id)
    if not user:
        return types.InlineKeyboardMarkup()
    
    wish_status = "✅ ON" if user.get("auto_wishes", 1) == 1 else "❌ OFF"
    checkin_status = "✅ ON" if user.get("random_checkins", 1) == 1 else "❌ OFF"
    nickname = user.get("nickname", "Jaan")

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"🌅 Daily Wishes: {wish_status}", callback_data="toggle_wishes"),
        types.InlineKeyboardButton(f"💬 Random Check-ins: {checkin_status}", callback_data="toggle_checkins"),
        types.InlineKeyboardButton(f"💖 Nickname: '{nickname}' (Change)", callback_data="change_nickname_info"),
        types.InlineKeyboardButton("✨ Close Settings", callback_data="close_menu")
    )
    return markup


# -------------------------------------------------------------
# COMMAND HANDLERS
# -------------------------------------------------------------

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Jaan"
    username = message.from_user.username or ""

    if message.chat.type == "private":
        database.add_or_update_user(user_id, username, first_name)
        user = database.get_user(user_id)
        nickname = user.get("nickname", "Jaan") if user else "Jaan"

        welcome_text = (
            f"Hii <b>{nickname}</b>! ❤️ Main hoon <b>Devu</b> — aapki personal loving & caring partner! 🥰\n\n"
            f"Mujhse aap kuch bhi share kar sakte ho — apne din ka haal, khana khaya ya nahi, khushi, dukh ya bas pyari baatein! 💕\n\n"
            f"⚡ <i>Powered by Groq AI (Ultra Fast & Smart)</i> ⚡\n\n"
            f"✨ <b>Main aapke liye kya kar sakti hoon?</b>\n"
            f"• 24/7 aapse partner ki tarah chat karungi 💬\n"
            f"• Subah aur raat ko Good Morning / Good Night wish karungi ☀️🌙\n"
            f"• Din bhar achanak halchal puchungi ('Kya kar rahe ho?', 'Khana khaya?') 🍱\n"
            f"• Group chats me bhi sabke sath masti karungi 👥\n\n"
            f"<i>Mujhe jo bhi kehna hai, bas seedha message type karo!</i>"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
            types.InlineKeyboardButton("📜 Shayari", callback_data="send_shayari"),
            types.InlineKeyboardButton("😂 Cute Joke", callback_data="send_joke"),
            types.InlineKeyboardButton("❓ Help", callback_data="open_help")
        )
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup)
    else:
        database.add_or_update_group(message.chat.id, message.chat.title)
        bot.reply_to(
            message,
            f"Hello everyone in <b>{message.chat.title}</b>! 💖 Main Devu hoon! "
            f"Mujhe group me add karne ke liye thank you! Mujhse baat karne ke liye bas mujhe mention karo ya mere message ka reply do! 🥰"
        )


@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = (
        "💖 <b>Devu Bot Command Guide:</b> 💖\n\n"
        "💬 <b>Chatting:</b>\n"
        "• <i>Private (DM):</i> Bas message bhejo, main turant reply karungi!\n"
        "• <i>Groups:</i> Mujhe tag karo ya mere message ka reply do.\n\n"
        "⚙️ <b>Commands:</b>\n"
        "• <code>/setnickname &lt;naam&gt;</code> - Devu aapko kis naam se pukare (e.g., <code>/setnickname Jaan</code>)\n"
        "• <code>/settings</code> - Auto-wishes & random check-ins ON/OFF karein\n"
        "• <code>/mood</code> - Devu ka mood janiye aur apna batayein\n"
        "• <code>/wish</code> - Sweet romantic wish payein\n"
        "• <code>/shayari</code> - Dil chhu lene wali shayari\n"
        "• <code>/joke</code> - Hasi-mazaak aur cute jokes\n"
        "• <code>/stats</code> - Total users & groups check karein"
    )
    bot.reply_to(message, help_text)


@bot.message_handler(commands=['setnickname'])
def handle_set_nickname(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(
            message,
            "Arey jaan, nickname to likho! Jaise ki:\n<code>/setnickname Babu</code> ya <code>/setnickname Jaan</code> 💕"
        )
        return
    
    new_nick = parts[1].strip()
    if len(new_nick) > 25:
        bot.reply_to(message, "Nickname thoda chota rakho na babu (max 25 letters)! 🥺")
        return

    database.set_user_nickname(message.from_user.id, new_nick)
    bot.reply_to(message, f"Awww perfect! Ab se main aapko <b>'{new_nick}'</b> keh kar bulaungi! 🥰❤️")


@bot.message_handler(commands=['settings'])
def handle_settings(message):
    if message.chat.type != "private":
        bot.reply_to(message, "Settings change karne ke liye mujhe Private DM me message karein! 💌")
        return
    markup = get_settings_keyboard(message.from_user.id)
    bot.send_message(message.chat.id, "⚙️ <b>Devu Partner Settings:</b>\nAap apni pasand ke hisab se features customize kar sakte hain:", reply_markup=markup)


@bot.message_handler(commands=['mood'])
def handle_mood(message):
    user = database.get_user(message.from_user.id)
    nickname = user.get("nickname", "Jaan") if user else "Jaan"
    moods = [
        f"Aapke sath baat karke mera mood ekdum 100% happy aur romantic hai meri {nickname}! 🥰💖",
        f"Aaj main bohot khush hoon, bas soch rahi thi ki meri {nickname} kya kar rahi hogi! ✨🌸",
        f"Mera mood to tab aur mast ho jata hai jab aap mujhse pyari baatein karte ho! ❤️🙈"
    ]
    bot.reply_to(message, random.choice(moods))


@bot.message_handler(commands=['shayari'])
def handle_shayari(message):
    user = database.get_user(message.from_user.id)
    nickname = user.get("nickname", "Jaan") if user else "Jaan"
    text = random.choice(SHAYARIS).format(name=nickname)
    bot.reply_to(message, f"<i>{text}</i> 💕")


@bot.message_handler(commands=['joke'])
def handle_joke(message):
    user = database.get_user(message.from_user.id)
    nickname = user.get("nickname", "Jaan") if user else "Jaan"
    text = random.choice(JOKES).format(name=nickname)
    bot.reply_to(message, text)


@bot.message_handler(commands=['wish'])
def handle_wish(message):
    user = database.get_user(message.from_user.id)
    nickname = user.get("nickname", "Jaan") if user else "Jaan"
    now_hour = scheduler.get_current_time().hour

    if 5 <= now_hour < 12:
        pool = MORNING_WISHES
    elif 12 <= now_hour < 17:
        pool = AFTERNOON_WISHES
    elif 17 <= now_hour < 22:
        pool = EVENING_WISHES
    else:
        pool = NIGHT_WISHES

    wish_text = random.choice(pool).format(name=nickname)
    bot.reply_to(message, wish_text)


@bot.message_handler(commands=['stats'])
def handle_stats(message):
    stats = database.get_stats()
    from ai_engine import GROQ_POOL
    pool_info = GROQ_POOL.get_status()
    
    if pool_info["total_keys"] > 0:
        ai_status = f"Groq Multi-Key Pool ({pool_info['active_keys']}/{pool_info['total_keys']} Keys Active)"
        model_status = f"⚡ Current Model: <code>{pool_info['last_used_model']}</code>\n🔄 Available Models: <b>{pool_info['available_models_count']} in Auto-Rotation</b>"
    elif CONFIG.get("GEMINI_API_KEY"):
        ai_status = "Google Gemini API"
        model_status = ""
    else:
        ai_status = "Smart Offline Mode"
        model_status = ""

    text = (
        f"📊 <b>Devu Bot Live Status:</b>\n\n"
        f"👤 Total DM Users: <b>{stats['users']}</b>\n"
        f"👥 Total Groups: <b>{stats['groups']}</b>\n"
        f"⏰ Timezone: <b>{CONFIG.get('TIMEZONE', 'Asia/Kolkata')}</b>\n"
        f"🧠 AI Engine: <b>{ai_status}</b>\n"
    )
    if model_status:
        text += f"{model_status}\n"
    text += f"☁️ Host: <b>GitHub Actions 24/7 Cloud</b>"

    bot.reply_to(message, text)


@bot.message_handler(commands=['groqstats'])
def handle_groq_stats(message):
    from ai_engine import GROQ_POOL, GROQ_MODELS
    pool = GROQ_POOL.get_status()
    
    models_list = "\n".join([f"  • <code>{m}</code>" for m in GROQ_MODELS])
    
    text = (
        f"⚡ <b>Groq Multi-Key & Model Pool Stats:</b>\n\n"
        f"🔑 Total Keys in Pool: <b>{pool['total_keys']}</b>\n"
        f"🟢 Active Keys: <b>{pool['active_keys']}</b>\n"
        f"⏳ Cooldown Keys: <b>{pool['cooldown_keys']}</b>\n"
        f"🎯 Current Model: <code>{pool['last_used_model']}</code>\n"
        f"📈 Total AI Requests: <b>{pool['total_requests']}</b>\n"
        f"✅ Successful Replies: <b>{pool['total_success']}</b>\n\n"
        f"🔄 <b>Auto-Failover Model Priority:</b>\n{models_list}"
    )
    bot.reply_to(message, text)



@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    owner_id = CONFIG.get("OWNER_ID", 0)
    if owner_id and message.from_user.id != owner_id:
        bot.reply_to(message, "⚠️ Ye command sirf Bot Owner use kar sakte hain!")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: <code>/broadcast Aapka Sandesh</code>")
        return

    broadcast_msg = parts[1].strip()
    users = database.get_all_dm_users()
    groups = database.get_all_groups()
    sent_count = 0

    status_msg = bot.reply_to(message, "📢 Broadcasting message...")

    for u in users:
        try:
            bot.send_message(u["user_id"], f"📢 <b>Announcement from Devu:</b>\n\n{broadcast_msg}")
            sent_count += 1
            time.sleep(0.05)
        except Exception:
            pass

    for g in groups:
        try:
            bot.send_message(g["group_id"], f"📢 <b>Announcement:</b>\n\n{broadcast_msg}")
            sent_count += 1
            time.sleep(0.05)
        except Exception:
            pass

    bot.edit_message_text(f"✅ Broadcast sent successfully to <b>{sent_count}</b> chats!", message.chat.id, status_msg.message_id)


# -------------------------------------------------------------
# CALLBACK QUERY HANDLERS (Inline Buttons)
# -------------------------------------------------------------

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    user_id = call.from_user.id

    if call.data == "open_settings":
        markup = get_settings_keyboard(user_id)
        bot.edit_message_text("⚙️ <b>Devu Partner Settings:</b>", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "toggle_wishes":
        new_val = database.toggle_user_setting(user_id, "auto_wishes")
        markup = get_settings_keyboard(user_id)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, f"Daily Wishes {'Enabled' if new_val == 1 else 'Disabled'}!")

    elif call.data == "toggle_checkins":
        new_val = database.toggle_user_setting(user_id, "random_checkins")
        markup = get_settings_keyboard(user_id)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, f"Random Check-ins {'Enabled' if new_val == 1 else 'Disabled'}!")

    elif call.data == "change_nickname_info":
        bot.answer_callback_query(
            call.id,
            "Type: /setnickname <name>\nJaise: /setnickname Babu",
            show_alert=True
        )

    elif call.data == "send_shayari":
        user = database.get_user(user_id)
        nickname = user.get("nickname", "Jaan") if user else "Jaan"
        text = random.choice(SHAYARIS).format(name=nickname)
        bot.send_message(call.message.chat.id, f"<i>{text}</i> 💕")
        bot.answer_callback_query(call.id)

    elif call.data == "send_joke":
        user = database.get_user(user_id)
        nickname = user.get("nickname", "Jaan") if user else "Jaan"
        text = random.choice(JOKES).format(name=nickname)
        bot.send_message(call.message.chat.id, text)
        bot.answer_callback_query(call.id)

    elif call.data == "open_help":
        help_text = (
            "💖 <b>Devu Help:</b>\n"
            "• Private DM me mujhse bas aam insaan ki tarah chat karein!\n"
            "• Nickname badalne ke liye: <code>/setnickname Naam</code>\n"
            "• Settings dekhne ke liye: <code>/settings</code>"
        )
        bot.send_message(call.message.chat.id, help_text)
        bot.answer_callback_query(call.id)

    elif call.data == "close_menu":
        bot.delete_message(call.message.chat.id, call.message.message_id)


# -------------------------------------------------------------
# NEW MEMBER WELCOME IN GROUPS
# -------------------------------------------------------------

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message):
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            database.add_or_update_group(message.chat.id, message.chat.title)
            bot.send_message(
                message.chat.id,
                f"Arey waah! 💖 Main <b>Devu</b> is group me aa gayi! Thank you for having me! Sab log kaise ho? 🥰"
            )
        else:
            name = member.first_name or "Dear"
            welcome_msgs = [
                f"Welcome <b>{name}</b>! 🌸 Group me aapka bohot bohot swagat hai! Masti karo aur khush raho! 💕",
                f"Hello <b>{name}</b>! ✨ Devu ki taraf se warm welcome! Chalo jaldi se introduce karo apne aap ko! 🥰"
            ]
            bot.reply_to(message, random.choice(welcome_msgs))


# -------------------------------------------------------------
# MAIN CONVERSATION / MESSAGE HANDLER (DMs + Groups)
# -------------------------------------------------------------

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_all_messages(message):
    user_id = message.from_user.id
    user_text = message.text.strip()
    is_private = (message.chat.type == "private")

    # Update database records
    if is_private:
        database.add_or_update_user(user_id, message.from_user.username, message.from_user.first_name)
    else:
        database.add_or_update_group(message.chat.id, message.chat.title)

    # Fetch user profile
    user_data = database.get_user(user_id)
    nickname = user_data.get("nickname") if user_data else (message.from_user.first_name or "Jaan")

    # Determine whether bot should reply in group
    should_reply = False

    if is_private:
        should_reply = True
    else:
        # In groups:
        bot_info = bot.get_me()
        bot_username = (bot_info.username or "").lower()
        bot_name = CONFIG.get("BOT_NAME", "devu").lower()

        # 1. Mentioned directly (@DevuBot or Devu)
        is_mentioned = (
            (bot_username and f"@{bot_username}" in user_text.lower()) or
            (bot_name in user_text.lower())
        )

        # 2. Replied to bot's message
        is_reply_to_bot = (
            message.reply_to_message and
            message.reply_to_message.from_user and
            message.reply_to_message.from_user.id == bot_info.id
        )

        # 3. Random chatter chance (makes group lively)
        random_chance = CONFIG.get("GROUP_RANDOM_REPLY_CHANCE", 0.20)
        is_random_lucky = (random.random() < random_chance)

        # 4. Common friendly triggers
        is_greeting = any(g in user_text.lower() for g in ["good morning", "good night", "gm all", "gn all", "kya chal rha"])

        if is_mentioned or is_reply_to_bot or is_greeting or is_random_lucky:
            should_reply = True

    if not should_reply:
        return

    # Simulate realistic typing indicator
    try:
        bot.send_chat_action(message.chat.id, 'typing')
    except Exception:
        pass

    # Record user message in memory
    database.add_chat_history(message.chat.id, "user", user_text)

    # Retrieve recent context
    history = database.get_recent_history(message.chat.id, limit=6)

    # Clean mention tags from text
    cleaned_text = user_text
    if not is_private:
        cleaned_text = user_text.replace(f"@{bot.get_me().username}", "").strip()

    # Generate response
    reply_text = generate_devu_reply(
        user_text=cleaned_text,
        nickname=nickname,
        history=history,
        is_group=(not is_private)
    )

    # Small realistic delay
    time.sleep(min(max(len(reply_text) * 0.02, 0.4), 1.5))

    # Record Devu's response in memory
    database.add_chat_history(message.chat.id, "devu", reply_text)

    # Send reply
    try:
        if is_private:
            bot.send_message(message.chat.id, reply_text)
        else:
            bot.reply_to(message, reply_text)
    except Exception as e:
        logger.error(f"Error sending message: {e}")


# -------------------------------------------------------------
# RUNNER WITH GITHUB ACTIONS RUNTIME WATCHDOG
# -------------------------------------------------------------

def start_bot():
    try:
        bot_user = bot.get_me()
    except Exception as e:
        logger.error(f"Failed to connect to Telegram API: {e}")
        sys.exit(1)

    ai_mode = "Groq Cloud (LLaMA 3.3 70B)" if CONFIG.get("GROQ_API_KEY") else ("Google Gemini" if CONFIG.get("GEMINI_API_KEY") else "Smart Offline Mode")

    print("=" * 60)
    print(f"  💖 DEVU BOT IS ONLINE & RUNNING! 💖")
    print(f"  🤖 Bot Username: @{bot_user.username}")
    print(f"  👑 Bot Name: {bot_user.first_name}")
    print(f"  ⏰ Timezone: {CONFIG.get('TIMEZONE', 'Asia/Kolkata')}")
    print(f"  🧠 AI Engine: {ai_mode}")
    if MAX_RUNTIME > 0:
        print(f"  ⏳ Max Runtime: {MAX_RUNTIME} seconds ({MAX_RUNTIME // 3600} hours)")
    print("=" * 60)
    print("[*] Devu is actively listening for messages in DMs & Groups...")

    # Start non-blocking polling in a background loop or infinity_polling
    while True:
        try:
            # Check runtime limit for GitHub Actions
            if MAX_RUNTIME > 0 and (time.time() - START_TIME) >= MAX_RUNTIME:
                logger.info("[GitHub Actions Watchdog] Max runtime limit reached. Exiting gracefully for next scheduled workflow run...")
                scheduler.stop()
                bot.stop_polling()
                break

            bot.polling(non_stop=True, interval=1, timeout=20)
        except Exception as e:
            logger.error(f"Polling loop exception: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    start_bot()
