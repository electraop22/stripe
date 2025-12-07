# main.py - FN Checker Telegram Bot
import aiohttp
import asyncio
import re
import random
import string
import os
import json
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

from stripeauth import StripeAuthGate
from stripe1dollar import StripeChargeGate

init()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AdvancedCardChecker:
    def __init__(self):
        mongo_uri = os.environ.get('MONGODB_URI', 'mongodb+srv://ElectraOp:BGMI272@cluster0.1jmwb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client['stripe_checker']
        self.users_col = self.db['users']
        self.keys_col = self.db['keys']
        self.checked_cards_col = self.db['checked_cards']
        self.user_stats_col = self.db['user_stats']
        self.admin_id = 7593550190
        self.admin_username = "FNxElectra"
        self.bot_username = None
        self.active_tasks = {}
        self.user_stats = {}
        self.proxy_pool = []
        self.request_timeout = aiohttp.ClientTimeout(total=70)
        self.user_semaphores = {}
        self.max_concurrent_per_user = 20
        self.bin_cache = {}
        self.user_files = {}
        self.rate_limits = {}
        self.rate_limit_window = 60
        self.rate_limit_max_cards = 1500
        
        self.stripe_auth = StripeAuthGate()
        self.stripe_charge = StripeChargeGate()
        self.load_proxies()

    def create_banner(self):
        return f"""
{Fore.CYAN}
╔══════════════════════════════════════════════════════════════╗
║ FN CHECKER BOT                                               ║
╠══════════════════════════════════════════════════════════════╣
║ Admin ID: {self.admin_id:<15}                                ║
║ Bot Username: @{self.bot_username or 'Initializing...':<20} ║
║ Admin Contact: https://t.me/{self.admin_username:<15}        ║
╚══════════════════════════════════════════════════════════════╝
{Fore.YELLOW}
System Ready
{Fore.RESET}
"""

    async def post_init(self, application: Application):
        self.bot_username = application.bot.username
        self.stripe_auth.load_proxies()
        self.stripe_charge.load_proxies()
        print(self.create_banner())

    def load_proxies(self):
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r') as f:
                self.proxy_pool = [line.strip() for line in f if line.strip()]
                self.stripe_auth.proxy_pool = self.proxy_pool
                self.stripe_charge.proxy_pool = self.proxy_pool

    def get_user_semaphore(self, user_id):
        if user_id not in self.user_semaphores:
            self.user_semaphores[user_id] = asyncio.Semaphore(self.max_concurrent_per_user)
        return self.user_semaphores[user_id]

    def cleanup_user_semaphore(self, user_id):
        if user_id in self.user_semaphores:
            del self.user_semaphores[user_id]

    def save_card_result(self, user_id, username, card, gate_type, result, bin_info, check_time, error_message=None):
        try:
            card_doc = {
                'user_id': str(user_id),
                'username': username,
                'card': card,
                'gate': gate_type,
                'result': 'approved' if result else 'declined',
                'bin_info': bin_info,
                'check_time': check_time,
                'error_message': error_message,
                'checked_at': datetime.now()
            }
            self.checked_cards_col.insert_one(card_doc)
        except Exception as e:
            logger.error(f"Failed to save card result: {e}")

    def get_user_persistent_stats(self, user_id):
        try:
            stats = self.user_stats_col.find_one({'user_id': str(user_id)})
            if stats:
                return {
                    'total_checked': stats.get('total_checked', 0),
                    'total_approved': stats.get('total_approved', 0),
                    'total_declined': stats.get('total_declined', 0),
                    'last_check': stats.get('last_check')
                }
        except Exception as e:
            logger.error(f"Failed to get user stats: {e}")
        return {'total_checked': 0, 'total_approved': 0, 'total_declined': 0, 'last_check': None}

    def update_user_persistent_stats(self, user_id, approved=False):
        try:
            update_doc = {
                '$inc': {
                    'total_checked': 1,
                    'total_approved': 1 if approved else 0,
                    'total_declined': 0 if approved else 1
                },
                '$set': {
                    'user_id': str(user_id),
                    'last_check': datetime.now()
                }
            }
            self.user_stats_col.update_one(
                {'user_id': str(user_id)},
                update_doc,
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to update user stats: {e}")

    def check_rate_limit(self, user_id, card_count=1):
        now = datetime.now()
        if user_id in self.rate_limits:
            window_start, count = self.rate_limits[user_id]
            if (now - window_start).total_seconds() > self.rate_limit_window:
                self.rate_limits[user_id] = (now, card_count)
                return True
            if count + card_count > self.rate_limit_max_cards:
                return False
            self.rate_limits[user_id] = (window_start, count + card_count)
        else:
            self.rate_limits[user_id] = (now, card_count)
        return True

    def get_rate_limit_remaining(self, user_id):
        now = datetime.now()
        if user_id in self.rate_limits:
            window_start, count = self.rate_limits[user_id]
            if (now - window_start).total_seconds() > self.rate_limit_window:
                return self.rate_limit_max_cards
            return max(0, self.rate_limit_max_cards - count)
        return self.rate_limit_max_cards

    def get_user_checked_cards(self, user_id, result_filter=None, limit=100):
        try:
            query = {'user_id': str(user_id)}
            if result_filter:
                query['result'] = result_filter
            cards = self.checked_cards_col.find(query).sort('checked_at', -1).limit(limit)
            return list(cards)
        except Exception as e:
            logger.error(f"Failed to get user cards: {e}")
        return []

    async def is_user_allowed(self, user_id):
        user = self.users_col.find_one({'user_id': str(user_id)})
        if user and user.get('expires_at', datetime.now()) > datetime.now():
            return True
        return user_id == self.admin_id

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("Upload Combo", callback_data='upload'),
             InlineKeyboardButton("Cancel Check", callback_data='cancel')],
            [InlineKeyboardButton("Live Stats", callback_data='stats'),
             InlineKeyboardButton("Help", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "<b>Welcome To FN MASS CHECKER BOT!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>Single Card Check:</b>\n"
            "- /chk - Gate 1 (Stripe Auth)\n"
            "- /chk1 - Gate 2 (Stripe $1 Charge)\n\n"
            "<b>Mass File Check:</b>\n"
            "- /fchk - Gate 1 (Stripe Auth)\n"
            "- /fchk1 - Gate 2 (Stripe $1 Charge)\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send Combo File And Reply With /fchk or /fchk1\n"
            "Use /gates to see all available gates\n\n"
            "Use Buttons Below:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    async def handle_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("Command restricted to admin only!")
            return

        command = update.message.text.split()
        if len(command) < 2:
            await update.message.reply_text("Usage: /allow <user_id> or /deny <user_id>")
            return

        action = command[0][1:]
        target_user = command[1]

        if action == 'allow':
            self.users_col.update_one(
                {'user_id': target_user},
                {'$set': {'expires_at': datetime.now() + relativedelta(days=30)}},
                upsert=True
            )
            await update.message.reply_text(f"User {target_user} approved!")
        elif action == 'deny':
            self.users_col.delete_one({'user_id': target_user})
            await update.message.reply_text(f"User {target_user} removed!")

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
            await query.edit_message_text(f"User {user_id} approved!")
            await self.application.bot.send_message(
                chat_id=int(user_id),
                text="Your access has been approved!\nUse /start to begin checking cards."
            )
            
        elif query.data.startswith('deny_'):
            user_id = query.data.split('_')[1]
            self.users_col.delete_one({'user_id': user_id})
            await query.edit_message_text(f"User {user_id} denied!")
            
        elif query.data == 'upload':
            if await self.is_user_allowed(query.from_user.id):
                await query.message.reply_text("Please upload your combo file (.txt)")
            else:
                await query.message.reply_text("You are not authorized!")
                
        elif query.data == 'stats':
            await self.show_stats(update, context)
        elif query.data == 'help':
            await self.show_help(update, context)
        elif query.data == 'cancel':
            await self.stop_command(update, context)

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("Admin only command!")
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
                    text=f"Admin Broadcast:\n\n{message}"
                )
                success += 1
            except:
                failed += 1
        await update.message.reply_text(f"Broadcast complete:\nSuccess: {success}\nFailed: {failed}")

    async def genkey_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("Admin only command!")
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
        
        await update.message.reply_text(f"New key generated:\n`{key}`\nDuration: {delta.days} days")

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
            await update.message.reply_text("Invalid or expired key!")
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
        await update.message.reply_text(f"Subscription activated until {expires_at.strftime('%Y-%m-%d')}!")

    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "<b>Bot Commands:</b>\n\n"
            "<b>Single Card Check:</b>\n"
            "/chk <card> - Gate 1 (Stripe Auth)\n"
            "/chk1 <card> - Gate 2 (Stripe $1 Charge)\n\n"
            "<b>Mass File Check:</b>\n"
            "/fchk - Gate 1 (Stripe Auth)\n"
            "/fchk1 - Gate 2 (Stripe $1 Charge)\n\n"
            "<b>Gates & Info:</b>\n"
            "/gates - View all available payment gates\n\n"
            "<b>Statistics & Export:</b>\n"
            "/stats - Show current session stats\n"
            "/mystats - Show lifetime statistics\n"
            "/export [all|approved|declined] [txt|csv] - Export cards\n\n"
            "/stop - Stop the current checking process\n"
            "/help - Show this help message\n\n"
            "<b>How to Use:</b>\n"
            "1. Upload a combo file (.txt)\n"
            "2. Reply with /fchk or /fchk1\n"
            "3. View live stats with inline buttons\n"
            "4. Use /stop to cancel anytime\n"
            "5. Export results with /export\n\n"
            "<b>Card Formats Supported:</b>\n"
            "- 4111111111111111|12|2025|123\n"
            "- 4111111111111111|12|25|123\n"
            "- 4111111111111111|12|2025|123|John Doe"
        )
        await self.send_message(update, help_text)

    async def gates_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        gates_text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "AVAILABLE PAYMENT GATES\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Gate 1: Stripe Auth</b>\n"
            "- Commands: /chk, /fchk\n"
            "- Type: Authentication Only\n"
            "- No charge made\n"
            "- Best for: Quick validation\n\n"
            "<b>Gate 2: Stripe $1 Charge</b>\n"
            "- Commands: /chk1, /fchk1\n"
            "- Type: Full Charge\n"
            "- Charges $1.00 USD\n"
            "- Best for: Live card testing\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(gates_text, parse_mode='HTML')

    async def send_message(self, update: Update, text: str):
        if update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode='HTML')
        else:
            await update.message.reply_text(text, parse_mode='HTML')

    async def initialize_user_stats(self, user_id):
        if user_id not in self.user_stats:
            self.user_stats[user_id] = {
                'total': 0,
                'approved': 0,
                'declined': 0,
                'checked': 0,
                'approved_ccs': [],
                'start_time': datetime.now(),
                'last_response': ''
            }

    def extract_card_from_text(self, text):
        patterns = [
            r'(\d{13,19})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})',
            r'(\d{13,19})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})[|\s/-]+(.+)',
            r'(\d{4}\s?\d{4}\s?\d{4}\s?\d{3,4})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 4:
                    card = groups[0].replace(" ", "")
                    month = groups[1]
                    year = groups[2]
                    cvv = groups[3]
                    
                    if len(year) == 2:
                        year = f"20{year}" if int(year) < 50 else f"19{year}"
                    
                    return f"{card}|{month}|{year}|{cvv}"
        
        return None

    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("Authorization required!")
            return

        try:
            file = await update.message.document.get_file()
            filename = f"combos_{user_id}_{datetime.now().timestamp()}.txt"
            await file.download_to_drive(filename)
            
            self.user_files[user_id] = filename
            
            await update.message.reply_text(
                "<b>File Received!</b>\n\n"
                "Now Reply To This Message With:\n"
                "- /fchk - Gate 1 (Stripe Auth)\n"
                "- /fchk1 - Stripe $1 Charge Gate\n\n"
                "Bot Will Start When You Use The Command",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"File error: {str(e)}")
            await update.message.reply_text("File processing failed!")

    def create_mass_check_buttons(self, charged, declined, response, cards_left, total_cards, gate_type="gate1"):
        if gate_type == "charge":
            status_text = f"CHARGED: {charged}"
        else:
            status_text = f"APPROVED: {charged}"
        
        keyboard = [
            [InlineKeyboardButton(status_text, callback_data='approved'),
             InlineKeyboardButton(f"DECLINED: {declined}", callback_data='declined')],
            [InlineKeyboardButton(f"Cards Left: {cards_left}/{total_cards}", callback_data='cards_left')],
            [InlineKeyboardButton("Stop", callback_data='cancel')]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _process_chk(self, update: Update, context: ContextTypes.DEFAULT_TYPE, gate_type="gate1"):
        user_id = update.effective_user.id
        user = update.effective_user
        
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("Authorization required!")
            return

        if not self.check_rate_limit(user_id, 1):
            remaining = self.get_rate_limit_remaining(user_id)
            await update.message.reply_text(
                f"Rate limit exceeded! You can check {remaining} more cards.\n"
                f"Wait {self.rate_limit_window} seconds before trying again."
            )
            return

        text = update.message.text
        combo = self.extract_card_from_text(text)
        
        if not combo:
            await update.message.reply_text(
                "Invalid card format!\n\n"
                "Supported formats:\n"
                "- 4111111111111111|12|2025|123\n"
                "- 4111111111111111|12|25|123"
            )
            return

        processing_msg = await update.message.reply_text("Processing card...")
        
        start_time = datetime.now()
        
        try:
            bin_number = combo.split("|")[0][:6]
            
            if gate_type == "charge":
                bin_info = await self.stripe_charge.fetch_bin_info(bin_number)
                result, status, error_message = await self.stripe_charge.process_card(combo)
            else:
                bin_info = await self.stripe_auth.fetch_bin_info(bin_number)
                result, status, error_message = await self.stripe_auth.process_card(combo)
            
            check_time = (datetime.now() - start_time).total_seconds()
            
            self.save_card_result(user_id, user.username, combo, gate_type, bool(result), bin_info, check_time, error_message)
            self.update_user_persistent_stats(user_id, approved=bool(result))
            
            if result:
                if gate_type == "charge":
                    message = await self.stripe_charge.format_approval_message(combo, bin_info, check_time, user)
                else:
                    message = await self.stripe_auth.format_approval_message(combo, bin_info, check_time, user)
            else:
                if gate_type == "charge":
                    message = await self.stripe_charge.format_declined_message(combo, bin_info, check_time, error_message, user)
                else:
                    message = await self.stripe_auth.format_declined_message(combo, bin_info, check_time, error_message, user)
            
            await processing_msg.edit_text(message, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Card check error: {str(e)}")
            await processing_msg.edit_text(f"Error processing card: {str(e)}")

    async def chk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._process_chk(update, context, gate_type="gate1")

    async def chk1_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._process_chk(update, context, gate_type="charge")

    async def process_combos(self, update, context, combos, user_id, gate_type="gate1"):
        user = update.effective_user
        username = user.username or user.full_name
        
        await self.initialize_user_stats(user_id)
        stats = self.user_stats[user_id]
        stats['total'] = len(combos)
        stats['start_time'] = datetime.now()

        if gate_type == "charge":
            header = "STRIPE $1 CHARGE GATE"
        else:
            header = "STRIPE AUTH GATE"

        status_message = await update.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{header}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Starting mass check for {len(combos)} cards...",
            reply_markup=self.create_mass_check_buttons(0, 0, "", len(combos), len(combos), gate_type)
        )

        semaphore = self.get_user_semaphore(user_id)
        self.active_tasks[user_id] = True

        async def check_single_card(combo):
            if not self.active_tasks.get(user_id, False):
                return None
                
            async with semaphore:
                try:
                    start_time = datetime.now()
                    bin_number = combo.split("|")[0][:6]
                    
                    if gate_type == "charge":
                        bin_info = await self.stripe_charge.fetch_bin_info(bin_number)
                        result, status, error_message = await self.stripe_charge.process_card(combo)
                    else:
                        bin_info = await self.stripe_auth.fetch_bin_info(bin_number)
                        result, status, error_message = await self.stripe_auth.process_card(combo)
                    
                    check_time = (datetime.now() - start_time).total_seconds()
                    
                    self.save_card_result(user_id, username, combo, gate_type, bool(result), bin_info, check_time, error_message)
                    self.update_user_persistent_stats(user_id, approved=bool(result))
                    
                    return {
                        'combo': combo,
                        'result': result,
                        'status': status,
                        'error': error_message,
                        'bin_info': bin_info,
                        'check_time': check_time
                    }
                except Exception as e:
                    logger.error(f"Error checking {combo}: {str(e)}")
                    return {'combo': combo, 'result': False, 'error': str(e)}

        tasks = [check_single_card(combo) for combo in combos]
        
        for i, future in enumerate(asyncio.as_completed(tasks)):
            if not self.active_tasks.get(user_id, False):
                break
                
            result = await future
            if result is None:
                continue
                
            stats['checked'] += 1
            
            if result['result']:
                stats['approved'] += 1
                stats['approved_ccs'].append(result['combo'])
                
                if gate_type == "charge":
                    msg = await self.stripe_charge.format_approval_message(
                        result['combo'], result.get('bin_info'), result.get('check_time', 0), user
                    )
                else:
                    msg = await self.stripe_auth.format_approval_message(
                        result['combo'], result.get('bin_info'), result.get('check_time', 0), user
                    )
                await update.message.reply_text(msg, parse_mode='HTML')
            else:
                stats['declined'] += 1
            
            cards_left = stats['total'] - stats['checked']
            
            try:
                await status_message.edit_reply_markup(
                    reply_markup=self.create_mass_check_buttons(
                        stats['approved'], 
                        stats['declined'], 
                        result.get('error', ''),
                        cards_left,
                        stats['total'],
                        gate_type
                    )
                )
            except Exception as e:
                logger.error(f"Failed to update status: {e}")

        self.cleanup_user_semaphore(user_id)
        self.active_tasks[user_id] = False

        elapsed = (datetime.now() - stats['start_time']).total_seconds()
        rate = stats['checked'] / elapsed if elapsed > 0 else 0
        
        if gate_type == "charge":
            completion_header = "STRIPE $1 CHARGE COMPLETE"
            success_label = "Charged"
        else:
            completion_header = "STRIPE AUTH COMPLETE"
            success_label = "Approved"

        completion_message = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{completion_header}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Total Checked: {stats['checked']}\n"
            f"{success_label}: {stats['approved']}\n"
            f"Declined: {stats['declined']}\n"
            f"Time: {elapsed:.2f}s\n"
            f"Speed: {rate:.2f} cards/sec"
        )
        await update.message.reply_text(completion_message)

    async def fchk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._process_file_check(update, context, gate_type="gate1")

    async def fchk1_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._process_file_check(update, context, gate_type="charge")

    async def _process_file_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE, gate_type="gate1"):
        user_id = update.effective_user.id
        
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("Authorization required!")
            return

        filename = None
        if update.message.reply_to_message and update.message.reply_to_message.document:
            try:
                file = await update.message.reply_to_message.document.get_file()
                filename = f"combos_{user_id}_{datetime.now().timestamp()}.txt"
                await file.download_to_drive(filename)
            except Exception as e:
                logger.error(f"Failed to download replied file: {e}")
        
        if not filename:
            filename = self.user_files.get(user_id)
        
        if not filename or not os.path.exists(filename):
            await update.message.reply_text(
                "No combo file found!\n\n"
                "Please upload a .txt file first, then reply with /fchk or /fchk1"
            )
            return

        try:
            with open(filename, 'r') as f:
                content = f.read()
            
            combos = []
            for line in content.split('\n'):
                line = line.strip()
                if line:
                    extracted = self.extract_card_from_text(line)
                    if extracted:
                        combos.append(extracted)
            
            if not combos:
                await update.message.reply_text("No valid cards found in file!")
                return

            if not self.check_rate_limit(user_id, len(combos)):
                remaining = self.get_rate_limit_remaining(user_id)
                await update.message.reply_text(
                    f"Rate limit exceeded! You can only check {remaining} more cards.\n"
                    f"File contains {len(combos)} cards. Wait {self.rate_limit_window} seconds."
                )
                return

            await self.process_combos(update, context, combos, user_id, gate_type)
            
            try:
                os.remove(filename)
                if user_id in self.user_files:
                    del self.user_files[user_id]
            except:
                pass
                
        except Exception as e:
            logger.error(f"File processing error: {str(e)}")
            await update.message.reply_text(f"Error processing file: {str(e)}")

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id in self.active_tasks:
            self.active_tasks[user_id] = False
            await self.send_message(update, "Stopping current operation...")
        else:
            await self.send_message(update, "No active operation to stop.")

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id in self.user_stats:
            stats = self.user_stats[user_id]
            elapsed = (datetime.now() - stats['start_time']).total_seconds()
            rate = stats['checked'] / elapsed if elapsed > 0 else 0
            
            stats_text = (
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"SESSION STATS\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Total Cards: {stats['total']}\n"
                f"Checked: {stats['checked']}\n"
                f"Approved/Charged: {stats['approved']}\n"
                f"Declined: {stats['declined']}\n"
                f"Speed: {rate:.2f} cards/sec\n"
                f"Last Response: {stats.get('last_response', 'N/A')}"
            )
            await self.send_message(update, stats_text)
        else:
            await self.send_message(update, "No statistics available. Start checking first!")

    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("Authorization required!")
            return

        filter_type = context.args[0].lower() if context.args else 'all'
        format_type = context.args[1].lower() if len(context.args) > 1 else 'txt'
        
        if filter_type not in ['all', 'approved', 'declined']:
            await update.message.reply_text(
                "<b>Invalid export type!</b>\n\n"
                "Usage: /export [all|approved|declined] [txt|csv]\n"
                "Example: /export approved txt",
                parse_mode='HTML'
            )
            return

        result_filter = None if filter_type == 'all' else filter_type
        cards = self.get_user_checked_cards(user_id, result_filter=result_filter, limit=1000)
        
        if not cards:
            await update.message.reply_text("No cards found to export!")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"export_{filter_type}_{timestamp}.{format_type}"
        
        try:
            with open(filename, 'w') as f:
                if format_type == 'csv':
                    f.write("Card,Gate,Result,Check Time,Date\n")
                    for card in cards:
                        f.write(f"{card['card']},{card['gate']},{card['result']},{card['check_time']:.2f}s,{card['checked_at'].strftime('%Y-%m-%d %H:%M')}\n")
                else:
                    for card in cards:
                        f.write(f"{card['card']}\n")
            
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"<b>Export Complete!</b>\n\n"
                           f"Type: {filter_type.title()}\n"
                           f"Format: {format_type.upper()}\n"
                           f"Cards: {len(cards)}",
                    parse_mode='HTML'
                )
            
            os.remove(filename)
        except Exception as e:
            logger.error(f"Export error: {e}")
            await update.message.reply_text(f"Export failed: {str(e)}")

    async def mystats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("Authorization required!")
            return

        stats = self.get_user_persistent_stats(user_id)
        last_check = stats['last_check'].strftime('%Y-%m-%d %H:%M') if stats['last_check'] else 'Never'
        
        success_rate = 0
        if stats['total_checked'] > 0:
            success_rate = (stats['total_approved'] / stats['total_checked']) * 100

        stats_text = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"YOUR LIFETIME STATS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>All-Time Statistics:</b>\n"
            f"Total Checked: {stats['total_checked']}\n"
            f"Approved/Charged: {stats['total_approved']}\n"
            f"Declined: {stats['total_declined']}\n"
            f"Success Rate: {success_rate:.1f}%\n"
            f"Last Check: {last_check}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(stats_text, parse_mode='HTML')

    async def adminstats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("Admin only command!")
            return

        try:
            total_users = self.users_col.count_documents({})
            active_users = self.users_col.count_documents({'expires_at': {'$gt': datetime.now()}})
            total_cards_checked = self.checked_cards_col.count_documents({})
            approved_cards = self.checked_cards_col.count_documents({'result': 'approved'})
            declined_cards = self.checked_cards_col.count_documents({'result': 'declined'})
            
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_checks = self.checked_cards_col.count_documents({'checked_at': {'$gte': today_start}})
            today_approved = self.checked_cards_col.count_documents({'checked_at': {'$gte': today_start}, 'result': 'approved'})
            
            top_users = list(self.user_stats_col.find().sort('total_checked', -1).limit(5))
            
            top_users_text = ""
            for i, u in enumerate(top_users, 1):
                top_users_text += f"  {i}. User {u['user_id']}: {u['total_checked']} checks\n"
            
            if not top_users_text:
                top_users_text = "  No activity yet\n"

            stats_text = (
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"ADMIN DASHBOARD\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<b>Users:</b>\n"
                f"Total: {total_users}\n"
                f"Active Subscriptions: {active_users}\n\n"
                f"<b>All-Time Stats:</b>\n"
                f"Total Cards Checked: {total_cards_checked}\n"
                f"Approved: {approved_cards}\n"
                f"Declined: {declined_cards}\n\n"
                f"<b>Today's Activity:</b>\n"
                f"Checked: {today_checks}\n"
                f"Approved: {today_approved}\n\n"
                f"<b>Top Users:</b>\n{top_users_text}"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            await update.message.reply_text(stats_text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Admin stats error: {e}")
            await update.message.reply_text(f"Error getting stats: {str(e)}")

    async def userinfo_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("Admin only command!")
            return

        if not context.args:
            await update.message.reply_text("Usage: /userinfo <user_id>")
            return

        target_user_id = context.args[0]
        user_data = self.users_col.find_one({'user_id': target_user_id})
        user_stats = self.get_user_persistent_stats(int(target_user_id))
        
        if not user_data:
            await update.message.reply_text(f"User {target_user_id} not found!")
            return

        expires = user_data.get('expires_at', 'N/A')
        if isinstance(expires, datetime):
            expires = expires.strftime('%Y-%m-%d %H:%M')
            
        info_text = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"USER INFO\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"User ID: {target_user_id}\n"
            f"Username: @{user_data.get('username', 'N/A')}\n"
            f"Full Name: {user_data.get('full_name', 'N/A')}\n"
            f"Expires: {expires}\n\n"
            f"<b>Statistics:</b>\n"
            f"Total Checked: {user_stats['total_checked']}\n"
            f"Approved: {user_stats['total_approved']}\n"
            f"Declined: {user_stats['total_declined']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(info_text, parse_mode='HTML')

    def run(self):
        token = os.environ.get('BOT_TOKEN', '8122009466:AAEx1Ct6OC4QkFxX4ea9MXNZzc0U6gxhZ2w')
        
        self.application = Application.builder().token(token).post_init(self.post_init).build()
        
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("chk", self.chk_command))
        self.application.add_handler(CommandHandler("chk1", self.chk1_command))
        self.application.add_handler(CommandHandler("fchk", self.fchk_command))
        self.application.add_handler(CommandHandler("fchk1", self.fchk1_command))
        self.application.add_handler(CommandHandler("gates", self.gates_command))
        self.application.add_handler(CommandHandler("stop", self.stop_command))
        self.application.add_handler(CommandHandler("stats", self.show_stats))
        self.application.add_handler(CommandHandler("help", self.show_help))
        self.application.add_handler(CommandHandler("allow", self.handle_admin_command))
        self.application.add_handler(CommandHandler("deny", self.handle_admin_command))
        self.application.add_handler(CommandHandler("broadcast", self.broadcast_command))
        self.application.add_handler(CommandHandler("genkey", self.genkey_command))
        self.application.add_handler(CommandHandler("redeem", self.redeem_command))
        self.application.add_handler(CommandHandler("export", self.export_command))
        self.application.add_handler(CommandHandler("mystats", self.mystats_command))
        self.application.add_handler(CommandHandler("adminstats", self.adminstats_command))
        self.application.add_handler(CommandHandler("userinfo", self.userinfo_command))
        
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_file))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        print("Bot starting...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    checker = AdvancedCardChecker()
    checker.run()
