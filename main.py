import os, time, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from telegram.error import Conflict
from langchain_openai import ChatOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

llm = ChatOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    model="llama-3.3-70b-versatile",
    temperature=0.7
)

SYSTEM_PROMPT = """You are Asisten Rabbani.
Roles: Personal assistant, Creative content team, Professional copywriter, Web3 discussion partner.
Skills: caption writing, marketing copywriting, brainstorming content, strategy discussion.
"""

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    response = llm.invoke(SYSTEM_PROMPT + "\nUser: " + user_text)
    await update.message.reply_text(response.content)

def main():
    retries = 0
    while True:
        try:
            app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            logger.info("Asisten Rabbani running...")
            app.run_polling(drop_pending_updates=True)
        except Conflict:
            retries += 1
            wait = min(30 * retries, 120)
            logger.warning(f"Conflict detected, waiting {wait}s before retry...")
            time.sleep(wait)
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
