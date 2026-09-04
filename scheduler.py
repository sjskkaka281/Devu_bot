"""
Background Scheduler for Sona Telegram Bot.
Handles automated Morning/Afternoon/Evening/Night greetings and spontaneous random check-ins.

Reliability: wish state is persisted in the SQLite database (bot_state table), so even if
the bot restarts (GitHub Actions 5-hour sessions) a wish is NEVER skipped and NEVER sent
twice on the same day. If the bot was offline at the exact wish time, the wish is sent as
soon as the bot comes back online within that wish's window (catch-up).
"""

import time
import random
import datetime
import threading
import logging
import pytz
from config import CONFIG
from responses import (
    MORNING_WISHES, AFTERNOON_WISHES, EVENING_WISHES, NIGHT_WISHES,
    RANDOM_CHECKINS, GROUP_RANDOM_CHAT
)
import database

logger = logging.getLogger(__name__)

# (state_key, window start minute-of-day, window end minute-of-day, message pool)
# Wide windows = catch-up guarantee: wish bhejna kabhi miss nahi hota.
WISH_SCHEDULE = [
    ("morning",   7 * 60 + 30, 12 * 60 + 59, MORNING_WISHES),    # 07:30 - 12:59
    ("afternoon", 13 * 60 + 15, 16 * 60 + 59, AFTERNOON_WISHES), # 13:15 - 16:59
    ("evening",   17 * 60 + 45, 21 * 60 + 59, EVENING_WISHES),   # 17:45 - 21:59
    ("night",     22 * 60 + 30, 25 * 60 + 59, NIGHT_WISHES),     # 22:30 - 01:59 (crosses midnight)
]


class DevuScheduler:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.tz_name = CONFIG.get("TIMEZONE", "Asia/Kolkata")
        try:
            self.tz = pytz.timezone(self.tz_name)
        except Exception:
            self.tz = pytz.timezone("Asia/Kolkata")

        self.running = False
        self.thread = None

    def get_current_time(self):
        """Get current datetime in configured timezone."""
        return datetime.datetime.now(self.tz)

    @staticmethod
    def _wish_day(now):
        """Calendar day a wish belongs to (after midnight, night wish counts for previous day)."""
        day = now.date()
        if now.hour < 6:
            day -= datetime.timedelta(days=1)
        return day.strftime("%Y-%m-%d")

    def get_due_wishes(self, now):
        """Return [(key, pool, day_str)] for wishes whose window is open and not yet sent for that day."""
        minutes = now.hour * 60 + now.minute
        if minutes < 6 * 60:          # 00:00-05:59 -> continuation of previous day's night window
            minutes += 24 * 60
        day_str = self._wish_day(now)
        due = []
        for key, start, end, pool in WISH_SCHEDULE:
            if start <= minutes <= end and database.get_state("wish_" + key) != day_str:
                due.append((key, pool, day_str))
        return due

    def send_broadcast_message(self, message_list, is_wish=True):
        """Send greeting/checkin to all registered users and groups."""
        # 1. Send to private chat users
        users = database.get_all_dm_users(wishes_only=is_wish, checkins_only=(not is_wish))
        for u in users:
            try:
                user_id = u["user_id"]
                nickname = u.get("nickname") or u.get("first_name") or "Jaan"
                text = random.choice(message_list).format(name=nickname)
                self.bot.send_message(user_id, text)
                time.sleep(0.08)  # Prevent flood limit
            except Exception as e:
                # If user blocked bot or chat deleted, log quietly
                logger.debug(f"Could not send to user {u.get('user_id')}: {e}")

        # 2. If it's a greeting, optionally send to registered groups too
        if is_wish:
            groups = database.get_all_groups(wishes_only=True)
            for g in groups:
                try:
                    group_id = g["group_id"]
                    text = random.choice(message_list).format(name="Friends / Group")
                    self.bot.send_message(group_id, text)
                    time.sleep(0.08)
                except Exception as e:
                    logger.debug(f"Could not send to group {g.get('group_id')}: {e}")

    def send_random_group_chatter(self):
        """Send a spontaneous friendly message to an active group."""
        groups = database.get_all_groups()
        if not groups:
            return
        # Pick one random group
        target_group = random.choice(groups)
        try:
            text = random.choice(GROUP_RANDOM_CHAT)
            self.bot.send_message(target_group["group_id"], text)
        except Exception as e:
            logger.debug(f"Could not send random chatter to group {target_group['group_id']}: {e}")

    def scheduler_loop(self):
        """Continuous background loop checking clock & triggers."""
        logger.info("[+] Sona Background Scheduler running...")
        last_random_time = time.time()
        # Random interval between 2 to 4 hours for spontaneous check-ins
        random_interval = random.randint(7200, 14400)

        while self.running:
            try:
                now = self.get_current_time()
                hour = now.hour

                # 1-4. Daily wishes with DB-backed catch-up (never skipped, never repeated)
                if CONFIG.get("AUTO_WISHES", True):
                    for key, pool, day_str in self.get_due_wishes(now):
                        logger.info(f"[Scheduler] Sending {key} wishes for {day_str}...")
                        self.send_broadcast_message(pool, is_wish=True)
                        database.set_state("wish_" + key, day_str)

                # 5. Spontaneous Random Check-ins (Between 10 AM and 9 PM IST)
                if CONFIG.get("RANDOM_CHECKINS", True) and (10 <= hour <= 21):
                    if time.time() - last_random_time > random_interval:
                        logger.info("[Scheduler] Triggering Spontaneous Partner Check-in...")
                        self.send_broadcast_message(RANDOM_CHECKINS, is_wish=False)
                        # Also occasionally send a fun chime-in into groups
                        if random.random() < 0.4:
                            self.send_random_group_chatter()
                        last_random_time = time.time()
                        random_interval = random.randint(7200, 14400)

            except Exception as e:
                logger.error(f"[Scheduler Exception] {e}")

            time.sleep(30)  # Check every 30 seconds

    def start(self):
        """Start scheduler in background daemon thread."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.scheduler_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop scheduler."""
        self.running = False
