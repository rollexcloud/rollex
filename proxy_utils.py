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
PROXY_VALIDATION_TEST_URL = 'https://www.youtube.com'
PROXY_VALIDATION_TIMEOUT = 8  # seconds

def validate_proxies(proxy_file='proxies.txt'):
    proxies = load_proxies(proxy_file)
    valid = []
    invalid = []
    for proxy in proxies:
        try:
            resp = requests.get(
                PROXY_VALIDATION_TEST_URL,
                proxies={"http": proxy, "https": proxy},
                timeout=PROXY_VALIDATION_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
            )
            if resp.status_code == 200:
                print(f"[proxy_utils] VALID proxy: {proxy}")
                valid.append(proxy)
            else:
                print(f"[proxy_utils] INVALID proxy (status {resp.status_code}): {proxy}")
                invalid.append(proxy)
        except Exception as e:
            print(f"[proxy_utils] ERROR for proxy {proxy}: {e}")
            invalid.append(proxy)
    return valid

def clean_proxies(proxy_file='proxies.txt'):
    """Removes invalid proxies from proxies.txt after validation."""
    valid = validate_proxies(proxy_file)
    with open(proxy_file, 'w', encoding='utf-8') as f:
        for proxy in valid:
            f.write(proxy + '\n')
    print(f"[proxy_utils] Cleaned {proxy_file}. {len(valid)} valid proxies remain.")

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
