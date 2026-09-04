"""
Group Skills & Member Memory for Sona 💖
- Group ke HAR member ko observe karke yaad rakhti hai (naam, messages, baat-cheet).
- AI ko group context deti hai taaki Sona situation-aware, personal baat kare.
- Fairness Engine: jo member sabse kam suna gaya hai usko khud se ping karti hai,
  taaki kisi ko bhi ignored feel na ho.
"""

import datetime
import logging
import database

logger = logging.getLogger(__name__)

# Quiet member ko pyaar se wapas masti me lane ke liye lines
QUIET_MEMBER_PINGS = [
    "Arey {name}, tum itne chup kyu ho aaj? Sab theek hai na? 🥺",
    "{name}! Tumhari awaaz nahi aa rahi group me, kuch bolo na yaar! 😄",
    "Arey {name}, kaha dubki maari hui hai? Wapas aao masti me! 🌸",
    "{name}, tumhare bina group adhoora lag raha hai aaj! 💖",
]


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_skills_db():
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            group_id INTEGER,
            user_id INTEGER,
            first_name TEXT,
            username TEXT,
            msg_count INTEGER DEFAULT 0,
            addressed_count INTEGER DEFAULT 0,
            last_msg TEXT,
            last_addressed TEXT,
            PRIMARY KEY (group_id, user_id)
        )
    """)
    conn.commit()
    conn.close()


init_skills_db()


def observe_member(group_id, user_id, first_name="", username=""):
    """Har group message sender ko note karo (ya naya member, ya update)."""
    now = _now()
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    if c.fetchone():
        c.execute("""
            UPDATE group_members
            SET msg_count = msg_count + 1,
                last_msg = ?,
                first_name = COALESCE(NULLIF(?, ''), first_name),
                username = COALESCE(NULLIF(?, ''), username)
            WHERE group_id = ? AND user_id = ?
        """, (now, first_name, username, group_id, user_id))
    else:
        c.execute("""
            INSERT INTO group_members (group_id, user_id, first_name, username,
                                         msg_count, addressed_count, last_msg, last_addressed)
            VALUES (?, ?, ?, ?, 1, 0, ?, '')
        """, (group_id, user_id, first_name or "Friend", username or "", now))
    conn.commit()
    conn.close()


def mark_addressed(group_id, user_id):
    """Jab Sona kisi member se baat kare, record karo (fairness ke liye)."""
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE group_members
        SET addressed_count = addressed_count + 1, last_addressed = ?
        WHERE group_id = ? AND user_id = ?
    """, (_now(), group_id, user_id))
    conn.commit()
    conn.close()


def get_group_members(group_id, limit=15):
    """Group ke active members (message count ke hisab se)."""
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT group_id, user_id, first_name, username, msg_count, addressed_count, last_msg, last_addressed
        FROM group_members WHERE group_id = ?
        ORDER BY msg_count DESC LIMIT ?
    """, (group_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_quiet_member(group_id):
    """Sabse kam suna gaya active member (kabhi na suna gaya ho to pehle)."""
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT group_id, user_id, first_name, username, msg_count, addressed_count, last_msg, last_addressed
        FROM group_members
        WHERE group_id = ? AND msg_count > 0
        ORDER BY last_addressed ASC LIMIT 1
    """, (group_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def build_group_note(group_id, sender_id):
    """AI ke liye chhota sa group-memory note taaki baat personal aur fair rahe."""
    members = get_group_members(group_id, 6)
    if not members:
        return ""
    parts = []
    for m in members:
        name = m["first_name"] or m["username"] or "Friend"
        parts.append(f"{name} ({m['msg_count']} msgs, aapse baat {m['addressed_count']}x)")
    note = "Group members jo tum yaad rakhti ho: " + ", ".join(parts) + "."
    if sender_id:
        for m in members:
            if m["user_id"] == sender_id:
                note += f" Abhi jo message bheja hai wo hai {m['first_name'] or 'Friend'}."
                break
    note += " Sabse pyaar se baat karo aur kisi ko ignore mat karo."
    return note
