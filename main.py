import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from langchain_openai import ChatOpenAI

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
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Asisten Rabbani running...")
    app.run_polling()

if __name__ == "__main__":
    main()
