"""
Database Manager for Sona Telegram Bot (SQLite3)
Manages user profiles, group preferences, chat memories, and automated messaging targets.
"""

import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "devu_data.db")

def get_connection():
    """Get a thread-safe SQLite database connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            nickname TEXT DEFAULT 'Jaan',
            auto_wishes INTEGER DEFAULT 1,
            random_checkins INTEGER DEFAULT 1,
            joined_at TEXT,
            last_active TEXT
        )
    """)

    # Groups Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY,
            group_title TEXT,
            auto_wishes INTEGER DEFAULT 1,
            random_chatter INTEGER DEFAULT 1,
            joined_at TEXT,
            last_active TEXT
        )
    """)

    # Chat History Table (stores recent conversation context)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            message TEXT,
            timestamp TEXT
        )
    """)

    # Scheduler / bot persistent state (so daily wishes are never skipped or repeated across restarts)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()

def get_state(key, default=""):
    """Read a persistent key/value from bot_state."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_state WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_state(key, value):
    """Write a persistent key/value into bot_state (upsert)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bot_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value)
    )
    conn.commit()
    conn.close()

def add_or_update_user(user_id, username="", first_name=""):
    """Register or update user activity."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, nickname FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, nickname, auto_wishes, random_checkins, joined_at, last_active)
            VALUES (?, ?, ?, ?, 1, 1, ?, ?)
        """, (user_id, username or "", first_name or "Friend", "Jaan", now, now))
    else:
        cursor.execute("""
            UPDATE users SET username = ?, first_name = ?, last_active = ?
            WHERE user_id = ?
        """, (username or "", first_name or "", now, user_id))

    conn.commit()
    conn.close()

def add_or_update_group(group_id, group_title=""):
    """Register or update group activity."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT group_id FROM groups WHERE group_id = ?", (group_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute("""
            INSERT INTO groups (group_id, group_title, auto_wishes, random_chatter, joined_at, last_active)
            VALUES (?, ?, 1, 1, ?, ?)
        """, (group_id, group_title or "Telegram Group", now, now))
    else:
        cursor.execute("""
            UPDATE groups SET group_title = ?, last_active = ?
            WHERE group_id = ?
        """, (group_title or "", now, group_id))

    conn.commit()
    conn.close()

def set_user_nickname(user_id, nickname):
    """Set custom partner nickname for the user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET nickname = ? WHERE user_id = ?", (nickname.strip(), user_id))
    conn.commit()
    conn.close()

def get_user(user_id):
    """Retrieve user details."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_group(group_id):
    """Retrieve group details."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM groups WHERE group_id = ?", (group_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def toggle_user_setting(user_id, setting_field):
    """Toggle 1/0 for a user setting (auto_wishes / random_checkins)."""
    if setting_field not in ("auto_wishes", "random_checkins"):
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {setting_field} FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        new_val = 0 if row[0] == 1 else 1
        cursor.execute(f"UPDATE users SET {setting_field} = ? WHERE user_id = ?", (new_val, user_id))
        conn.commit()
        conn.close()
        return new_val
    conn.close()
    return None

def toggle_group_setting(group_id, setting_field):
    """Toggle 1/0 for group setting (auto_wishes / random_chatter)."""
    if setting_field not in ("auto_wishes", "random_chatter"):
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {setting_field} FROM groups WHERE group_id = ?", (group_id,))
    row = cursor.fetchone()
    if row:
        new_val = 0 if row[0] == 1 else 1
        cursor.execute(f"UPDATE groups SET {setting_field} = ? WHERE group_id = ?", (new_val, group_id))
        conn.commit()
        conn.close()
        return new_val
    conn.close()
    return None

def get_all_dm_users(wishes_only=False, checkins_only=False):
    """Fetch list of user IDs for proactive messages."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT user_id, first_name, nickname FROM users WHERE 1=1"
    if wishes_only:
        query += " AND auto_wishes = 1"
    if checkins_only:
        query += " AND random_checkins = 1"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_groups(wishes_only=False):
    """Fetch list of group IDs."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT group_id, group_title FROM groups WHERE 1=1"
    if wishes_only:
        query += " AND auto_wishes = 1"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_chat_history(chat_id, role, message):
    """Record conversation message in history (keeps last 20 messages per chat)."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (chat_id, role, message, timestamp) VALUES (?, ?, ?, ?)",
                   (chat_id, role, message[:500], now))
    # Prune old messages for this chat to keep DB small
    cursor.execute("""
        DELETE FROM chat_history 
        WHERE chat_id = ? AND id NOT IN (
            SELECT id FROM chat_history WHERE chat_id = ? ORDER BY id DESC LIMIT 20
        )
    """, (chat_id, chat_id))
    conn.commit()
    conn.close()

def get_recent_history(chat_id, limit=6):
    """Fetch recent messages formatted for AI conversation context."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, message FROM chat_history 
        WHERE chat_id = ? 
        ORDER BY id DESC LIMIT ?
    """, (chat_id, limit))
    rows = cursor.fetchall()
    conn.close()
    # Return chronologically
    return [{"role": r["role"], "message": r["message"]} for r in reversed(rows)]

def get_stats():
    """Get total users and groups statistics."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM groups")
    group_count = cursor.fetchone()[0]
    conn.close()
    return {"users": user_count, "groups": group_count}

# Initialize tables at import time
init_db()
