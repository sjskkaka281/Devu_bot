"""
Task & Reminder Engine for Sona 💖
- User (DM ya group) Sona ko koi bhi kaam/time batata hai -> Sona yaad rakhti hai.
- Target time par aake puchhti hai "kiya kya?"; jawab na aaye to har 30 min me dobara.
- Daily tasks (dawai, gym...) har din repeat; one-time task done hone par khatam.
- Cancel: natural language ("abse yad mat dilana") ya /deltask command.
- Sab kuch SQLite me saved -> GitHub restart ke baad bhi yaad rahta hai.
"""

import re
import random
import datetime
import logging
import database

logger = logging.getLogger(__name__)

ASK_RETRY_MINUTES = 30

# ---------- vocabulary ----------
RECUR_WORDS = ["roj", "roz", "daily", "har din", "har roz", "rozana", "every day", "everyday", "nitya", "har roj"]
TASK_WORDS = ["puchna", "puchhna", "puch lena", "puchlena", "puch liya karo", "yaad dilana", "yad dilana",
              "yaad rakhna", "yad rakhna", "remind", "reminder", "batana", "puchegi", "pucha karo"]
CANCEL_WORDS = ["yad mat dilao", "yaad mat dilana", "yaad mat dila", "mat puchna", "mat puchhna", "cancel",
                "band karo", "band kar do", "abse nahi", "ab se nahi", "zarurat nahi", "zaroorat nahi",
                "nahi karunga", "nahi karungi", "nhi karunga", "nhi karungi", "remove task", "hatado", "hata do"]
CONFIRM_WORDS = ["haan", "han ji", "ji haan", "yes", "done", "ho gaya", "ho gayi", "hogaya", "kar liya",
                 "kar li", "le liya", "le li", "liya", "li hai", "kha liya", "kha li", "pi liya", "pi li",
                 "complete", "ho gya"]
REFUSE_WORDS = ["nahi", "nhi", "abhi nahi", "abhi nhi", "not yet", "abhi tak nahi", "nhi kiya", "nahi kiya"]

PERIOD_AM = ["subah", "subha", "saver", "suprabhat", "morning"]
PERIOD_NOON = ["dopeher", "dophar", "dupehar", "noon", "afternoon"]
PERIOD_EVE = ["shaam", "sham", "sandhya", "evening"]
PERIOD_NIGHT = ["raat", "ratri", "raatri", "night", "midnight"]

REMINDER_LINES = [
    "{name}, ek kaam yaad dilau — {title}? Kiya kya? 🥺",
    "Hey {name}! {title} — ho gaya ya abhi baaki hai? 💖",
    "{name} ji, aapka task tha: {title}. Batao, done ya nahi? 😊",
    "{name}... {title} ✅ ya ❌? Sach sach batana! ",
]

DONE_LINES = [
    "Yayy! Shabash {name}! 🥰 Dil se khush ho gayi main. Ab agla task time par yaad dilaungi! 💖",
    "Wah {name}, kaam ho gaya! 💯 Mujhe tum par bohot garv hai... matlab pyaar! 😘",
]


# ---------- storage ----------
def init_task_db():
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            user_name TEXT,
            title TEXT,
            hour INTEGER,
            minute INTEGER,
            recurring INTEGER DEFAULT 1,
            active INTEGER DEFAULT 1,
            created TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS task_state (
            task_id INTEGER,
            day TEXT,
            last_asked TEXT,
            ask_count INTEGER DEFAULT 0,
            done INTEGER DEFAULT 0,
            PRIMARY KEY (task_id, day)
        )
    """)
    conn.commit()
    conn.close()


init_task_db()


def _now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_task(chat_id, user_id, user_name, parsed):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO user_tasks (chat_id, user_id, user_name, title, hour, minute, recurring, active, created)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (chat_id, user_id, user_name, parsed["title"], parsed["hour"], parsed["minute"],
          1 if parsed["recurring"] else 0, _now_str()))
    tid = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"[Tasks] New task #{tid}: '{parsed['title']}' at {parsed['hour']:02d}:{parsed['minute']:02d} "
                f"({'daily' if parsed['recurring'] else 'one-time'}) for {user_name} in {chat_id}")
    return tid


def get_active_tasks(chat_id, user_id=None):
    conn = database.get_connection()
    c = conn.cursor()
    if user_id is None:
        c.execute("SELECT * FROM user_tasks WHERE chat_id = ? AND active = 1 ORDER BY id", (chat_id,))
    else:
        c.execute("SELECT * FROM user_tasks WHERE chat_id = ? AND user_id = ? AND active = 1 ORDER BY id",
                  (chat_id, user_id))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _get_state(task_id, day):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM task_state WHERE task_id = ? AND day = ?", (task_id, day))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def mark_asked(task_id, now):
    day = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO task_state (task_id, day, last_asked, ask_count, done)
        VALUES (?, ?, ?, 1, 0)
        ON CONFLICT(task_id, day) DO UPDATE SET last_asked = ?, ask_count = ask_count + 1
    """, (task_id, day, ts, ts))
    conn.commit()
    conn.close()


def get_asked_pending(chat_id, user_id, now):
    """Aaj ka task jo pucha ja chuka hai par abhi done nahi (user confirm kar sakta hai)."""
    day = now.strftime("%Y-%m-%d")
    for t in get_active_tasks(chat_id, user_id):
        if (t["hour"] * 60 + t["minute"]) > (now.hour * 60 + now.minute):
            continue
        st = _get_state(t["id"], day)
        if st and st["ask_count"] > 0 and not st["done"]:
            return t
    return None


def mark_done(task, now):
    day = now.strftime("%Y-%m-%d")
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO task_state (task_id, day, last_asked, ask_count, done)
        VALUES (?, ?, '', 0, 1)
        ON CONFLICT(task_id, day) DO UPDATE SET done = 1
    """, (task["id"], day))
    if not task["recurring"]:
        c.execute("UPDATE user_tasks SET active = 0 WHERE id = ?", (task["id"],))
    conn.commit()
    conn.close()


def get_due(now):
    """Tasks jinhe abhi puchna hai (time aa gaya, done nahi, 30 min se nahi pucha)."""
    day = now.strftime("%Y-%m-%d")
    minutes_now = now.hour * 60 + now.minute
    due = []
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM user_tasks WHERE active = 1")
    tasks = [dict(r) for r in c.fetchall()]
    conn.close()
    for t in tasks:
        if (t["hour"] * 60 + t["minute"]) > minutes_now:
            continue
        st = _get_state(t["id"], day)
        if st and st["done"]:
            continue
        if st and st["last_asked"]:
            try:
                last = datetime.datetime.strptime(st["last_asked"], "%Y-%m-%d %H:%M:%S")
                now_naive = now.replace(tzinfo=None)
                if (now_naive - last).total_seconds() < ASK_RETRY_MINUTES * 60:
                    continue
            except Exception:
                pass
        due.append(t)
    return due


def cancel_task(task_id):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("UPDATE user_tasks SET active = 0 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def cancel_by_arg(chat_id, user_id, arg):
    """arg = task id ya title keyword; khali ho to sabse naya active task."""
    tasks = get_active_tasks(chat_id, user_id)
    if not tasks:
        return "🥺 Aapka koi active task hai hi nahi is chat me!"
    target = None
    arg = (arg or "").strip()
    if arg:
        if arg.isdigit():
            target = next((t for t in tasks if t["id"] == int(arg)), None)
        else:
            target = next((t for t in tasks if arg.lower() in t["title"].lower()), None)
        if not target:
            return f"🤔 '{arg}' naam ka koi active task nahi mila. /tasks se list dekho!"
    else:
        target = tasks[-1]
    cancel_task(target["id"])
    return (f"✅ Theek hai jaan, '{target['title']}' wala task memory se hata diya — "
            f"ab main iske liye nahi puchhungi! 💖")


def list_tasks(chat_id, user_id):
    tasks = get_active_tasks(chat_id, user_id)
    if not tasks:
        return "🥺 Abhi koi active task nahi hai! Task dene ke liye likho: /task roj 08:00 dawai lena"
    lines = ["💖 <b>Aapke active tasks:</b>"]
    for t in tasks:
        kind = "🔁 roj" if t["recurring"] else "1️⃣ one-time"
        lines.append(f"#{t['id']} • {t['hour']:02d}:{t['minute']:02d} • {t['title']} ({kind})")
    lines.append("Hatane ke liye: /deltask <id>")
    return "\n".join(lines)


# ---------- language understanding ----------
def parse_time(text):
    """Saari notations samjho: 8 A.M / 8 am / 8 a.m / 8 P.M / 8pm / 8:30 pm / 8.30 p.m /
    20:00 / subah 8 / 8 baje subah / shaam 4 / dopeher 2 / raat 10 baje ..."""
    t = text.lower()

    # HH:MM with am/pm (any notation: am, a.m, pm, p.m ...)
    m = re.search(r"(\d{1,2})[:.](\d{2})\s*(a\.m|p\.m|am|pm)\b", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        return _apply_ampm(h, m.group(3)), mi

    # plain 24h HH:MM
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if m and int(m.group(1)) <= 23:
        return int(m.group(1)), int(m.group(2))

    # number + am/pm
    m = re.search(r"(\d{1,2})\s*(a\.m|p\.m|am|pm)\b", t)
    if m:
        return _apply_ampm(int(m.group(1)), m.group(2)), 0

    # period word + number  OR  number (+baje) + period word
    for words, conv in [
        (PERIOD_AM, lambda h: 0 if h == 12 else h),
        (PERIOD_NOON, lambda h: h if h == 12 else h + 12),
        (PERIOD_EVE, lambda h: h + 12 if h < 12 else h),
        (PERIOD_NIGHT, lambda h: 0 if h == 12 else (h + 12 if h < 12 else h)),
    ]:
        for w in words:
            m = re.search(rf"{w}\D{{0,6}}(\d{{1,2}})", t) or re.search(rf"(\d{{1,2}})\D{{0,8}}{w}", t)
            if m and 1 <= int(m.group(1)) <= 12:
                return conv(int(m.group(1))), 0

    # bare "8 baje" (1-6 => evening, 7-12 => morning guess; confirmation me time dikhta hai)
    m = re.search(r"(\d{1,2})\s*(?:baje|baja|bje|baaje)", t)
    if m and 1 <= int(m.group(1)) <= 12:
        h = int(m.group(1))
        return (h + 12 if h <= 6 else h), 0

    return None, None


def _apply_ampm(h, tag):
    pm = tag.replace(".", "").startswith("p")
    if pm and h < 12:
        return h + 12
    if not pm and h == 12:
        return 0
    return h


def try_parse_task(text, force=False):
    """Natural language se task nikalo; time zaroori hai (+ task-word ya force)."""
    if not text:
        return None
    t = text.lower()
    hour, minute = parse_time(text)
    if hour is None:
        return None
    if not force and not any(w in t for w in TASK_WORDS):
        return None
    recurring = any(w in t for w in RECUR_WORDS)

    # title: time-tokens aur filler hatao
    title = text
    title = re.sub(r"\d{1,2}[:.]\d{2}\s*(a\.m|p\.m|am|pm)\b", " ", title, flags=re.I)
    title = re.sub(r"\d{1,2}\s*(a\.m|p\.m|am|pm)\b", " ", title, flags=re.I)
    title = re.sub(r"\d{1,2}\s*(baje|baja|bje|baaje)?", " ", title, flags=re.I)
    for w in (PERIOD_AM + PERIOD_NOON + PERIOD_EVE + PERIOD_NIGHT + RECUR_WORDS + TASK_WORDS +
              ["mujhe", "mujhse", "mujse", "mereko", "merko", "please", "plz", "ki nhi", "ki nahi",
               "kiya ki nhi", "task", "aaj", "kal", "abse", "ab se", "mujhe", "bola", "bole", "sona", "tum"]):
        title = re.sub(rf"\b{re.escape(w)}\b", " ", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" -.!,?")
    if len(title) < 3:
        title = text.strip()[:60]
    return {"title": title, "hour": hour, "minute": minute or 0, "recurring": recurring}


def detect_cancel(text):
    t = (text or "").lower()
    return any(w in t for w in CANCEL_WORDS)


def detect_confirm(text):
    t = (text or "").lower().strip()
    return any(w in t for w in CONFIRM_WORDS)


def detect_refuse(text):
    t = (text or "").lower().strip()
    return any(w in t for w in REFUSE_WORDS)


def confirmation_line(parsed, name):
    when = f"{parsed['hour']:02d}:{parsed['minute']:02d}"
    kind = "roj" if parsed["recurring"] else "aaj/ek baar"
    return (f"Pakka {name}! 💖 Maine yaad kar liya — <b>{parsed['title']}</b> ke liye main <b>{kind} "
            f"{when}</b> par aake puchhungi. Jab tak aap 'haan/done' nahi bologe, main har 30 min me "
            f"yaad dilati rahungi! 😘✅")
