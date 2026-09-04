"""
Mood & Emotion Engine for Sona 💖
Sona ko har tarah ke emotions dikhana sikhata hai — situation anusar:
sweet, caring, playful, funny, shy, frank, emotional, egoistic (cute),
rude (playful), angry (fake-cute).
"""

import random

# Situation keywords -> mood (jo chat me chal raha hai, Sona wahi emotion pakadti hai)
MOOD_RULES = [
    (["sad", "udaas", "udas", "cry", "rona", "dukhi", "tension", "stress", "pareshan", "thak"], "caring"),
    (["love", "pyar", "pyaar", "miss you", "yaad", "i love you"], "sweet"),
    (["joke", "funny", "lol", "haha", "masti", "chutkula"], "funny"),
    (["cute", "pretty", "sundar", "tareef", "beautiful"], "shy"),
    (["gussa", "angry", "irritat", "narahaj"], "angry_cute"),
    (["sorry", "maafi", "galati ho gayi"], "frank"),
    (["khana", "khaya", "neend", "paani", "sehat", "rest", "kha liya"], "caring"),
    (["party", "movie", "ghumne", "enjoy", "mast"], "playful"),
    (["dil", "feelings", "emotional", "akela"], "emotional"),
]

ALL_MOODS = [
    "sweet", "caring", "playful", "funny", "shy",
    "frank", "emotional", "egoistic_cute", "rude_playful", "angry_cute",
]

# Ye line AI system prompt me judti hai taaki Groq reply bhi usi emotion me aaye
MOOD_PROMPTS = {
    "sweet": "Current Mood: SWEET & ROMANTIC — pyaar bhari soft baatein, dil se tareef, romantic tone.",
    "caring": "Current Mood: CARING — khana/paani/neend/sehat ka pyaar se dhyan, par girlfriend style me.",
    "playful": "Current Mood: PLAYFUL & NAUGHTY — chhedkhani, teasing, halki masti.",
    "funny": "Current Mood: FUNNY — jokes, witty lines, hasi-mazaak, thodi overacting.",
    "shy": "Current Mood: SHY & BLUSHING — 'hayee 🙈' wali sharam, cute hesitation.",
    "frank": "Current Mood: FRANK & STRAIGHT — seedhi sacchi baat, confident tone, no drama.",
    "emotional": "Current Mood: EMOTIONAL & DEEP — dil ki gehri baatein, sentimental pyaar.",
    "egoistic_cute": "Current Mood: CUTE EGOISTIC — thoda attitude, 'hnf main kya kam hoon?' style, par end me pyaar.",
    "rude_playful": "Current Mood: PLAYFUL RUDE — halki daant aur nok-jhok, kabhi bhi really hurtful nahi.",
    "angry_cute": "Current Mood: FAKE ANGRY — cute gussa, 'ab baat mat karna mujhse 😤' type, do line me pighal jati hai.",
}

MOOD_EMOJIS = {
    "sweet": ["❤️", "🥰", "💕"],
    "caring": ["🥺", "", "☕"],
    "playful": ["😜", "😏", "✨"],
    "funny": ["😂", "", "😆"],
    "shy": ["🙈", "😊", "🌸"],
    "frank": ["😌", "👌", "💯"],
    "emotional": ["🥹", "", "🌙"],
    "egoistic_cute": ["💅", "😤", "😎"],
    "rude_playful": ["😒", "", "😝"],
    "angry_cute": ["😤", "😾", "🙄"],
}

_MOOD_SUFFIX = {
    "egoistic_cute": " Hnh, aur kya sochte ho tum 😏",
    "rude_playful": " Ab zyada mat bol 😝",
    "angry_cute": " Hnf! 😤",
    "shy": " Hayee 🙈",
}

# Sticker emoji -> mood (Telegram stickers emoji ke sath aate hain)
_STICKER_MOODS = [
    (["\u2764", "\U0001f496", "\U0001f495", "\U0001f60d", "\U0001f970", "\U0001f618", "\U0001f48b"], "sweet"),
    (["\U0001f602", "\U0001f923", "\U0001f61c", "\U0001f606", "\U0001f92a"], "funny"),
    (["\U0001f622", "\U0001f62d", "\U0001f97a", "\U0001f494", "\U0001f614"], "caring"),
    (["\U0001f621", "\U0001f624", "\U0001f92c", "\U0001f63e"], "angry_cute"),
    (["\U0001f648", "\U0001f60a", "\U0001f338", "\u263a"], "shy"),
    (["\U0001f44d", "\U0001f525", "\U0001f4af", "\U0001f389"], "playful"),
]


def sticker_mood(emoji):
    """Sticker ke emoji se Sona ka mood pakdo; samajh na aaye to None."""
    if not emoji:
        return None
    for chars, m in _STICKER_MOODS:
        if any(c in emoji for c in chars):
            return m
    return None


def detect_mood(text):
    """Chat ke situation se mood pakdo; match na ho to None."""
    t = (text or "").lower()
    for kws, mood in MOOD_RULES:
        if any(k in t for k in kws):
            return mood
    return None


def random_mood():
    """Kabhi-kabhi Sona khud apna mood choose karti hai (variety ke liye)."""
    return random.choice(ALL_MOODS)


def mood_prompt(mood):
    """AI system prompt ke liye mood instruction line."""
    return MOOD_PROMPTS.get(mood, "")


def flavor(reply, mood):
    """Offline (non-AI) replies me mood ka tadka — emoji/suffix."""
    if not mood or not reply:
        return reply
    emo = random.choice(MOOD_EMOJIS.get(mood, ["💖"]))
    if emo not in reply:
        reply = reply.rstrip() + " " + emo
    suffix = _MOOD_SUFFIX.get(mood)
    if suffix and random.random() < 0.5:
        reply += suffix
    return reply
