# main.py (updated with fixed /stop command)
import asyncio
import re
import random
import string
import os
import logging
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

# Import the StripeProcessor from gate.py
from gate import StripeProcessor

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
        self.user_semaphores = {}  # Per-user semaphore dictionary
        self.max_concurrent_per_user = 20  # Max concurrent requests per user
        self.user_files = {}  # Store user's uploaded files
        self.stop_flags = {}  # Add stop flags for each user
        
        # Initialize Stripe Processor
        self.stripe_processor = StripeProcessor()
        self.stripe_processor.load_proxies()

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

        # Reset stop flag for this user
        self.stop_flags[user_id] = False
        
        await self.initialize_user_stats(user_id)
        user_semaphore = self.get_user_semaphore(user_id)
        
        self.active_tasks[user_id] = asyncio.create_task(
            self.process_combos(user_id, filename, update, user_semaphore)
        )
        await update.message.reply_text(
            "✅ 𝐅𝐢𝐥𝐞 𝐑𝐞𝐜𝐨𝐠𝐧𝐢𝐳𝐞𝐝! 𝐒𝐭𝐚𝐫𝐭𝐢𝐧𝐠 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠...\n"
            "⚡ 𝐒𝐩𝐞𝐞𝐝: 𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 𝐖𝐢𝐥𝐥 𝐁𝐞 𝐔𝐩𝐝𝐚𝐭𝐞𝐝 𝐖𝐡𝐞𝐧 𝐁𝐨𝐭 𝐂𝐡𝐞𝐜𝐤𝐞𝐝 50 𝐂𝐚𝐫𝐝𝐬/sec\n"
            "📈 𝐔𝐬𝐞 /stats 𝐅𝐨𝐫 𝐋𝐢𝐯𝐞 𝐔𝐩𝐝𝐚𝐭𝐞𝐬\n"
            "🛑 Use /stop to cancel anytime"
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
                bin_info = await self.stripe_processor.fetch_bin_info(combo[:6])
                check_time = random.uniform(3.0, 10.0)
                
                if status == "3d_secure":
                    await self.send_3d_secure_message(update, combo, bin_info, check_time, update.effective_user)
                else:
                    await self.send_approval(update, combo, bin_info, check_time, update.effective_user)
            else:
                bin_info = await self.stripe_processor.fetch_bin_info(combo[:6])
                check_time = random.uniform(3.0, 10.0)
                await self.send_declined_message(update, combo, bin_info, check_time, error_message, update.effective_user)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Check failed: {str(e)}")

    async def process_combos(self, user_id, filename, update, user_semaphore):
        """Process multiple combos from a file with stop functionality"""
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
                
                # Create tasks list
                tasks = []
                for combo in combos:
                    # Check stop flag before creating task
                    if self.stop_flags.get(user_id, False):
                        break
                    
                    task = asyncio.create_task(
                        self.process_line_with_stop_check(user_id, combo, user_semaphore, update, is_single_check=False)
                    )
                    tasks.append(task)
                
                # Process tasks
                for future in asyncio.as_completed(tasks):
                    # Check stop flag
                    if self.stop_flags.get(user_id, False):
                        # Cancel remaining tasks
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        break
                    
                    try:
                        result, status, error_message = await future
                        self.user_stats[user_id]['checked'] += 1
                        
                        if result:
                            self.user_stats[user_id]['approved'] += 1
                            self.user_stats[user_id]['approved_ccs'].append(result)
                            bin_info = await self.stripe_processor.fetch_bin_info(result[:6])
                            check_time = random.uniform(3.0, 10.0)
                            
                            if status == "3d_secure":
                                await self.send_3d_secure_message(update, result, bin_info, check_time, update.effective_user)
                            else:
                                await self.send_approval(update, result, bin_info, check_time, update.effective_user)
                        else:
                            self.user_stats[user_id]['declined'] += 1
                        
                        if self.user_stats[user_id]['checked'] % 50 == 0:
                            await self.send_progress_update(user_id, update)
                            
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Task error: {str(e)}")
                        continue

                # Only send final report if not stopped
                if not self.stop_flags.get(user_id, False) and self.user_stats[user_id]['checked'] > 0:
                    await self.send_report(user_id, update)
                elif self.stop_flags.get(user_id, False):
                    await update.message.reply_text("⏹️ Process stopped successfully!")
                    
        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            await self.send_message(update, f"❌ Processing failed: {str(e)}")
        finally:
            # Cleanup
            if os.path.exists(filename):
                os.remove(filename)
            if user_id in self.user_files:
                del self.user_files[user_id]
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
            if user_id in self.stop_flags:
                del self.stop_flags[user_id]
            self.cleanup_user_semaphore(user_id)

    async def process_line_with_stop_check(self, user_id, combo, semaphore, update, is_single_check=False):
        """Process a single card with stop flag check"""
        # Check stop flag before processing
        if self.stop_flags.get(user_id, False):
            raise asyncio.CancelledError("Process stopped by user")
        
        return await self.process_line(user_id, combo, semaphore, update, is_single_check)

    async def process_line(self, user_id, combo, semaphore, update, is_single_check=False):
        """Process a single card line using the Stripe processor"""
        # Check stop flag
        if self.stop_flags.get(user_id, False):
            raise asyncio.CancelledError("Process stopped by user")
        
        start_time = datetime.now()
        
        async with semaphore:
            # Check stop flag again before actual processing
            if self.stop_flags.get(user_id, False):
                raise asyncio.CancelledError("Process stopped by user")
                
            result, status, error_message = await self.stripe_processor.process_stripe_payment(combo)
            check_time = (datetime.now() - start_time).total_seconds()
            
            if is_single_check:
                return result, status, error_message
            
            return result, status, error_message

    async def send_approval(self, update, combo, bin_info, check_time, user):
        message = await self.stripe_processor.format_approval_message(combo, bin_info, check_time, user)
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
        message = await self.stripe_processor.format_3d_secure_message(combo, bin_info, check_time, user)
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
        message = await self.stripe_processor.format_declined_message(combo, bin_info, check_time, error_message, user)
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
[✪] 𝐀𝐯𝐠 𝐒𝐩𝐞𝐞𝐝: {stats['checked']/elapsed.seconds if elapsed.seconds else 0:.1f} c/s
[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {(stats['approved']/stats['checked'])*100 if stats['checked'] > 0 else 0:.2f}%
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @FNxELECTRA ⚡😈
━━━━━━━━━━━━━━━━━━━━━━
🛑 Use /stop to cancel"""
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
[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐑𝐄𝐒𝐔𝐋𝐓𝐒 😈⚡
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {stats['approved']}
[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {stats['declined']}
[✪] 𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {stats['checked']}
[✪] 𝐓𝐨𝐭𝐚𝐥 𝐢𝐧 𝐅𝐢𝐥𝐞: {stats['total']}
[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
[✪] 𝐀𝐯𝐠 𝐒𝐩𝐞𝐞𝐝: {stats['checked']/elapsed.seconds if elapsed.seconds else 0:.1f} c/s
[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {(stats['approved']/stats['checked'])*100 if stats['checked'] > 0 else 0:.2f}%
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @FNxELECTRA ⚡😈
━━━━━━━━━━━━━━━━━━━━━━"""
        
        # Generate and send hits file if there are approved cards
        if stats['approved_ccs']:
            try:
                hits_file = await self.generate_hits_file(stats['approved_ccs'], stats['checked'])
                await update.message.reply_document(
                    document=open(hits_file, 'rb'),
                    caption="🎯 FN Checker Results Attached"
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
            await self.send_message(update, "📊 No active checking session. Start one with /fchk")
            return
            
        stats = self.user_stats[user_id]
        elapsed = datetime.now() - stats['start_time']
        message = f"""
━━━━━━━━━━━━━━━━━━━━━━
[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐒𝐓𝐀𝐓𝐔𝐒 😈⚡
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {stats['approved']}
[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {stats['declined']}
[✪] 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {stats['checked']}/{stats['total']}
[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
[✪] 𝐀𝐯𝐠 𝐒𝐩𝐞𝐞𝐝: {stats['checked']/elapsed.seconds if elapsed.seconds else 0:.1f} c/s
[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {(stats['approved']/stats['checked'])*100 if stats['checked'] > 0 else 0:.2f}%
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @FNxELECTRA ⚡😈
━━━━━━━━━━━━━━━━━━━━━━
🛑 Use /stop to cancel"""
        await self.send_message(update, message)

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop the current checking process for the user"""
        user_id = update.effective_user.id
        
        if user_id in self.active_tasks:
            # Set stop flag
            self.stop_flags[user_id] = True
            
            # Cancel the main task
            task = self.active_tasks[user_id]
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # Send confirmation
            await update.message.reply_text("⏹️ Process stopped successfully!")
            
            # Cleanup
            if user_id in self.user_stats:
                # Send partial stats if available
                if self.user_stats[user_id]['checked'] > 0:
                    elapsed = datetime.now() - self.user_stats[user_id]['start_time']
                    partial_report = f"""
⏹️ Process Stopped by User

━━━━━━━━━━━━━━━━━━━━━━
[⌬] 𝐏𝐀𝐑𝐓𝐈𝐀𝐋 𝐑𝐄𝐒𝐔𝐋𝐓𝐒
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {self.user_stats[user_id]['approved']}
[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {self.user_stats[user_id]['declined']}
[✪] 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {self.user_stats[user_id]['checked']}/{self.user_stats[user_id]['total']}
[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
━━━━━━━━━━━━━━━━━━━━━━
"""
                    await update.message.reply_text(partial_report)
                
                # Generate hits file if there are approved cards
                if self.user_stats[user_id]['approved_ccs']:
                    try:
                        hits_file = await self.generate_hits_file(
                            self.user_stats[user_id]['approved_ccs'], 
                            self.user_stats[user_id]['checked']
                        )
                        await update.message.reply_document(
                            document=open(hits_file, 'rb'),
                            caption="🎯 Partial Results (Stopped)"
                        )
                        os.remove(hits_file)
                    except Exception as e:
                        logger.error(f"Failed to send partial hits file: {str(e)}")
                
                del self.user_stats[user_id]
            
            # Cleanup files
            if user_id in self.user_files:
                filename = self.user_files[user_id]
                if os.path.exists(filename):
                    os.remove(filename)
                del self.user_files[user_id]
            
            # Remove from active tasks
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
            
            # Cleanup semaphore
            self.cleanup_user_semaphore(user_id)
            
            # Remove stop flag
            if user_id in self.stop_flags:
                del self.stop_flags[user_id]
                
        else:
            await update.message.reply_text("⚠️ No active checking process to stop!")

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
    application = Application.builder().token("8122009466:AAEx1Ct6OC4QkFxX4ea9MXNZzc0U6gxhZ2w").post_init(checker.post_init).build()
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
