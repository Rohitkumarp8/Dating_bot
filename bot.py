import os
import logging
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from groq import Groq

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_KEY_HERE")

# ─── Conversation States ───────────────────────────────────────────────────────
NAME, AGE, GENDER, LOOKING_FOR, BIO, PHOTO = range(6)

# ─── Database Setup ────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("dating.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            age INTEGER,
            gender TEXT,
            looking_for TEXT,
            bio TEXT,
            photo_id TEXT,
            liked_users TEXT DEFAULT '',
            disliked_users TEXT DEFAULT '',
            matched_users TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("dating.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        cols = ["user_id","username","name","age","gender","looking_for","bio","photo_id","liked_users","disliked_users","matched_users","active"]
        return dict(zip(cols, row))
    return None

def save_user(data: dict):
    conn = sqlite3.connect("dating.db")
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO users
        (user_id, username, name, age, gender, looking_for, bio, photo_id, liked_users, disliked_users, matched_users, active)
        VALUES (:user_id, :username, :name, :age, :gender, :looking_for, :bio, :photo_id, :liked_users, :disliked_users, :matched_users, :active)
    """, data)
    conn.commit()
    conn.close()

def get_potential_matches(user_id, gender_pref, my_gender):
    conn = sqlite3.connect("dating.db")
    c = conn.cursor()
    c.execute("""
        SELECT user_id, name, age, bio, photo_id FROM users
        WHERE user_id != ?
          AND active = 1
          AND gender = ?
          AND (looking_for = ? OR looking_for = 'Both')
    """, (user_id, gender_pref, my_gender))
    rows = c.fetchall()
    conn.close()
    return rows

# ─── AI Helper ─────────────────────────────────────────────────────────────────
def get_ai_icebreaker(my_profile: dict, their_profile: dict) -> str:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = f"""You are a friendly dating coach. Generate a fun, short icebreaker message (2-3 sentences max) 
that {my_profile['name']} can send to {their_profile['name']}.

My profile: Name={my_profile['name']}, Age={my_profile['age']}, Bio={my_profile['bio']}
Their profile: Name={their_profile['name']}, Age={their_profile['age']}, Bio={their_profile['bio']}

Keep it light, fun and genuine. No emojis overload. Respond in the same language as the bio."""

        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            max_tokens=200
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.error(f"AI error: {e}")
        return f"Hey {their_profile['name']}! I came across your profile and thought we might vibe. How are you? 😊"

# ─── Command Handlers ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        await update.message.reply_text(
            f"Welcome back, {user['name']}! 💖\n\n"
            "What do you want to do?",
            reply_markup=main_menu_keyboard()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "💘 *Welcome to LoveConnect Bot!*\n\n"
            "India ka sabse smart dating bot — AI powered matching!\n\n"
            "Let's set up your profile. Kya aap ready hain? 🚀\n\n"
            "Apna *naam* batao:",
            parse_mode="Markdown"
        )
        context.user_data.clear()
        context.user_data["user_id"] = update.effective_user.id
        context.user_data["username"] = update.effective_user.username or ""
        context.user_data["liked_users"] = ""
        context.user_data["disliked_users"] = ""
        context.user_data["matched_users"] = ""
        context.user_data["active"] = 1
        context.user_data["photo_id"] = ""
        return NAME

def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        ["💘 Discover", "💌 My Matches"],
        ["👤 My Profile", "✏️ Edit Profile"],
        ["🤖 AI Icebreaker", "❌ Pause Profile"]
    ], resize_keyboard=True)

# ─── Profile Setup ─────────────────────────────────────────────────────────────
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Naam thoda lamba likho please 😅")
        return NAME
    context.user_data["name"] = name
    await update.message.reply_text(f"Nice name, {name}! 😊\n\nAb apni *umar* batao (sirf number):", parse_mode="Markdown")
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text.strip())
        if age < 18:
            await update.message.reply_text("⚠️ Sorry, yeh bot sirf 18+ ke liye hai.")
            return AGE
        if age > 80:
            await update.message.reply_text("Sahi umar likho please 😄")
            return AGE
    except ValueError:
        await update.message.reply_text("Sirf number likho jaise: 25")
        return AGE

    context.user_data["age"] = age
    keyboard = ReplyKeyboardMarkup([["Male", "Female"], ["Other"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Aap kya hain?", reply_markup=keyboard)
    return GENDER

async def get_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender = update.message.text.strip()
    if gender not in ["Male", "Female", "Other"]:
        await update.message.reply_text("Neeche se choose karo please.")
        return GENDER
    context.user_data["gender"] = gender
    keyboard = ReplyKeyboardMarkup([["Male", "Female"], ["Both"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Aap kise dhundh rahe hain?", reply_markup=keyboard)
    return LOOKING_FOR

async def get_looking_for(update: Update, context: ContextTypes.DEFAULT_TYPE):
    looking = update.message.text.strip()
    if looking not in ["Male", "Female", "Both"]:
        await update.message.reply_text("Neeche se choose karo please.")
        return LOOKING_FOR
    context.user_data["looking_for"] = looking
    await update.message.reply_text(
        "Thodi si apne baare mein *bio* likho 📝\n\n"
        "(Apni hobbies, pasand, kya dhundh rahe ho — 2-3 lines kaafi hain)",
        parse_mode="Markdown"
    )
    return BIO

async def get_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bio = update.message.text.strip()
    if len(bio) < 10:
        await update.message.reply_text("Thoda aur likho apne baare mein 😊 (kam se kam 10 characters)")
        return BIO
    context.user_data["bio"] = bio
    await update.message.reply_text(
        "Ab ek *photo* bhejo 📸\n\n(Ya /skip likho agar baad mein add karna ho)",
        parse_mode="Markdown"
    )
    return PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
        context.user_data["photo_id"] = photo_id
    save_user(context.user_data)
    await update.message.reply_text(
        f"🎉 *Profile ready hai, {context.user_data['name']}!*\n\n"
        "Ab discover karo aur apna match dhundo! 💘",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["photo_id"] = ""
    save_user(context.user_data)
    await update.message.reply_text(
        f"🎉 *Profile ready hai, {context.user_data['name']}!*\n\n"
        "Ab discover karo aur apna match dhundo! 💘",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# ─── Discover ──────────────────────────────────────────────────────────────────
async def discover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Pehle /start karke profile banao! 😊")
        return

    already_seen = set(
        (user["liked_users"] + "," + user["disliked_users"]).split(",")
    ) - {""}

    matches = get_potential_matches(update.effective_user.id, user["looking_for"], user["gender"])
    matches = [m for m in matches if str(m[0]) not in already_seen]

    if not matches:
        await update.message.reply_text(
            "😔 Abhi koi new profile nahi mili.\n\nThodi der baad try karo ya apna preference change karo!",
            reply_markup=main_menu_keyboard()
        )
        return

    profile = matches[0]
    pid, name, age, bio, photo_id = profile

    caption = f"💘 *{name}*, {age}\n\n📝 {bio}"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❤️ Like", callback_data=f"like_{pid}"),
            InlineKeyboardButton("👎 Dislike", callback_data=f"dislike_{pid}")
        ]
    ])

    if photo_id:
        await update.message.reply_photo(photo=photo_id, caption=caption, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update.message.reply_text(f"👤 {caption}", parse_mode="Markdown", reply_markup=keyboard)

async def handle_like_dislike(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, target_id = data.split("_", 1)
    target_id = int(target_id)

    user = get_user(query.from_user.id)
    if not user:
        return

    if action == "like":
        liked = user["liked_users"].split(",") if user["liked_users"] else []
        liked.append(str(target_id))
        user["liked_users"] = ",".join(liked)

        # Check if target also liked this user → MATCH!
        target = get_user(target_id)
        if target and str(query.from_user.id) in (target["liked_users"] or "").split(","):
            # Add to matched list for both
            my_matched = user["matched_users"].split(",") if user["matched_users"] else []
            my_matched.append(str(target_id))
            user["matched_users"] = ",".join(my_matched)

            t_matched = target["matched_users"].split(",") if target["matched_users"] else []
            t_matched.append(str(query.from_user.id))
            target["matched_users"] = ",".join(t_matched)
            save_user(target)

            await query.edit_message_caption(
                caption=f"🎉 *It's a Match!* ❤️\n\nTum aur {target['name']} ne ek dusre ko like kiya!",
                parse_mode="Markdown"
            )
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 *It's a Match!*\n\n{user['name']} ne bhi tumhe like kiya! Baat karo! 💬",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_caption(
                caption=f"❤️ Liked! Agar unhone bhi like kiya toh match ho jaega!",
                parse_mode="Markdown"
            ) if hasattr(query.message, 'caption') and query.message.caption else \
            await query.edit_message_text("❤️ Liked! Agar unhone bhi like kiya toh match ho jaega!")

    else:  # dislike
        disliked = user["disliked_users"].split(",") if user["disliked_users"] else []
        disliked.append(str(target_id))
        user["disliked_users"] = ",".join(disliked)
        try:
            await query.edit_message_caption(caption="👎 Skipped!") if hasattr(query.message, 'caption') and query.message.caption else \
            await query.edit_message_text("👎 Skipped!")
        except:
            pass

    save_user(user)

# ─── My Matches ────────────────────────────────────────────────────────────────
async def my_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user or not user["matched_users"]:
        await update.message.reply_text(
            "😔 Abhi koi match nahi hai.\n\nDiscover karke like karo! 💘",
            reply_markup=main_menu_keyboard()
        )
        return

    matched_ids = [m for m in user["matched_users"].split(",") if m]
    text = "💌 *Tumhare Matches:*\n\n"
    for mid in matched_ids:
        m = get_user(int(mid))
        if m:
            text += f"• {m['name']}, {m['age']} — @{m['username'] or 'username nahi'}\n"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# ─── My Profile ────────────────────────────────────────────────────────────────
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Pehle /start karo! 😊")
        return

    text = (
        f"👤 *Tera Profile*\n\n"
        f"📛 Naam: {user['name']}\n"
        f"🎂 Umar: {user['age']}\n"
        f"⚧️ Gender: {user['gender']}\n"
        f"💘 Dhundh raha/rahi: {user['looking_for']}\n"
        f"📝 Bio: {user['bio']}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# ─── AI Icebreaker ─────────────────────────────────────────────────────────────
async def ai_icebreaker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user or not user["matched_users"]:
        await update.message.reply_text("Pehle koi match hona chahiye! 💘")
        return

    matched_ids = [m for m in user["matched_users"].split(",") if m]
    if not matched_ids:
        await update.message.reply_text("Koi match nahi abhi. Pehle discover karo!")
        return

    # Use latest match
    target = get_user(int(matched_ids[-1]))
    if not target:
        await update.message.reply_text("Match profile nahi mili.")
        return

    await update.message.reply_text("🤖 AI ek achha message soch raha hai... ✨")
    message = get_ai_icebreaker(user, target)
    await update.message.reply_text(
        f"💬 *{target['name']} ke liye icebreaker:*\n\n_{message}_",
        parse_mode="Markdown"
    )

# ─── Pause / Resume ────────────────────────────────────────────────────────────
async def pause_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        return
    user["active"] = 0 if user["active"] == 1 else 1
    save_user(user)
    status = "pause" if user["active"] == 0 else "active"
    await update.message.reply_text(
        f"{'⏸️ Profile pause ho gayi!' if status == 'pause' else '▶️ Profile active ho gayi!'}",
        reply_markup=main_menu_keyboard()
    )

# ─── Cancel ────────────────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Setup cancel ho gaya. /start se dobara shuru karo.")
    return ConversationHandler.END

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            LOOKING_FOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_looking_for)],
            BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_bio)],
            PHOTO: [
                MessageHandler(filters.PHOTO, get_photo),
                CommandHandler("skip", skip_photo)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.Regex("💘 Discover"), discover))
    app.add_handler(MessageHandler(filters.Regex("💌 My Matches"), my_matches))
    app.add_handler(MessageHandler(filters.Regex("👤 My Profile"), my_profile))
    app.add_handler(MessageHandler(filters.Regex("🤖 AI Icebreaker"), ai_icebreaker))
    app.add_handler(MessageHandler(filters.Regex("❌ Pause Profile"), pause_profile))
    app.add_handler(CallbackQueryHandler(handle_like_dislike, pattern=r"^(like|dislike)_\d+$"))

    print("🤖 LoveConnect Bot chal raha hai...")
    app.run_polling()

if __name__ == "__main__":
    main()
