"""Check webhook safely; --set configures it using secrets from the environment."""
import argparse
import os
import re
import sys
from urllib.parse import urlsplit
import httpx

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True, help='Expected HTTPS URL ending in /telegram')
    parser.add_argument('--set', action='store_true', help='Register the webhook (no pending updates discarded)')
    args = parser.parse_args()
    u = urlsplit(args.url)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path != '/telegram':
        raise ValueError('Expected https://your-service/telegram')
    token = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    secret = os.environ.get('TELEGRAM_WEBHOOK_SECRET','').strip()
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', secret):
        raise ValueError('Configure TELEGRAM_BOT_TOKEN and a valid TELEGRAM_WEBHOOK_SECRET')
    def call(method, payload=None):
        response = httpx.post(f'https://api.telegram.org/bot{token}/{method}', json=payload or {}, timeout=25)
        if response.status_code != 200:
            raise RuntimeError(f'Telegram returned HTTP {response.status_code}')
        result = response.json()
        if result.get('ok') is not True:
            raise RuntimeError('Telegram did not confirm the operation')
        return result['result']
    if getattr(args, 'set'):
        call('setWebhook', {'url':args.url, 'secret_token':secret, 'allowed_updates':['message'], 'drop_pending_updates':False})
        print('Webhook registered; pending updates preserved.')
    info = call('getWebhookInfo')
    matches = info.get('url') == args.url
    print('Expected URL matches:', matches)
    print('Pending updates:', info.get('pending_update_count',0))
    print('Last error recorded:', bool(info.get('last_error_message')))
    print('Telegram does not return the configured secret. Verify /diagnostico and /hoy in the owner private chat.')
    return 0 if matches else 1

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as exc:
        # Never print request URLs, tokens, provider response bodies or full exceptions.
        print('Check failed:', type(exc).__name__, file=sys.stderr)
        sys.exit(1)
