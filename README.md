# 💖 Sona - AI Partner Telegram Chatbot (GitHub 24/7 Cloud)

**Sona (सोना)** ek sweet, caring aur romantic partner Telegram Chatbot hai jo **GitHub Actions Workflow** par 24/7 bina kisi server cost ke chalta hai.

Isko **Multi-Key Groq API Pool** aur **Dynamic Multi-Model Auto-Rotation** ke sath banaya gaya hai taaki **kabhi bhi Rate Limit (429) na lage** aur bot 24/7 bina ruke instant replies de!

---

## ⚡ Multi-Key & Multi-Model Rotation Engine (Kaise Kaam Karta Hai?)

1. **Multi-Model Auto-Switching:**
   - Sona pehle **LLaMA 3.3 70B Versatile** use karta hai.
   - Agar kisi model par rate limit aati hai, to Sona automatically bina drop kiye agle model par switch ho jata hai:
     ```
     LLaMA 3.3 70B ➔ LLaMA 3.1 8B Instant ➔ LLaMA 3 70B ➔ Mixtral 8x7B ➔ Gemma 2 9B ➔ LLaMA 3 8B
     ```
2. **Multi-Key Auto-Rotation:**
   - Jab ek Groq Key ke saare models temporarily exhaust ho jaate hain, Sona automatically **Aapki Next Groq Key** par rotate ho jata hai.
   - Keys ko 60-second cooldown ke baad dobara active kar diya jata hai.
3. **Smart Offline Fallback:**
   - Agar saari keys aur models exhaust ho jayein, to Sona offline intelligent Hinglish rules se reply dega taaki bot **kabhi bhi unresponsive na ho**!

---

## 🚀 GitHub Actions Setup (24/7 Hosting Guide)

### Step 1: Groq API Keys Banayein
[console.groq.com/keys](https://console.groq.com/keys) par jayein aur jitni chahein utni API Keys bana lein (e.g. 2 se 10 keys).

---

### Step 2: GitHub Repository Secrets Me Keys Daalein
1. Apne GitHub Repository me jayein -> **Settings** -> **Secrets and variables** -> **Actions**.
2. **New repository secret** par click karein:

#### Secret 1: `BOT_TOKEN`
- Telegram `@BotFather` ka API Token paste karein.

#### Secret 2: `GROQ_API_KEYS` (Multiple Keys Support)
Aap multiple keys ko **Comma (`,`)** ya **Newline** se alag karke daal sakte hain:
```
gsk_key1_abc123..., gsk_key2_xyz789..., gsk_key3_pqr456...
```
*(Ya fir single key ke liye `gsk_key1` daal sakte hain)*.

---

### Step 3: Workflow Start Karein
1. GitHub Repo ke **Actions** tab me jayein.
2. Left menu me **"Sona Telegram Bot 24/7 Cloud Runner"** par click karein.
3. **Run workflow** button daba dein!

Bot GitHub cloud par **24/7 start ho jayega** aur har 5 ghante me auto-schedule hokar continuous chalega!

---

## 📱 Telegram Live Commands

| Command | Description |
|---|---|
| `/start` | Bot welcome & Partner menu |
| `/setnickname <naam>` | Sona aapko kya bulaye (e.g. `/setnickname Jaan`) |
| `/settings` | Wishes & Random check-ins toggle |
| `/groqstats` | Live Groq Keys count, active model & API requests stats |
| `/stats` | Live connected users aur groups ki report |
| `/wish` | Sweet time-based wish |
| `/shayari` | Dil chhu lene wali romantic shayari |
| `/joke` | Cute jokes aur masti |
| `/broadcast <msg>` | (Owner Only) Sabhi chats me announcement |
