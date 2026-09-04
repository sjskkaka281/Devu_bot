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
import skills
import task as taskmod
import responses as responses_mod

logger = logging.getLogger(__name__)

# (state_key, window start minute-of-day, window end minute-of-day, message pool)
# Wide windows = catch-up guarantee: wish bhejna kabhi miss nahi hota.
WISH_SCHEDULE = [
    ("morning",   7 * 60 + 30, 12 * 60 + 59, MORNING_WISHES),    # 07:30 - 12:59
    ("afternoon", 13 * 60 + 15, 16 * 60 + 59, AFTERNOON_WISHES), # 13:15 - 16:59
    ("evening",   17 * 60 + 45, 21 * 60 + 59, EVENING_WISHES),   # 17:45 - 21:59
    ("night",     22 * 60 + 30, 25 * 60 + 59, NIGHT_WISHES),     # 22:30 - 01:59 (crosses midnight)
]

# Group care windows: meals & health check-ins (per group, once a day)
GROUP_CARE_SCHEDULE = [
    ("breakfast", 8 * 60, 10 * 60 + 30, "GROUP_BREAKFAST_PINGS"),
    ("lunch",     13 * 60, 15 * 60 + 30, "GROUP_LUNCH_PINGS"),
    ("health",    17 * 60, 19 * 60 + 30, "GROUP_HEALTH_CHECKINS"),
    ("dinner",    20 * 60, 22 * 60 + 30, "GROUP_DINNER_PINGS"),
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

        # Spontaneous group chatter timer (every 3-6 hours, waking hours only)
        self.last_group_time = time.time()
        self.group_interval = random.randint(10800, 21600)

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
        """Send a spontaneous friendly message to an active group.
        Fairness: agar koi member chup/shant hai to pehle usko naam se bulati hai,
        taaki kisi ko ignored feel na ho."""
        groups = database.get_all_groups()
        if not groups:
            return
        # Pick one random group
        target_group = random.choice(groups)
        gid = target_group["group_id"]
        try:
            quiet = skills.get_quiet_member(gid)
            if quiet and random.random() < 0.6:
                name = quiet["first_name"] or quiet["username"] or "Jaan"
                text = random.choice(skills.QUIET_MEMBER_PINGS).format(name=name)
                self.bot.send_message(gid, text)
                skills.mark_addressed(gid, quiet["user_id"])
            else:
                text = random.choice(GROUP_RANDOM_CHAT)
                self.bot.send_message(gid, text)
        except Exception as e:
            logger.debug(f"Could not send random chatter to group {gid}: {e}")

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
                        last_random_time = time.time()
                        random_interval = random.randint(7200, 14400)

                # 6. Spontaneous group chatter (every 3-6 hours, 10 AM - 9 PM IST)
                if (10 <= hour <= 21) and (time.time() - self.last_group_time > self.group_interval):
                    logger.info("[Scheduler] Sending spontaneous group chatter...")
                    self.send_random_group_chatter()
                    self.last_group_time = time.time()
                    self.group_interval = random.randint(10800, 21600)

                # 7. User tasks & reminders (DM + groups, 30-min retry until confirmed)
                self.run_tasks(now)

                # 8. Group care: breakfast/lunch/dinner + health/halchal check-ins
                self.run_group_care(now)

            except Exception as e:
                logger.error(f"[Scheduler Exception] {e}")

            time.sleep(30)  # Check every 30 seconds

    def run_tasks(self, now):
        """Due tasks ko puchho (time aa gaya, done nahi, 30 min retry window)."""
        for t in taskmod.get_due(now):
            try:
                name = t["user_name"] or "Jaan"
                line = random.choice(taskmod.REMINDER_LINES).format(name=name, title=t["title"])
                self.bot.send_message(t["chat_id"], line)
                taskmod.mark_asked(t["id"], now)
                logger.info(f"[Tasks] Asked task #{t['id']} ('{t['title']}') in chat {t['chat_id']}")
            except Exception as e:
                logger.debug(f"Task ask failed #{t['id']}: {e}")

    def run_group_care(self, now):
        """Har group me breakfast/lunch/dinner + health/halchal — roz ek baar har window me."""
        minutes = now.hour * 60 + now.minute
        day_str = now.strftime("%Y-%m-%d")
        groups = database.get_all_groups()
        if not groups:
            return
        for key, start, end, list_name in GROUP_CARE_SCHEDULE:
            if not (start <= minutes <= end):
                continue
            pool = getattr(responses_mod, list_name)
            for g in groups:
                state_key = f"gcare_{key}_{g['group_id']}"
                if database.get_state(state_key) == day_str:
                    continue
                try:
                    self.bot.send_message(g["group_id"], random.choice(pool))
                    database.set_state(state_key, day_str)
                    logger.info(f"[GroupCare] {key} ping sent to {g['group_id']}")
                    time.sleep(0.08)
                except Exception as e:
                    logger.debug(f"Group care {key} failed for {g['group_id']}: {e}")

    def start(self):
        """Start scheduler in background daemon thread."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.scheduler_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop scheduler."""
        self.running = False
