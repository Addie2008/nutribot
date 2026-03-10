import os
import logging
import asyncio
from io import BytesIO

from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

from google import genai
import PIL.Image

# -------------------- HARDCODED CREDENTIALS --------------------
GEMINI_API_KEY = "AIzaSyC9PIFsB32r-9qAgapBAxvFsGgHqpGhu4Q"
BOT_TOKEN = "8654917593:AAH-sf5eyJ7Kjl-8EhtvCFk3P0ML3bPqgLU"

# -------------------- Configuration --------------------
MODEL_NAME = "gemini-2.0-flash" 

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# -------------------- Telegram Bot Setup --------------------
bot = Bot(token=BOT_TOKEN)
application = Application.builder().bot(bot).updater(None).build()

# Global flag to track initialization
_initialized = False

async def ensure_init():
    """Properly awaits the async initialization of the bot."""
    global _initialized
    if not _initialized:
        await application.initialize()
        await application.start()
        _initialized = True

# -------------------- Async Handlers --------------------
async def analyze_image_with_gemini(image_bytes: bytes) -> str:
    prompt = """
You are a food analyst expert. Analyze the food product shown in the image (label or package).
Provide: Nutri-Score, Calories, Main ingredients, Nutritional highlights, Overall assessment, and Recommendations.
Use bullet points, emojis, and bold text.
"""
    try:
        image = PIL.Image.open(BytesIO(image_bytes))
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, image]
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return "❌ Sorry, I couldn't analyze the image. Please try again later."

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("👋 Hi! Send me a photo of a food label, and I'll analyze it for you!")

async def handle_photo(update: Update, context: CallbackContext):
    await update.message.reply_text("🔍 Analyzing the image... Please wait.")
    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        analysis = await analyze_image_with_gemini(bytes(image_bytes))

        if len(analysis) <= 4096:
            await update.message.reply_text(analysis, parse_mode="Markdown")
        else:
            for i in range(0, len(analysis), 4096):
                await update.message.reply_text(analysis[i:i+4096], parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("⚠️ Something went wrong.")

# Register Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# -------------------- Flask Webhook Endpoints --------------------
@app.route('/webhook', methods=['POST'])
def webhook():
    async def process():
        await ensure_init()
        update = Update.de_json(request.get_json(force=True), bot)
        await application.process_update(update)
    
    # This runs the async logic inside the sync Flask route
    asyncio.run(process())
    return jsonify({"status": "ok"}), 200

@app.route('/set-webhook', methods=['GET'])
def set_webhook():
    webhook_url = request.url_root.rstrip('/') + '/webhook'
    async def set_it():
        await ensure_init()
        return await bot.set_webhook(url=webhook_url)
    
    success = asyncio.run(set_it())
    return f"✅ Webhook set to {webhook_url}" if success else "❌ Failed", 200

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
