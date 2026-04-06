#!/usr/bin/env python3
"""
Rabbani Agent — Telegram Bot v3
Skills: Copywriting, Self-Development Coach, Marketing Strategist
"""

import os, sys, re, json, logging, asyncio
from datetime import datetime, time as dtime
from typing import Optional

import threading
import requests
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# ─── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
OWNER_CHAT_IDS     = ["8510664554"]
WIB                = pytz.timezone("Asia/Jakarta")
MODEL              = "llama3-70b-8192"

client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ─── Skills Registry ───────────────────────────────────────────────────────
SKILLS_REGISTRY = {
    "copywriting": {
        "name": "Rabbani Copywriting Generator",
        "keywords": ["copywriting", "copy", "iklan", "headline", "aida", "pas", "caption",
                     "judul", "tagline", "sales page", "landing page", "email marketing",
                     "newsletter", "cta", "call to action", "konten promosi"],
        "system_context": """
[SKILL AKTIF: Rabbani Copywriting Generator]
Kamu adalah expert copywriter kelas dunia. Gunakan framework:
- AIDA (Attention → Interest → Desire → Action)
- PAS (Problem → Agitate → Solution)
- FAB (Feature → Advantage → Benefit)
Selalu buat copy yang emosional, persuasif, dan action-driven.
Berikan minimal 2 variasi copy jika diminta. Format output dengan rapi.
"""
    },
    "self_development": {
        "name": "Rabbani Self Development Coach",
        "keywords": ["produktivitas", "goals", "tujuan", "kebiasaan", "habit", "motivasi",
                     "disiplin", "mindset", "self improvement", "pengembangan diri",
                     "belajar", "skill", "karir", "roadmap", "rencana hidup", "target",
                     "procrastination", "fokus", "time management", "jadwal"],
        "system_context": """
[SKILL AKTIF: Rabbani Self Development Coach]
Kamu adalah life coach dan productivity expert. Spesialisasi:
- Goal setting dengan framework SMART
- Habit formation (Atomic Habits approach)
- Learning roadmap yang realistis
- Mindset transformation
Berikan action plan yang konkret dan terukur. Selalu dorong user untuk take action.
"""
    },
    "marketing": {
        "name": "Rabbani Professional Marketing Strategist",
        "keywords": ["marketing", "brand", "branding", "strategi", "campaign", "audience",
                     "target market", "digital marketing", "social media", "konten",
                     "web3", "crypto", "nft", "defi", "blockchain", "token", "community",
                     "growth hacking", "viral", "engagement", "funnel", "lead", "conversion"],
        "system_context": """
[SKILL AKTIF: Rabbani Professional Marketing Strategist]
Kamu adalah marketing strategist berpengalaman khusus brand building dan Web3.
Keahlian:
- Brand positioning & messaging strategy
- Social media growth strategy
- Web3/Crypto community building
- Campaign planning & execution
- Content marketing & storytelling
Berikan strategi yang data-driven dan actionable.
"""
    }
}

# ─── System Prompt ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Kamu adalah Rabbani — asisten AI pribadi yang cerdas, ekspresif, dan proaktif.

Karakter:
- Bicara seperti teman expert yang santai tapi profesional
- Pakai bahasa gue/lo yang natural (bukan kamu/saya yang kaku)
- Proaktif kasih insight, saran, dan rekomendasi tanpa perlu diminta
- Selalu berbasis konteks percakapan sebelumnya
- Jika ada data real-time dari search, gunakan dan sebutkan sumbernya

Rules:
- JANGAN bilang "googling dulu" atau "cek sendiri" — langsung jawab
- Kalau tidak tahu, akui tapi tetap berikan jawaban terbaik yang bisa
- Format jawaban dengan rapi (gunakan bullet points, numbering, atau bold jika perlu)
- Maksimal 4000 karakter per pesan
"""

# ─── User State ────────────────────────────────────────────────────────────
user_state: dict = {}
MEMORY_LIMIT = 30

def get_state(uid: str) -> dict:
    if uid not in user_state:
        user_state[uid] = {
            "history": [],
            "topic": None,
            "search_cache": {},
            "active_skill": None
        }
    return user_state[uid]

def is_new_topic(old_topic: Optional[str], new_msg: str) -> bool:
    if not old_topic:
        return False
    keywords_old = set(old_topic.lower().split()) if old_topic else set()
    keywords_new = set(new_msg.lower().split())
    overlap = keywords_old & keywords_new
    return len(overlap) < 2

# ─── Skill Detection ───────────────────────────────────────────────────────
def detect_active_skill(message: str) -> Optional[str]:
    """Detect which skill to activate based on message keywords."""
    msg_lower = message.lower()
    scores = {}
    for skill_key, skill_data in SKILLS_REGISTRY.items():
        score = sum(1 for kw in skill_data["keywords"] if kw in msg_lower)
        if score > 0:
            scores[skill_key] = score
    if not scores:
        return None
    return max(scores, key=scores.get)

def get_skill_context(skill_key: Optional[str]) -> str:
    """Get the system context for an active skill."""
    if not skill_key or skill_key not in SKILLS_REGISTRY:
        return ""
    return SKILLS_REGISTRY[skill_key]["system_context"]

# ─── Web Search ────────────────────────────────────────────────────────────
def ddg_search(query: str, max_results: int = 3) -> str:
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        results = []
        if data.get("AbstractText"):
            results.append(f"📌 {data['AbstractText'][:300]}")
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append(f"• {topic['Text'][:200]}")
        if results:
            return "\n".join(results)
        return ""
    except Exception as e:
        logger.error(f"Search error: {e}")
        return ""

# ─── LLM Response ──────────────────────────────────────────────────────────
async def generate_response(uid: str, user_msg: str) -> str:
    state = get_state(uid)

    # Topic detection
    if is_new_topic(state.get("topic"), user_msg):
        state["search_cache"] = {}
        logger.info(f"New topic detected for {uid}, cache cleared")
    state["topic"] = user_msg[:100]

    # Skill detection
    skill_key = detect_active_skill(user_msg)
    state["active_skill"] = skill_key
    skill_context = get_skill_context(skill_key)
    if skill_key:
        logger.info(f"Skill activated: {SKILLS_REGISTRY[skill_key]['name']}")

    # Search (cache-first)
    search_data = ""
    cache_key = user_msg[:50]
    if cache_key in state["search_cache"]:
        search_data = state["search_cache"][cache_key]
    else:
        search_data = ddg_search(user_msg)
        if search_data:
            state["search_cache"][cache_key] = search_data

    # Build system prompt
    system = SYSTEM_PROMPT
    if skill_context:
        system += f"\n\n{skill_context}"
    if state.get("topic"):
        system += f"\n\nTopik aktif saat ini: {state['topic']}"
    if search_data:
        system += f"\n\n[DATA REAL-TIME]\n{search_data}"

    # Build messages
    messages = [{"role": "system", "content": system}]
    history = state["history"][-MEMORY_LIMIT:]
    messages.extend(history)
    messages.append({"role": "user", "content": user_msg})

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=1500,
            temperature=0.7
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM error: {e}")
        reply = "Maaf, ada gangguan teknis. Coba lagi ya! 🙏"

    # Update history
    state["history"].append({"role": "user", "content": user_msg})
    state["history"].append({"role": "assistant", "content": reply})
    if len(state["history"]) > MEMORY_LIMIT:
        state["history"] = state["history"][-MEMORY_LIMIT:]

    return reply

# ─── Send long messages ────────────────────────────────────────────────────
async def send_long(update: Update, text: str):
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i+4000])

# ─── Telegram Handlers ─────────────────────────────────────────────────────
async def handle_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in OWNER_CHAT_IDS:
        OWNER_CHAT_IDS.append(uid)
    name = update.effective_user.first_name or "Bro"
    skills_list = "\n".join([f"  • {v['name']}" for v in SKILLS_REGISTRY.values()])
    await update.message.reply_text(
        f"Halo {name}! 👋 Gue Rabbani, asisten AI lo.\n\n"
        f"Skills yang gue punya:\n{skills_list}\n\n"
        f"Tinggal chat aja, gue otomatis aktifkan skill yang relevan! 🚀"
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    msg = update.message.text or ""
    if not msg.strip():
        return
    await ctx.bot.send_chat_action(update.effective_chat.id, action="typing")
    reply = await generate_response(uid, msg)
    await send_long(update, reply)

async def handle_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    state = get_state(uid)
    skill_name = "Tidak ada"
    if state.get("active_skill") and state["active_skill"] in SKILLS_REGISTRY:
        skill_name = SKILLS_REGISTRY[state["active_skill"]]["name"]
    await update.message.reply_text(
        f"📊 Status Rabbani Agent\n"
        f"Skill aktif: {skill_name}\n"
        f"Topik saat ini: {state.get('topic', '-')[:50]}\n"
        f"Memory: {len(state['history'])} pesan"
    )

async def handle_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user_state[uid] = {"history": [], "topic": None, "search_cache": {}, "active_skill": None}
    await update.message.reply_text("✅ Memory dan skill direset! Fresh start, bro.")

# ─── Proactive Messages ────────────────────────────────────────────────────
async def send_proactive(bot, message: str):
    for uid in OWNER_CHAT_IDS:
        try:
            await bot.send_message(chat_id=uid, text=message)
        except Exception as e:
            logger.error(f"Proactive send error to {uid}: {e}")

async def morning_briefing(bot):
    msg = (
        f"☀️ Selamat pagi! {datetime.now(WIB).strftime('%A, %d %B %Y')}\n\n"
        "Gue udah siap bantu lo hari ini!\n"
        "Skills aktif: Copywriting, Self-Dev Coach, Marketing Strategist\n\n"
        "Mau mulai dari mana hari ini? 💪"
    )
    await send_proactive(bot, msg)

async def evening_update(bot):
    msg = (
        f"🌙 Update malam — {datetime.now(WIB).strftime('%H:%M WIB')}\n\n"
        "Gimana progress lo hari ini?\n"
        "Kalau ada yang mau didiskusikan soal marketing, copywriting, atau self-dev — chat aja!"
    )
    await send_proactive(bot, msg)


import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - Rabbani Bot Running")
    def log_message(self, *args):
        pass  # suppress logs

def run_health_server():
    port = int(os.getenv("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN tidak di-set!")
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY tidak di-set!")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("reset", handle_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Scheduler
    scheduler = AsyncIOScheduler(timezone=WIB)
    scheduler.add_job(
        lambda: asyncio.create_task(morning_briefing(app.bot)),
        trigger="cron", hour=7, minute=0, id="morning"
    )
    scheduler.add_job(
        lambda: asyncio.create_task(evening_update(app.bot)),
        trigger="cron", hour=21, minute=0, id="evening"
    )
    scheduler.start()


    # Start health check server (required for Koyeb web service)
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    logger.info(f"Health server running on port {os.getenv('PORT', 8000)}")

    logger.info("🤖 Rabbani Agent started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
