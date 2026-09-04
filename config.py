"""
Configuration Manager for Sona Telegram Bot.
Handles multiple API keys, environment variables, GitHub Secrets, and custom settings.
"""

import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "BOT_TOKEN": "",
    "OWNER_ID": 0,
    "GROQ_API_KEYS": [],       # Supports single string or list of multiple keys
    "GEMINI_API_KEY": "",
    "BOT_NAME": "Sona",
    "TIMEZONE": "Asia/Kolkata",
    "GROUP_RANDOM_REPLY_CHANCE": 0.45,
    "AUTO_WISHES": True,
    "RANDOM_CHECKINS": True,
    "DEFAULT_NICKNAME": "Jaan"
}

def parse_keys_list(raw_val):
    """Parse string, list, or comma/newline-separated keys into a clean list of keys."""
    if not raw_val:
        return []
    if isinstance(raw_val, list):
        return [k.strip() for k in raw_val if isinstance(k, str) and k.strip()]
    if isinstance(raw_val, str):
        # Could be JSON string or delimited
        raw_val = raw_val.strip()
        if raw_val.startswith("[") and raw_val.endswith("]"):
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, list):
                    return [k.strip() for k in parsed if isinstance(k, str) and k.strip()]
            except Exception:
                pass
        
        # Split by comma, newline, semicolon
        delimiters = [",", "\n", ";", " "]
        keys = [raw_val]
        for d in delimiters:
            new_keys = []
            for k in keys:
                new_keys.extend(k.split(d))
            keys = new_keys
        return [k.strip() for k in keys if k.strip() and len(k.strip()) > 5]
    return []

def load_config():
    """Load configuration from config.json and Environment Variables / GitHub Secrets."""
    cfg = DEFAULT_CONFIG.copy()

    # Load from config.json if present
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception as e:
            print(f"[!] Warning: Could not read config.json: {e}")

    # Process GROQ_API_KEYS from config.json
    cfg["GROQ_API_KEYS"] = parse_keys_list(cfg.get("GROQ_API_KEYS") or cfg.get("GROQ_API_KEY") or [])

    # Override with Environment Variables / GitHub Secrets
    if os.environ.get("BOT_TOKEN"):
        cfg["BOT_TOKEN"] = os.environ.get("BOT_TOKEN").strip()

    if os.environ.get("OWNER_ID"):
        try:
            cfg["OWNER_ID"] = int(os.environ.get("OWNER_ID").strip())
        except ValueError:
            pass

    # Environment variable for single or multiple Groq keys
    env_groq = os.environ.get("GROQ_API_KEYS") or os.environ.get("GROQ_API_KEY")
    if env_groq:
        parsed_env_keys = parse_keys_list(env_groq)
        if parsed_env_keys:
            cfg["GROQ_API_KEYS"] = parsed_env_keys

    if os.environ.get("GEMINI_API_KEY"):
        cfg["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY").strip()

    return cfg

def save_config(cfg_dict):
    """Save configuration to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg_dict, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[!] Error saving config: {e}")
        return False

# Initialize configuration
CONFIG = load_config()
