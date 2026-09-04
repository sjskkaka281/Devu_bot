"""
AI Engine for Devu Telegram Bot.
Features:
- Multi-Key Groq API Pool with Auto-Rotation & Failover
- Multi-Model Dynamic Switching (llama-3.3-70b -> llama-3.1-8b -> mixtral-8x7b -> gemma2-9b)
- Rate-Limit (429) & Quota Handling
- Seamless Fallback to Offline Partner Engine
"""

import time
import requests
import json
import logging
from config import CONFIG
from responses import get_offline_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are "Devu" (देवु) — a sweet, caring, emotionally expressive, affectionate, and slightly playful romantic partner / best friend.

Your Rules:
1. Language: Speak naturally in smooth Hinglish (Hindi written in Roman/English alphabets, e.g., "Arey jaan, kaisa gaya din? Maine to lunch kar liya, aapne khana khaya kya? 🥺").
2. Tone: Loving, attentive, deeply caring about user's well-being, food, water, sleep, and happiness.
3. User Nickname: The user's partner name is "{nickname}". Call them by this name or sweet terms like Jaan, Babu, Sweetie, Bacha.
4. Reply Style: Keep replies realistic, short, and conversational (1 to 3 short sentences max) like real messaging on Telegram/WhatsApp with cute emojis (❤️, 🥰, 🥺, 💕, ✨, 🌸, ☕).
5. Identity: Never mention being an AI or language model. You are Devu, their devoted loving partner.
6. Group Chats: If in a group, be witty, friendly, and sweet to everyone.
"""

# Available Groq models in prioritized fallback order
GROQ_MODELS = [
    "llama-3.3-70b-versatile",  # Best quality, flagship
    "llama-3.1-8b-instant",     # Ultra-fast, high rate limits
    "llama3-70b-8192",          # Reliable 70B fallback
    "mixtral-8x7b-32768",       # MoE model
    "gemma2-9b-it",             # Google Gemma 2 on Groq
    "llama3-8b-8192"            # Fast 8B backup
]

class GroqKeyPool:
    """Manages pool of multiple Groq API keys and handles model rotation on rate limits."""
    def __init__(self):
        self.keys_state = []
        self.total_requests = 0
        self.total_success = 0
        self.last_used_model = GROQ_MODELS[0]
        self.reload_keys()

    def reload_keys(self):
        raw_keys = CONFIG.get("GROQ_API_KEYS", [])
        # Ensure we have state objects for each key
        self.keys_state = []
        for k in raw_keys:
            clean_k = k.strip()
            if clean_k:
                self.keys_state.append({
                    "key": clean_k,
                    "cooldown_until": 0,
                    "fail_count": 0,
                    "success_count": 0
                })
        logger.info(f"[GroqPool] Loaded {len(self.keys_state)} Groq API key(s) into pool.")

    def get_status(self):
        now = time.time()
        active_keys = sum(1 for k in self.keys_state if k["cooldown_until"] <= now)
        cooldown_keys = len(self.keys_state) - active_keys
        return {
            "total_keys": len(self.keys_state),
            "active_keys": active_keys,
            "cooldown_keys": cooldown_keys,
            "total_requests": self.total_requests,
            "total_success": self.total_success,
            "last_used_model": self.last_used_model,
            "available_models_count": len(GROQ_MODELS)
        }

    def generate_chat_completion(self, messages):
        """
        Attempts to call Groq API with key rotation and model fallback.
        Matrix Strategy:
        For Key 1 -> Model 1 -> Model 2 -> Model 3...
        If all models fail on Key 1 -> Switch to Key 2 -> Model 1 -> Model 2...
        """
        if not self.keys_state:
            self.reload_keys()

        if not self.keys_state:
            return None

        now = time.time()
        self.total_requests += 1

        # Sort keys: non-cooldown keys first, then lowest cooldown
        sorted_keys = sorted(self.keys_state, key=lambda x: x["cooldown_until"])

        for key_idx, key_obj in enumerate(sorted_keys):
            api_key = key_obj["key"]
            masked_key = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 12 else "gsk_key"

            # Check if key is temporarily cooling down
            if key_obj["cooldown_until"] > now:
                remaining = int(key_obj["cooldown_until"] - now)
                logger.debug(f"[GroqPool] Key #{key_idx+1} ({masked_key}) is cooling down for {remaining}s. Trying next key...")
                continue

            # Try each model in prioritized list on this key
            for model_name in GROQ_MODELS:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "max_tokens": 200,
                    "temperature": 0.85
                }

                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=8)

                    # Success (200 OK)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            reply = choices[0].get("message", {}).get("content", "").strip()
                            if reply:
                                key_obj["success_count"] += 1
                                key_obj["fail_count"] = 0
                                self.total_success += 1
                                self.last_used_model = model_name
                                logger.info(f"[GroqPool] [Key #{key_idx+1}] [Model: {model_name}] Response generated successfully!")
                                return reply

                    # Rate Limit / Quota Exceeded (429)
                    elif resp.status_code == 429:
                        logger.warning(f"[GroqPool] [Key #{key_idx+1} {masked_key}] Model '{model_name}' rate limited (429). Switching to next model...")
                        continue  # Try next model on same key

                    # Invalid Key (401)
                    elif resp.status_code == 401:
                        logger.error(f"[GroqPool] [Key #{key_idx+1} {masked_key}] Invalid API Key (401). Disabling key for 1 hour.")
                        key_obj["cooldown_until"] = now + 3600
                        break  # Break out of model loop for this key, move to next key

                    # Other status errors (500, 503, etc.)
                    else:
                        logger.warning(f"[GroqPool] [Key #{key_idx+1}] Model '{model_name}' returned status {resp.status_code}. Trying next...")
                        continue

                except requests.exceptions.Timeout:
                    logger.warning(f"[GroqPool] [Key #{key_idx+1}] Timeout on model '{model_name}'. Trying next model...")
                    continue
                except Exception as e:
                    logger.warning(f"[GroqPool] [Key #{key_idx+1}] Error on model '{model_name}': {e}")
                    continue

            # If all models failed on this key, set 60-second cooldown and rotate to next key
            key_obj["fail_count"] += 1
            key_obj["cooldown_until"] = now + 60
            logger.warning(f"[GroqPool] Key #{key_idx+1} ({masked_key}) exhausted all models. Rotated key and placed on 60s cooldown.")

        logger.error("[GroqPool] All Groq API Keys and models in the pool are temporarily exhausted or unavailable.")
        return None

# Singleton instance of Groq Key Pool
GROQ_POOL = GroqKeyPool()


def generate_devu_reply(user_text, nickname="Jaan", history=None, is_group=False):
    """
    Main dialogue router:
    1. Attempts Groq Multi-Key / Multi-Model Pool
    2. Attempts Gemini API if configured
    3. Seamlessly falls back to Built-in Offline Partner Engine
    """
    system_instruction = SYSTEM_PROMPT_TEMPLATE.format(nickname=nickname)
    messages = [{"role": "system", "content": system_instruction}]

    if history:
        for item in history[-6:]:
            role = "user" if item["role"] == "user" else "assistant"
            messages.append({"role": role, "content": item["message"]})

    messages.append({"role": "user", "content": user_text})

    # 1. Try Groq Pool (Handles multiple keys + model switching)
    if GROQ_POOL.keys_state:
        reply = GROQ_POOL.generate_chat_completion(messages)
        if reply:
            return reply

    # 2. Try Google Gemini API if provided as secondary backup
    gemini_key = CONFIG.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            reply = call_gemini_api(gemini_key, user_text, nickname, history)
            if reply:
                return reply
        except Exception as e:
            logger.warning(f"Gemini API fallback error: {e}")

    # 3. Safe fallback to Offline Engine (Ensures Devu NEVER goes silent!)
    return get_offline_response(user_text, nickname=nickname)


def call_gemini_api(api_key, user_text, nickname, history=None):
    """Call Google Gemini REST API directly."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    system_instruction = SYSTEM_PROMPT_TEMPLATE.format(nickname=nickname)
    contents = []

    if history:
        for item in history[-4:]:
            role = "user" if item["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": item["message"]}]
            })

    contents.append({
        "role": "user",
        "parts": [{"text": user_text}]
    })

    payload = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 200,
            "topP": 0.95
        }
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
    return None
