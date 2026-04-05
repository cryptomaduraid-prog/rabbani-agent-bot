import os
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from langchain_openai import ChatOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================
# ENV VARIABLES
# ==========================

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# ==========================
# CONNECT GROQ
# ==========================

llm = ChatOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    model="llama-3.3-70b-versatile",
    temperature=0.7
)

# ==========================
# SYSTEM PROMPT
# ==========================

SYSTEM_PROMPT = """You are Asisten Rabbani.

Roles:
- Personal assistant
- Creative content team
- Professional copywriter
- Web3 discussion partner

Skills:
- caption writing
- marketing copywriting
- brainstorming content
- strategy discussion
"""

# ==========================
# APP HOLDER (for webhook handler)
# ==========================

APP_HOLDER = {'app': None}

# ==========================
# AGENT
# ==========================

async def rabbani_agent(prompt):
    response = llm.invoke(SYSTEM_PROMPT + "\nUser: " + prompt)
    return response.content

# ==========================
# TELEGRAM HANDLER
# ==========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    reply = await rabbani_agent(user_text)
    await update.message.reply_text(reply)

# ==========================
# WEB HANDLERS
# ==========================

async def health_handler(request):
    return web.Response(text="OK", status=200)

async def webhook_handler(request):
    application = APP_HOLDER.get('app')
    if not application:
        return web.Response(status=200)
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(status=200)

# ==========================
# MAIN
# ==========================

async def main():
    # Build telegram app
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Set webhook
    webhook_path = f"https://{WEBHOOK_URL}/webhook" if WEBHOOK_URL else ""
    if webhook_path:
        await application.bot.set_webhook(webhook_path)
        logger.info(f"Webhook set to: {webhook_path}")

    APP_HOLDER['app'] = application

    # Setup aiohttp - register ALL routes BEFORE runner.setup()
    web_app = web.Application()
    web_app.router.add_get('/health', health_handler)
    web_app.router.add_post('/webhook', webhook_handler)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    logger.info(f"Asisten Rabbani running on port {PORT}")

    # Start telegram app
    await application.initialize()
    await application.start()

    # Keep running
    import asyncio
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await application.stop()
        await runner.cleanup()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
