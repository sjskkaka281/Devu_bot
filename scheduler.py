"""
Background Scheduler for Devu Telegram Bot.
Handles automated Morning/Afternoon/Evening/Night greetings and spontaneous random check-ins.
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

class DevuScheduler:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.tz_name = CONFIG.get("TIMEZONE", "Asia/Kolkata")
        try:
            self.tz = pytz.timezone(self.tz_name)
        except Exception:
            self.tz = pytz.timezone("Asia/Kolkata")

        self.last_sent = {
            "morning": None,
            "afternoon": None,
            "evening": None,
            "night": None,
            "random_checkin": None
        }
        self.running = False
        self.thread = None

    def get_current_time(self):
        """Get current datetime in configured timezone."""
        return datetime.datetime.now(self.tz)

    def send_broadcast_message(self, message_list, is_wish=True):
        """Send greeting/checkin to all registered users and groups."""
        today_date = self.get_current_time().strftime("%Y-%m-%d")
        
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
        logger.info("[+] Devu Background Scheduler running...")
        last_random_time = time.time()
        # Random interval between 2 to 4 hours for spontaneous check-ins
        random_interval = random.randint(7200, 14400)

        while self.running:
            try:
                now = self.get_current_time()
                today_str = now.strftime("%Y-%m-%d")
                hour = now.hour
                minute = now.minute

                if CONFIG.get("AUTO_WISHES", True):
                    # 1. Good Morning (Between 07:00 AM and 08:30 AM)
                    if hour == 7 and minute >= 30 and self.last_sent["morning"] != today_str:
                        logger.info("[Scheduler] Sending Morning Wishes...")
                        self.send_broadcast_message(MORNING_WISHES, is_wish=True)
                        self.last_sent["morning"] = today_str

                    # 2. Good Afternoon (Between 01:00 PM and 02:00 PM)
                    elif hour == 13 and minute >= 15 and self.last_sent["afternoon"] != today_str:
                        logger.info("[Scheduler] Sending Afternoon Lunch Wishes...")
                        self.send_broadcast_message(AFTERNOON_WISHES, is_wish=True)
                        self.last_sent["afternoon"] = today_str

                    # 3. Good Evening (Between 05:30 PM and 06:30 PM)
                    elif hour == 17 and minute >= 45 and self.last_sent["evening"] != today_str:
                        logger.info("[Scheduler] Sending Evening Chai Wishes...")
                        self.send_broadcast_message(EVENING_WISHES, is_wish=True)
                        self.last_sent["evening"] = today_str

                    # 4. Good Night (Between 10:30 PM and 11:30 PM)
                    elif hour == 22 and minute >= 30 and self.last_sent["night"] != today_str:
                        logger.info("[Scheduler] Sending Good Night Wishes...")
                        self.send_broadcast_message(NIGHT_WISHES, is_wish=True)
                        self.last_sent["night"] = today_str

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
