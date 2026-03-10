"""
Food Label Analyzer Bot for Telegram
Webhook version for Render – using Python 3.11 and Gemini 2.0 Flash
"""

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
GEMINI_API_KEY = "AIzaSyC9PIFsB32r-9qAgapBAxvFsGgHqpGhu4Q"   # Your Gemini key
BOT_TOKEN = "8654917593:AAH-sf5eyJ7Kjl-8EhtvCFk3P0ML3bPqgLU"                   # <-- REPLACE WITH YOUR TOKEN

# -------------------- Configuration --------------------
MODEL_NAME = "gemini-2.0-flash"  # Stable model

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
# Disable Updater for webhook mode
application = Application.builder().bot(bot).updater(None).build()

# IMPORTANT: Initialize the application before using it
application.initialize()

# -------------------- Async Handlers --------------------
async def analyze_image_with_gemini(image_bytes: bytes) -> str:
    """Send image to Gemini and return analysis."""
    prompt = """
You are a food analyst expert. Analyze the food product shown in the image (label or package).
Provide the following information in a clear, nicely formatted way:

- **Nutri-Score** (A, B, C, D, or E) based on European standards, with a brief explanation.
- **Calories**: per 100g/ml and per typical serving (if visible).
- **Main ingredients** list, highlighting any problematic ones (e.g., high sugar, saturated fat, salt, additives, E-numbers, allergens). Explain why they might be concerning.
- **Nutritional highlights** (e.g., high fiber, protein, vitamins) if any.
- **Overall assessment**: a short summary of the product's healthiness.
- **Recommendations**: suggestions for healthier alternatives or consumption tips.

Use bullet points, emojis, and bold text to make the answer easy to read. If any information is missing from the label, state that it's not visible.
"""
    try:
        image = PIL.Image.open(BytesIO(image_bytes))
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, image]
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        return "❌ Sorry, I couldn't analyze the image. Please try again later."

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "👋 Hi! Send me a photo of a food product label or package, and I'll analyze it "
        "with AI to give you a Nutri-Score, ingredient warnings, and more!"
    )

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📸 Just send a clear photo of the food label (ingredients, nutrition facts, front package). "
        "I'll do the rest!"
    )

async def handle_photo(update: Update, context: CallbackContext):
    """Process incoming photo messages."""
    await update.message.reply_text("🔍 Analyzing the image... This may take a few seconds.")

    try:
        # Get the largest photo
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        image_bytes = bytes(image_bytes)

        analysis = await analyze_image_with_gemini(image_bytes)

        # Telegram message limit is 4096 characters
        if len(analysis) <= 4096:
            await update.message.reply_text(analysis, parse_mode="Markdown")
        else:
            parts = [analysis[i:i+4096] for i in range(0, len(analysis), 4096)]
            for part in parts:
                await update.message.reply_text(part, parse_mode="Markdown")
                await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Error processing photo: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Something went wrong. Please try again with a different image.")

# -------------------- Register Handlers --------------------
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# -------------------- Flask Webhook Endpoints --------------------
@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram will send updates here. Errors are logged but we always return 200."""
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        # Process update asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update))
        loop.close()
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
    # Always return 200 to acknowledge receipt
    return jsonify({"status": "ok"}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/set-webhook', methods=['GET'])
def set_webhook():
    """Helper to configure the webhook URL (call once after deployment)."""
    webhook_url = request.url_root.rstrip('/') + '/webhook'
    # set_webhook is asynchronous, so we need to run it in an event loop
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(bot.set_webhook(url=webhook_url))
        loop.close()
        if success:
            return f"✅ Webhook set to {webhook_url}", 200
        else:
            return "❌ Failed to set webhook", 500
    except Exception as e:
        logger.error(f"Error setting webhook: {e}", exc_info=True)
        return f"❌ Error: {str(e)}", 500

# -------------------- Main --------------------
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
