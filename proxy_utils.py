import random
import requests
import time

# Usage:
# Call get_valid_proxies() to get a list of working proxies from proxies.txt.
# This will validate each proxy by making a quick HTTP request to http://example.com.
# Results are cached for 5 minutes to avoid repeated checks.

def load_proxies(proxy_file='proxies.txt'):
    proxies = []
    try:
        with open(proxy_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    proxies.append(line)
    except Exception:
        pass
    return proxies

_proxy_validation_cache = {
    'timestamp': 0,
    'valid_proxies': []
}

PROXY_VALIDATION_CACHE_TTL = 300  # seconds
PROXY_VALIDATION_TEST_URL = 'http://example.com'
PROXY_VALIDATION_TIMEOUT = 5  # seconds

def validate_proxies(proxy_file='proxies.txt'):
    proxies = load_proxies(proxy_file)
    valid = []
    for proxy in proxies:
        try:
            resp = requests.get(
                PROXY_VALIDATION_TEST_URL,
                proxies={"http": proxy, "https": proxy},
                timeout=PROXY_VALIDATION_TIMEOUT
            )
            if resp.status_code == 200:
                valid.append(proxy)
        except Exception:
            continue
    return valid

def get_valid_proxies(proxy_file='proxies.txt'):
    now = time.time()
    if now - _proxy_validation_cache['timestamp'] < PROXY_VALIDATION_CACHE_TTL:
        return list(_proxy_validation_cache['valid_proxies'])
    valid = validate_proxies(proxy_file)
    _proxy_validation_cache['timestamp'] = now
    _proxy_validation_cache['valid_proxies'] = valid
    return list(valid)

def get_random_proxy(proxy_file='proxies.txt'):
    valid = get_valid_proxies(proxy_file)
    if valid:
        return random.choice(valid)
    return None
