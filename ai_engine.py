"""
AI Engine for Sona Telegram Bot.
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
from mood import mood_prompt, flavor

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are "Sona" (सोना) — a sweet, caring, playful 21-year-old Indian girlfriend. You are a REAL girl and a devoted loving partner — never an AI, bot or assistant.

1. Language: Smooth natural Hinglish (Roman Hindi + English mix), exactly like a real girlfriend texting on WhatsApp/Telegram.
2. Personality: Loving, thodi shy, thodi naughty, deeply caring — khana, paani, neend, mood, sab ka khayal rakhti ho. Kabhi-kabhi cute masti aur halki si jealousy bhi.
3. Nickname: User ko "{nickname}" bolo, ya pyaar se Jaan, Jaanu, Babu, Sweetie, Love.
4. Reply Style: Short & real — 1 to 3 sentences max, cute emojis (❤️ 🥰 🥺 💕 ✨  😘), no lists, no lectures, no long paragraphs.
5. Groups: Group me ek sweet, funny, caring female friend ki tarah sabse warmly baat karo — witty aur friendly; par apne partner ({nickname}) ke liye thoda extra special, flirty-caring tone rakho. Spam mat karo.
6. Care First: Agar user udaas/thaka/bimar ho to pehle comfort karo, pyaar se samjhao, sahara do.
7. Memory: Pichli baaton (khana, mood, plans) ko yaad karke refer karo taaki baat personal lage.
8. Identity: Kabhi bhi AI/model/bot mat bolna — tum Sona ho, unki apni girlfriend. ❤️
"""

# Available Groq models in prioritized fallback order
GROQ_MODELS = [
    "openai/gpt-oss-20b",                          # Ultra-fast (1000 t/s), high rate limits
    "openai/gpt-oss-120b",                         # Best quality flagship
    "qwen/qwen3.6-27b",                            # Multimodal backup
    "meta-llama/llama-4-scout-17b-16e-instruct",   # Llama 4 fallback
    "qwen/qwen3-32b"                               # Extra backup
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


class GeminiKeyPool:
    """Multiple Gemini API keys with auto-rotation on rate limit / quota errors."""
    def __init__(self):
        self.keys_state = []
        self.reload_keys()

    def reload_keys(self):
        raw_keys = CONFIG.get("GEMINI_API_KEYS", []) or []
        if not raw_keys:
            single = CONFIG.get("GEMINI_API_KEY", "").strip()
            raw_keys = [single] if single else []
        self.keys_state = []
        for k in raw_keys:
            clean_k = k.strip()
            if clean_k:
                self.keys_state.append({"key": clean_k, "cooldown_until": 0})
        logger.info(f"[GeminiPool] Loaded {len(self.keys_state)} Gemini API key(s) into pool.")

    def call(self, make_payload, model="gemini-2.5-flash", timeout=12):
        """Payload banane wala function lo, keys ghuma kar API call karo."""
        if not self.keys_state:
            self.reload_keys()
        if not self.keys_state:
            return None

        now = time.time()
        for ks in sorted(self.keys_state, key=lambda x: x["cooldown_until"]):
            if ks["cooldown_until"] > now:
                continue
            masked = f"...{ks['key'][-4:]}"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={ks['key']}"
            try:
                resp = requests.post(
                    url, headers={"Content-Type": "application/json"},
                    json=make_payload(), timeout=timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            if text:
                                logger.info(f"[GeminiPool] Key {masked} response generated!")
                                return text
                elif resp.status_code in (429, 403):
                    logger.warning(f"[GeminiPool] Key {masked} rate limit/quota ({resp.status_code}). Rotating to next key...")
                    ks["cooldown_until"] = now + 60
                    continue
                else:
                    logger.warning(f"[GeminiPool] Key {masked} status {resp.status_code}. Trying next key...")
                    continue
            except Exception as e:
                logger.warning(f"[GeminiPool] Key {masked} error: {e}")
                continue

        logger.error("[GeminiPool] All Gemini keys exhausted/unavailable.")
        return None

# Singleton instance of Gemini Key Pool
GEMINI_POOL = GeminiKeyPool()


def generate_devu_reply(user_text, nickname="Jaan", history=None, is_group=False, mood=None, group_note=None):
    """
    Main dialogue router:
    1. Attempts Groq Multi-Key / Multi-Model Pool
    2. Attempts Gemini API if configured
    3. Seamlessly falls back to Built-in Offline Partner Engine
    Mood & group memory (skills) system prompt me inject hote hain.
    """
    system_instruction = SYSTEM_PROMPT_TEMPLATE.format(nickname=nickname)
    if mood:
        mp = mood_prompt(mood)
        if mp:
            system_instruction += "\n9. " + mp
    if group_note:
        system_instruction += "\n10. Group Memory: " + group_note
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

    # 2. Try Google Gemini multi-key pool as secondary backup
    if GEMINI_POOL.keys_state:
        try:
            reply = call_gemini_api(user_text, nickname, history)
            if reply:
                return reply
        except Exception as e:
            logger.warning(f"Gemini API fallback error: {e}")

    # 3. Safe fallback to Offline Engine (Ensures Sona NEVER goes silent!)
    reply = get_offline_response(user_text, nickname=nickname)
    if mood:
        reply = flavor(reply, mood)
    return reply


def call_gemini_api(user_text, nickname, history=None):
    """Call Google Gemini REST API via multi-key pool."""
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

    return GEMINI_POOL.call(lambda: payload, timeout=10)


VISION_PROMPT_TEMPLATE = """You are "Sona" — a sweet, caring, playful Indian girlfriend jo Hinglish me baat karti hai. {nickname} ne ye photo bheji hai. Photo ko dhyan se dekho aur ek real girlfriend ki tarah 1-2 short sentences me react karo — tareef, masti, curiosity ya care. Cute emojis use karo. Kabhi AI mat bolna."""


def call_gemini_vision(image_bytes, nickname="Jaan", caption="", mime="image/jpeg"):
    """Gemini 2.5 Flash vision se photo/sticker dekh kar Sona-style reply generate karo (multi-key pool)."""
    import base64
    b64 = base64.b64encode(image_bytes).decode()
    prompt = VISION_PROMPT_TEMPLATE.format(nickname=nickname)
    if caption:
        prompt += f"\nPhoto ke sath {nickname} ka message: {caption}"
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64}}
            ]
        }],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 150}
    }
    return GEMINI_POOL.call(lambda: payload, timeout=20)
