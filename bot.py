import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
from collections import defaultdict
from typing import List, Dict, Tuple
import tempfile
import asyncio
from datetime import datetime
import pytz

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Store conversation history for each user
# Format: {user_id: [(role, content), ...]}
conversation_history: Dict[int, List[Tuple[str, str]]] = defaultdict(list)
MAX_HISTORY = 10

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    conversation_history[user_id].clear()  # Clear history on restart
    await update.message.reply_text("Greetings! I am Wonder, your personal AI assistant. Like JARVIS, but with my own unique charm. I'm here to help with anything you need - from complex problems to casual conversation. You can send me text messages or voice notes! How may I assist you today?")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text("I'm here to help! You can:\n- Send me text messages\n- Send voice messages\n- Use /clear to reset our conversation\n\nI'll do my best to assist you with any questions or tasks!")

def update_conversation_history(user_id: int, role: str, content: str):
    """Update the conversation history for a user."""
    conversation_history[user_id].append((role, content))
    # Keep only the last MAX_HISTORY messages
    if len(conversation_history[user_id]) > MAX_HISTORY:
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY:]

def build_messages(user_id: int, new_message: str) -> List[dict]:
    """Build the messages list for the API call including conversation history."""
    # Get current time in Pacific timezone
    pacific_timezone = pytz.timezone('America/Los_Angeles')
    current_time = datetime.now(pacific_timezone)
    
    # Format the date and time information
    date_str = current_time.strftime("%A, %B %d, %Y")
    time_str = current_time.strftime("%-I:%M %p")  # Using %-I to remove leading zero
    
    # Get the base system prompt
    base_prompt = os.getenv('SYSTEM_PROMPT', 'You are a helpful assistant.')
    
    # Add time awareness to the system prompt
    time_aware_prompt = f"{base_prompt} The current date is {date_str} and the time is {time_str} Pacific Time."
    
    messages = [{"role": "system", "content": time_aware_prompt}]
    
    # Add conversation history
    for role, content in conversation_history[user_id]:
        messages.append({"role": role, "content": content})
    
    # Add the new message
    messages.append({"role": "user", "content": new_message})
    return messages

async def process_message(user_id: int, message_text: str) -> str:
    """Process a message and get AI response."""
    # Update history with user's message
    update_conversation_history(user_id, "user", message_text)
    
    # Build messages with conversation history
    messages = build_messages(user_id, message_text)
    
    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    
    # Extract the response text
    ai_response = response.choices[0].message.content
    
    # Update history with AI's response
    update_conversation_history(user_id, "assistant", ai_response)
    
    return ai_response

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages."""
    try:
        # Send initial acknowledgment
        processing_msg = await update.message.reply_text("🎧 Processing your voice message...")
        
        # Get the voice message file
        voice = update.message.voice
        voice_file = await context.bot.get_file(voice.file_id)
        
        # Create a temporary file to store the voice message
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
            # Download the voice message
            await voice_file.download_to_drive(temp_file.name)
            
            # Transcribe using Whisper
            with open(temp_file.name, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
        
        # Delete the temporary file
        os.unlink(temp_file.name)
        
        # Get the transcribed text
        transcribed_text = transcript.text
        
        # Send transcription to user
        await processing_msg.edit_text(f"🎯 I heard: \"{transcribed_text}\"\n\n💭 Thinking...")
        
        # Process the transcribed text like a regular message
        ai_response = await process_message(update.effective_user.id, transcribed_text)
        
        # Send AI response
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logging.error(f"Error processing voice message: {str(e)}")
        await update.message.reply_text("I apologize, but I encountered an error processing your voice message. Please try again or send your message as text.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages."""
    try:
        user_id = update.effective_user.id
        user_message = update.message.text
        
        # Process the message and get response
        ai_response = await process_message(user_id, user_message)
        
        # Send the response back to the user
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        await update.message.reply_text("I apologize, but I encountered an error. Please try again later.")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear the conversation history for a user."""
    user_id = update.effective_user.id
    conversation_history[user_id].clear()
    await update.message.reply_text("Conversation history has been cleared. Let's start fresh!")

def main():
    """Start the bot."""
    # Create the Application and pass it your bot's token
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 