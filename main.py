import os, logging, time
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from telegram.error import Conflict, NetworkError
from langchain_openai import ChatOpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
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
Respond in the same language as the user (Indonesian or English).
"""

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_text = update.message.text
        logger.info(f"Message from {update.effective_user.username}: {user_text[:50]}")
        response = llm.invoke(SYSTEM_PROMPT + "\nUser: " + user_text)
        await update.message.reply_text(response.content)
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("Maaf, terjadi error. Silakan coba lagi.")

def main():
    retry = 0
    while True:
        try:
            logger.info(f"Starting Asisten Rabbani bot (attempt {retry+1})...")
            app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            app.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                poll_interval=1.0,
                timeout=30
            )
        except Conflict:
            wait = min(30 * (retry + 1), 120)
            logger.warning(f"Conflict - another instance running. Waiting {wait}s...")
            time.sleep(wait)
            retry += 1
        except NetworkError as e:
            logger.warning(f"Network error: {e}. Retrying in 15s...")
            time.sleep(15)
        except Exception as e:
            logger.error(f"Fatal error: {e}. Restarting in 10s...")
            time.sleep(10)
            retry += 1

if __name__ == "__main__":
    main()
