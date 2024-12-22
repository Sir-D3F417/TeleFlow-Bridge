# Code By D3F417 
# https://t.me/d3f417ir
# https://zil.ink/d3f417
# https://github.com/Sir-D3F417

import os
import logging
from datetime import datetime
from telegram.ext import Application, MessageHandler, filters
import discord
from discord.ext import commands
import asyncio
import threading
import ssl
from dotenv import load_dotenv
import dns.resolver
import httpx
from functools import partial
import queue
import io
import sys

# Configure logging
def setup_logging():
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Set up file handler with rotating logs
    current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file = f'logs/bot_{current_time}.log'
    
    # Configure logging format
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Create logger instance
    logger = logging.getLogger('TelegramDiscordBot')
    return logger

# Initialize logger
logger = setup_logging()

# Configure DNS resolver
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['1.1.1.1', '8.8.8.8']

# Set event loop policy for Windows
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load environment variables
load_dotenv()

# Bot configuration
class BotConfig:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    TELEGRAM_CHANNEL_USERNAME = os.getenv('TELEGRAM_CHANNEL_USERNAME')
    
    @classmethod
    def validate_config(cls):
        missing_vars = []
        for var in ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_USERNAME']:
            if not getattr(cls, var):
                missing_vars.append(var)
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Initialize Discord bot with all intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
discord_bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables
discord_ready = False
message_queue = queue.Queue()
stats = {
    'messages_processed': 0,
    'media_processed': 0,
    'errors_encountered': 0
}

class MessageProcessor:
    @staticmethod
    async def download_media(url, timeout=30):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=timeout)
                if response.status_code == 200:
                    return response.content
                else:
                    logger.error(f"Failed to download media: Status {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error downloading media: {e}")
            return None

    @staticmethod
    async def process_message_queue():
        while True:
            try:
                if not message_queue.empty():
                    message_data = message_queue.get()
                    channel = discord_bot.get_channel(BotConfig.DISCORD_CHANNEL_ID)
                    if channel:
                        try:
                            # Create a rich embed
                            embed = discord.Embed(color=0x00ff00, timestamp=datetime.now())
                            
                            # Add author info
                            author_name = message_data.get('author', '')
                            if message_data.get('channel_name'):
                                author_name = f"{author_name} ({message_data['channel_name']})"
                            
                            # Use channel photo or fallback to Telegram logo
                            icon_url = message_data.get('profile_photo_url') or "https://telegram.org/img/t_logo.png"
                            embed.set_author(
                                name=author_name,
                                icon_url=icon_url
                            )
                            
                            # Add text content
                            if message_data.get('text'):
                                embed.description = message_data['text']
                            
                            # Add footer
                            embed.set_footer(
                                text="Via Telegram",
                                icon_url="https://telegram.org/img/t_logo.png"
                            )
                            
                            # Handle media
                            if message_data.get('media_type'):
                                media_content = await MessageProcessor.download_media(message_data['media_url'])
                                if media_content:
                                    file = None
                                    media_type_icons = {
                                        'photo': '📸',
                                        'video': '🎥',
                                        'gif': '🎞️',
                                        'document': '📎'
                                    }
                                    
                                    icon = media_type_icons.get(message_data['media_type'], '')
                                    embed.add_field(
                                        name=f"{icon} Media Type",
                                        value=message_data['media_type'].title(),
                                        inline=True
                                    )
                                    
                                    if message_data['media_type'] == 'photo':
                                        file = discord.File(fp=io.BytesIO(media_content), filename="image.jpg")
                                    elif message_data['media_type'] == 'video':
                                        file = discord.File(fp=io.BytesIO(media_content), filename="video.mp4")
                                    elif message_data['media_type'] == 'gif':
                                        file = discord.File(fp=io.BytesIO(media_content), filename="animation.gif")
                                    elif message_data['media_type'] == 'document':
                                        filename = message_data.get('filename', 'document')
                                        file = discord.File(fp=io.BytesIO(media_content), filename=filename)
                                        embed.add_field(
                                            name="Filename",
                                            value=filename,
                                            inline=True
                                        )
                                    
                                    # Send file with embed
                                    if file:
                                        await channel.send(file=file, embed=embed)
                                        stats['media_processed'] += 1
                            else:
                                # Text-only message
                                await channel.send(embed=embed)
                            
                            stats['messages_processed'] += 1
                            logger.info(f"Successfully processed message: {message_data.get('text', '')[:50]}...")
                            
                        except Exception as e:
                            stats['errors_encountered'] += 1
                            logger.error(f"Error sending message to Discord: {e}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in queue processing: {e}")

@discord_bot.event
async def on_ready():
    global discord_ready
    logger.info(f'{discord_bot.user} has connected to Discord!')
    logger.info(f'Looking for channel ID: {BotConfig.DISCORD_CHANNEL_ID}')
    
    # Set custom status
    await discord_bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Created by D3F417"
        ),
        status=discord.Status.online
    )
    
    channel = discord_bot.get_channel(BotConfig.DISCORD_CHANNEL_ID)
    if channel:
        logger.info(f"Successfully found Discord channel: {channel.name}")
        embed = discord.Embed(
            title="Bot Status Update",
            description="Bot is now online and ready!",
            color=0x00ff00
        )
        embed.add_field(name="Start Time", value=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        embed.set_footer(text="Created by D3F417", icon_url="https://telegram.org/img/t_logo.png")
        await channel.send(embed=embed)
        discord_ready = True
        asyncio.create_task(MessageProcessor.process_message_queue())
    else:
        logger.error(f"Could not find Discord channel with ID: {BotConfig.DISCORD_CHANNEL_ID}")

@discord_bot.command(name='stats')
async def show_stats(ctx):
    """Show bot statistics"""
    if ctx.channel.id == BotConfig.DISCORD_CHANNEL_ID:
        embed = discord.Embed(title="Bot Statistics", color=0x00ff00)
        embed.add_field(name="Messages Processed", value=stats['messages_processed'])
        embed.add_field(name="Media Files Processed", value=stats['media_processed'])
        embed.add_field(name="Errors Encountered", value=stats['errors_encountered'])
        await ctx.send(embed=embed)

async def telegram_message_handler(update, context):
    logger.info(f"Received Telegram update: {update}")
    message = update.channel_post
    
    if message:
        # For channel posts, we'll use the channel's photo if available
        profile_photo = None
        try:
            chat = message.chat
            if chat:
                chat_photos = await context.bot.get_chat(chat.id)
                if chat_photos.photo:
                    photo_file = await chat_photos.photo.get_big_file()
                    profile_photo = photo_file.file_path
        except Exception as e:
            logger.error(f"Error fetching channel photo: {e}")

        message_data = {
            'author': message.author_signature,
            'text': message.text or message.caption or "",
            'media_url': None,
            'media_type': None,
            'filename': None,
            'profile_photo_url': profile_photo,
            'channel_name': message.chat.title if message.chat else None
        }
        
        try:
            # Handle Photos
            if message.photo:
                file = await message.photo[-1].get_file()
                message_data['media_url'] = file.file_path
                message_data['media_type'] = 'photo'
                logger.info("Processing photo message")
            
            # Handle Videos
            elif message.video:
                file = await message.video.get_file()
                message_data['media_url'] = file.file_path
                message_data['media_type'] = 'video'
                logger.info("Processing video message")
            
            # Handle Animations (GIFs)
            elif message.animation:
                file = await message.animation.get_file()
                message_data['media_url'] = file.file_path
                message_data['media_type'] = 'gif'
                logger.info("Processing GIF message")
            
            # Handle Documents
            elif message.document:
                file = await message.document.get_file()
                message_data['media_url'] = file.file_path
                message_data['media_type'] = 'document'
                message_data['filename'] = message.document.file_name
                logger.info(f"Processing document: {message_data['filename']}")
            
            message_queue.put(message_data)
            logger.info(f"Added message to queue: {message_data}")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            message_queue.put({'text': message_data['text']})

def run_discord_bot():
    ssl_context = ssl.create_default_context()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(discord_bot.start(BotConfig.DISCORD_TOKEN))
    except Exception as e:
        logger.error(f"Discord bot error: {e}")
        logger.info("Attempting to reconnect...")
        try:
            loop.run_until_complete(discord_bot.close())
            loop.run_until_complete(discord_bot.start(BotConfig.DISCORD_TOKEN))
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")

def run_telegram_bot():
    try:
        proxy_url = "socks5://127.0.0.1:10808"
        
        telegram_app = Application.builder() \
            .token(BotConfig.TELEGRAM_TOKEN) \
            .proxy_url(proxy_url) \
            .connect_timeout(30.0) \
            .read_timeout(30.0) \
            .write_timeout(30.0) \
            .build()
        
        telegram_app.add_handler(MessageHandler(
            filters.ChatType.CHANNEL & filters.UpdateType.CHANNEL_POST,
            telegram_message_handler
        ))
        
        logger.info("Starting Telegram bot...")
        telegram_app.run_polling(allowed_updates=["channel_post"], drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Telegram bot error: {e}")

if __name__ == '__main__':
    try:
        # Validate configuration
        BotConfig.validate_config()
        
        logger.info("Starting bot services...")
        logger.info(f"Discord Token (first 10 chars): {BotConfig.DISCORD_TOKEN[:10]}...")
        
        # Create and start the Discord bot thread
        discord_thread = threading.Thread(target=run_discord_bot)
        discord_thread.start()
        
        # Run the Telegram bot in the main thread
        run_telegram_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error occurred: {e}") 
