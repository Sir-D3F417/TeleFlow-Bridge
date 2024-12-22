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
import subprocess
import random
from itertools import cycle

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
discord_bot = commands.Bot(command_prefix='@', intents=intents)

# Global variables
discord_ready = False
message_queue = queue.Queue()
stats = {
    'messages_processed': 0,
    'media_processed': 0,
    'errors_encountered': 0
}
bot_start_time = datetime.now()

class ColorScheme:
    """Color schemes for different message types"""
    PHOTO = 0x3498db      # Blue
    VIDEO = 0xe74c3c      # Red
    ANIMATION = 0x2ecc71   # Green
    STICKER = 0x9b59b6    # Purple
    VOICE = 0xf1c40f      # Yellow
    DOCUMENT = 0xe67e22   # Orange
    TEXT = 0x1abc9c       # Turquoise
    STATUS = 0x00ff00     # Bright Green
    ERROR = 0xff0000      # Bright Red

    @classmethod
    def get_color(cls, media_type):
        color_map = {
            'photo': cls.PHOTO,
            'video': cls.VIDEO,
            'animation': cls.ANIMATION,
            'sticker': cls.STICKER,
            'sticker_animated': cls.STICKER,
            'sticker_video': cls.STICKER,
            'voice': cls.VOICE,
            'document': cls.DOCUMENT
        }
        return color_map.get(media_type, cls.TEXT)

class BotStatus:
    """Dynamic status messages for the bot"""
    
    # Status messages with different activities
    WATCHING_MESSAGES = [
        "Telegram Messages",
        "for new media",
        "D3F417's Channel",
        f"{stats['messages_processed']} messages"
    ]
    
    PLAYING_MESSAGES = [
        "Use @bothelp",
        "Forwarding messages",
        "Converting media",
        f"with {stats['media_processed']} files"
    ]
    
    LISTENING_MESSAGES = [
        "Telegram updates",
        "voice messages",
        "your commands",
        "@botstatus for info"
    ]
    
    @classmethod
    def get_status_message(cls):
        """Get a random status configuration"""
        status_types = [
            (discord.ActivityType.watching, cls.WATCHING_MESSAGES),
            (discord.ActivityType.playing, cls.PLAYING_MESSAGES),
            (discord.ActivityType.listening, cls.LISTENING_MESSAGES)
        ]
        activity_type, messages = random.choice(status_types)
        return activity_type, random.choice(messages)

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
    async def convert_mp4_to_gif(mp4_content):
        try:
            # Save MP4 content to a temporary file
            with open('temp.mp4', 'wb') as f:
                f.write(mp4_content)
            
            # Convert MP4 to GIF using ffmpeg
            subprocess.run([
                'ffmpeg',
                '-i', 'temp.mp4',
                '-vf', 'fps=15,scale=320:-1:flags=lanczos',
                '-c:v', 'gif',
                'temp.gif'
            ], check=True)
            
            # Read the GIF content
            with open('temp.gif', 'rb') as f:
                gif_content = f.read()
            
            # Clean up temporary files
            os.remove('temp.mp4')
            os.remove('temp.gif')
            
            return gif_content
        except Exception as e:
            logger.error(f"Error converting MP4 to GIF: {e}")
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
                            # Determine embed color based on content type
                            color = ColorScheme.TEXT
                            if message_data.get('media_types'):
                                color = ColorScheme.get_color(message_data['media_types'][0])

                            # Create a rich embed with the determined color
                            embed = discord.Embed(
                                color=color,
                                timestamp=datetime.now()
                            )
                            
                            # Add author info with enhanced formatting
                            author_name = message_data.get('author', '')
                            if message_data.get('channel_name'):
                                author_name = f"📢 {author_name} ({message_data['channel_name']})"
                            else:
                                author_name = f"👤 {author_name}"
                            
                            embed.set_author(
                                name=author_name,
                                icon_url="https://telegram.org/img/t_logo.png"
                            )
                            
                            # Add text content with enhanced formatting
                            if message_data.get('text'):
                                text = message_data['text']
                                # Add decorative elements for different types
                                if message_data.get('media_types'):
                                    media_type = message_data['media_types'][0]
                                    if media_type == 'document':
                                        text = f"```📎 File Information\n{text}```"
                                    elif media_type == 'voice':
                                        text = f"```🎤 Voice Message\n{text}```"
                                embed.description = text
                            
                            # Handle media with enhanced formatting
                            files = []
                            if message_data.get('media_urls'):
                                for i, (media_url, media_type, filename) in enumerate(zip(
                                    message_data['media_urls'],
                                    message_data['media_types'],
                                    message_data['filenames']
                                )):
                                    media_content = await MessageProcessor.download_media(media_url)
                                    if media_content:
                                        media_type_icons = {
                                            'photo': '📸',
                                            'video': '🎥',
                                            'animation': '🎞️',
                                            'sticker': '🎨',
                                            'sticker_animated': '✨',
                                            'sticker_video': '🎬',
                                            'voice': '🎤',
                                            'document': '📎'
                                        }
                                        
                                        icon = media_type_icons.get(media_type, '')
                                        
                                        file = discord.File(
                                            fp=io.BytesIO(media_content),
                                            filename=filename
                                        )
                                        files.append(file)
                                        
                                        if i == 0:  # Only add media type field for first media
                                            embed.add_field(
                                                name=f"{icon} Content Type",
                                                value=f"**{media_type.replace('_', ' ').title()}**",
                                                inline=True
                                            )
                                            
                                            # Add file info for documents
                                            if media_type == 'document':
                                                embed.add_field(
                                                    name="📁 Filename",
                                                    value=f"```{filename}```",
                                                    inline=False
                                                )
                            
                            # Add footer with timestamp
                            embed.set_footer(
                                text="Created by D3F417 | Forwarded from Telegram",
                                icon_url="https://telegram.org/img/t_logo.png"
                            )
                            
                            # Send message with files and embed
                            if files or message_data.get('text'):
                                await channel.send(files=files, embed=embed)
                                if files:
                                    stats['media_processed'] += len(files)
                            
                            stats['messages_processed'] += 1
                            
                        except Exception as e:
                            stats['errors_encountered'] += 1
                            logger.error(f"Error sending message to Discord: {e}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in queue processing: {e}")

async def update_bot_status():
    """Update bot status periodically"""
    while True:
        try:
            activity_type, message = BotStatus.get_status_message()
            # Update stats in status messages
            BotStatus.WATCHING_MESSAGES[3] = f"{stats['messages_processed']} messages"
            BotStatus.PLAYING_MESSAGES[3] = f"with {stats['media_processed']} files"
            
            activity = discord.Activity(
                type=activity_type,
                name=message
            )
            await discord_bot.change_presence(
                activity=activity,
                status=discord.Status.online
            )
            # Update status every 10 seconds instead of 30
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error updating bot status: {e}")
            await asyncio.sleep(10)  # Also update error retry time to 10 seconds

@discord_bot.event
async def on_ready():
    global discord_ready
    logger.info(f'{discord_bot.user} has connected to Discord!')
    logger.info(f'Looking for channel ID: {BotConfig.DISCORD_CHANNEL_ID}')
    
    channel = discord_bot.get_channel(BotConfig.DISCORD_CHANNEL_ID)
    if channel:
        logger.info(f"Successfully found Discord channel: {channel.name}")
        embed = discord.Embed(
            title="Bot Status Update",
            description="Bot is now online and ready!",
            color=ColorScheme.STATUS
        )
        embed.add_field(
            name="🚀 Startup Time", 
            value=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        embed.add_field(
            name="📌 Commands",
            value="Use `@bothelp` to see available commands",
            inline=False
        )
        embed.set_footer(text="Created by D3F417", icon_url="https://telegram.org/img/t_logo.png")
        await channel.send(embed=embed)
        discord_ready = True
        
        # Start status update task
        asyncio.create_task(update_bot_status())
        # Start message queue processing
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

@discord_bot.command(name='botstatus')
async def show_status(ctx):
    """Show detailed bot status and uptime"""
    if ctx.channel.id == BotConfig.DISCORD_CHANNEL_ID:
        uptime = datetime.now() - bot_start_time
        embed = discord.Embed(
            title="🤖 Bot Status Dashboard",
            color=ColorScheme.STATUS,
            timestamp=datetime.now()
        )
        
        # Add status fields with formatting
        embed.add_field(
            name="⏱️ Uptime",
            value=f"```{str(uptime).split('.')[0]}```",
            inline=False
        )
        embed.add_field(
            name="📊 Statistics",
            value=f"```\n"
                  f"Messages Processed: {stats['messages_processed']}\n"
                  f"Media Files: {stats['media_processed']}\n"
                  f"Errors: {stats['errors_encountered']}\n"
                  f"```",
            inline=False
        )
        embed.add_field(
            name="🏓 Latency",
            value=f"```{round(discord_bot.latency * 1000)}ms```",
            inline=False
        )
        
        # Add fancy footer
        embed.set_footer(
            text="Bot Status | Created by D3F417",
            icon_url="https://telegram.org/img/t_logo.png"
        )
        
        await ctx.send(embed=embed)

@discord_bot.command(name='bothelp')
async def show_help(ctx):
    """Show bot commands and information"""
    if ctx.channel.id == BotConfig.DISCORD_CHANNEL_ID:
        embed = discord.Embed(title="📚 Bot Commands", color=0x00ff00)
        embed.add_field(name="@botstatus", value="Show bot statistics and status", inline=False)
        embed.add_field(name="@bothelp", value="Show this help message", inline=False)
        embed.add_field(name="@ping", value="Check bot's response time", inline=False)
        await ctx.send(embed=embed)

@discord_bot.command(name='ping')
async def ping(ctx):
    """Check bot's response time"""
    if ctx.channel.id == BotConfig.DISCORD_CHANNEL_ID:
        embed = discord.Embed(title="🏓 Pong!", color=0x00ff00)
        embed.add_field(name="Latency", value=f"{round(discord_bot.latency * 1000)}ms")
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

        # Create base message data
        message_data = {
            'author': message.author_signature,
            'text': message.text or message.caption or "",
            'media_urls': [],
            'media_types': [],
            'filenames': [],
            'profile_photo_url': profile_photo,
            'channel_name': message.chat.title if message.chat else None
        }
        
        try:
            # Handle media group messages (multiple photos/videos)
            if message.media_group_id:
                # For media groups, handle the current media item
                if message.photo:
                    file = await message.photo[-1].get_file()
                    message_data['media_urls'].append(file.file_path)
                    message_data['media_types'].append('photo')
                    message_data['filenames'].append('image.jpg')
                elif message.video:
                    file = await message.video.get_file()
                    message_data['media_urls'].append(file.file_path)
                    message_data['media_types'].append('video')
                    message_data['filenames'].append('video.mp4')
            
            # Handle single photo
            elif message.photo:
                file = await message.photo[-1].get_file()
                message_data['media_urls'].append(file.file_path)
                message_data['media_types'].append('photo')
                message_data['filenames'].append('image.jpg')
            
            # Handle video
            elif message.video:
                file = await message.video.get_file()
                message_data['media_urls'].append(file.file_path)
                message_data['media_types'].append('video')
                message_data['filenames'].append('video.mp4')
            
            # Handle animations (GIFs/MP4s from Telegram)
            elif message.animation:
                file = await message.animation.get_file()
                message_data['media_urls'].append(file.file_path)
                message_data['media_types'].append('animation')
                message_data['filenames'].append('animation.mp4')
                if message.caption:
                    message_data['text'] = message.caption
            
            # Handle stickers
            elif message.sticker:
                file = await message.sticker.get_file()
                if message.sticker.is_animated:
                    message_data['media_urls'].append(file.file_path)
                    message_data['media_types'].append('sticker_animated')
                    message_data['filenames'].append('sticker.tgs')
                elif message.sticker.is_video:
                    message_data['media_urls'].append(file.file_path)
                    message_data['media_types'].append('sticker_video')
                    message_data['filenames'].append('sticker.webm')
                else:
                    message_data['media_urls'].append(file.file_path)
                    message_data['media_types'].append('sticker')
                    message_data['filenames'].append('sticker.webp')
                
                if message.sticker.emoji:
                    message_data['text'] = f"Sticker: {message.sticker.emoji}"
            
            # Handle voice messages
            elif message.voice:
                file = await message.voice.get_file()
                message_data['media_urls'].append(file.file_path)
                message_data['media_types'].append('voice')
                message_data['filenames'].append('voice.ogg')
                if message.voice.duration:
                    duration = message.voice.duration
                    message_data['text'] = f"Voice message ({duration}s)"
            
            # Handle documents (files)
            elif message.document:
                file = await message.document.get_file()
                filename = message.document.file_name
                if not filename:
                    # If no filename, create one based on the file type
                    mime_type = message.document.mime_type
                    ext = mime_type.split('/')[-1] if mime_type else 'file'
                    filename = f'document.{ext}'
                
                message_data['media_urls'].append(file.file_path)
                message_data['media_types'].append('document')
                message_data['filenames'].append(filename)
                
                # Add file info to text
                file_size = message.document.file_size
                size_str = f"{file_size / 1024 / 1024:.2f}MB" if file_size > 1024 * 1024 else f"{file_size / 1024:.2f}KB"
                message_data['text'] = f"📎 **File:** {filename}\n📦 **Size:** {size_str}\n\n{message_data['text']}"
            
            # Add message to queue
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
        telegram_app = Application.builder() \
            .token(BotConfig.TELEGRAM_TOKEN) \
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
