"""
Food Label Analyzer Bot for Telegram
Webhook version for Render deployment
"""

import os
import logging
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters, CallbackContext
from google import genai
import PIL.Image
from io import BytesIO
import asyncio

# ---------- Configuration ----------
GEMINI_API_KEY = "AIzaSyC9PIFsB32r-9qAgapBAxvFsGgHqpGhu4Q"  # Your hardcoded key
BOT_TOKEN = "8654917593:AAH-sf5eyJ7Kjl-8EhtvCFk3P0ML3bPqgLU"  # Replace with your token

# Initialize
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, update_queue=None, workers=4)
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3-flash-preview"

# Flask app for webhook
app = Flask(__name__)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Bot Logic ----------
async def analyze_image_with_gemini(image_bytes):
    """Analyze food image with Gemini"""
    prompt = """
You are a food analyst expert. Analyze the food product shown in the image.
Provide: Nutri-Score (A-E), Calories per 100g/serving, Main ingredients with problematic ones highlighted,
Nutritional highlights, Overall assessment, Recommendations.
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
    await update.message.reply_text(
        "👋 Hi! Send me a photo of a food product label or package, and I'll analyze it "
        "with AI to give you a Nutri-Score, ingredient warnings, and more!"
    )

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📸 Just send a clear photo of the food label. I'll do the rest!"
    )

async def handle_photo(update: Update, context: CallbackContext):
    """Process incoming photo messages"""
    await update.message.reply_text("🔍 Analyzing the image... This may take a few seconds.")

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        
        analysis = await analyze_image_with_gemini(bytes(image_bytes))
        
        # Telegram message limit is 4096 characters
        if len(analysis) <= 4096:
            await update.message.reply_text(analysis, parse_mode="Markdown")
        else:
            parts = [analysis[i:i+4096] for i in range(0, len(analysis), 4096)]
            for part in parts:
                await update.message.reply_text(part, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")

# Register handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# ---------- Webhook Endpoint ----------
@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint for Telegram to send updates"""
    update = Update.de_json(request.get_json(force=True), bot)
    
    # Process update asynchronously
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(dispatcher.process_update(update))
    loop.close()
    
    return jsonify({"status": "ok"}), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Render"""
    return jsonify({"status": "healthy"}), 200

@app.route('/set-webhook', methods=['GET'])
def set_webhook():
    """Helper endpoint to set the webhook URL"""
    webhook_url = request.url_root.rstrip('/') + '/webhook'
    success = bot.set_webhook(url=webhook_url)
    if success:
        return f"Webhook set to {webhook_url}", 200
    else:
        return "Failed to set webhook", 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)