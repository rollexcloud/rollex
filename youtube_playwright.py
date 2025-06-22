import asyncio
from playwright.async_api import async_playwright

async def get_youtube_streams(url, proxy=None):
    '''
    Launch headless Chromium, visit YouTube video URL, extract stream URLs.
    Returns: dict with 'video_urls', 'audio_urls', 'title', 'page_html'
    '''
    import os
    from pathlib import Path
    user_data_dir = str(Path('pw_userdata').absolute())
    cookies_path = 'cookies.txt'
    async with async_playwright() as p:
        # Use persistent context for session/cookies
        launch_args = dict(user_data_dir=user_data_dir, headless=True)
        if proxy:
            launch_args["proxy"] = {"server": proxy}
        browser = await p.chromium.launch_persistent_context(**launch_args)
        page = await browser.new_page()
        # Load cookies.txt if present
        if os.path.exists(cookies_path):
            import json
            import http.cookiejar
            import browser_cookie3
            # Try to parse cookies.txt (Netscape format)
            cookies = []
            try:
                cj = http.cookiejar.MozillaCookieJar()
                cj.load(cookies_path)
                for c in cj:
                    cookies.append({
                        'name': c.name,
                        'value': c.value,
                        'domain': c.domain,
                        'path': c.path,
                        'expires': c.expires,
                        'httpOnly': c._rest.get('HttpOnly') or False,
                        'secure': c.secure,
                        'sameSite': 'Lax',
                    })
                await page.context.add_cookies(cookies)
            except Exception:
                pass
        await page.goto(url, wait_until='networkidle')
        # Accept consent if present
        try:
            consent = await page.query_selector('form[action*="consent"] button')
            if consent:
                await consent.click()
                await page.wait_for_timeout(2000)
        except Exception:
            pass
        title = await page.title()
        html = await page.content()

        # --- Extract PO Token from googlevideo.com requests ---
        po_token = None
        def handle_request(request):
            nonlocal po_token
            if 'googlevideo.com' in request.url and 'pot=' in request.url:
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(request.url).query)
                pot = qs.get('pot')
                if pot:
                    po_token = pot[0]
        page.on('request', handle_request)
        # Play video for a few seconds to trigger googlevideo.com requests
        try:
            await page.evaluate('''() => {
                const v = document.querySelector('video');
                if (v) { v.play(); }
            }''')
            await page.wait_for_timeout(5000)
        except Exception:
            pass
        # Remove listener
        page.off('request', handle_request)

        # Extract ytInitialPlayerResponse JSON (contains streaming info)
        player_json = None
        for script in await page.query_selector_all('script'):
            js = await script.text_content()
            if js and 'ytInitialPlayerResponse' in js:
                import re, json
                m = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;', js, re.DOTALL)
                if m:
                    try:
                        player_json = json.loads(m.group(1))
                        break
                    except Exception:
                        pass
        result = {
            'title': title,
            'video_urls': [],
            'audio_urls': [],
            'po_token': po_token,
        }
        # --- DEBUG: Save HTML if extraction fails ---
        extraction_failed = False
        if not player_json:
            extraction_failed = True
        else:
            streaming_data = player_json.get('streamingData', {})
            for fmt in streaming_data.get('formats', []) + streaming_data.get('adaptiveFormats', []):
                mime = fmt.get('mimeType', '')
                url = fmt.get('url')
                if not url:
                    continue
                if 'video' in mime and 'audio' in mime:
                    result['video_urls'].append(url)
                elif 'video' in mime:
                    result['video_urls'].append(url)
                elif 'audio' in mime:
                    result['audio_urls'].append(url)
            if not result['video_urls'] and not result['audio_urls']:
                extraction_failed = True
        if extraction_failed:
            try:
                with open('last_failed_youtube_page.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print('[youtube_playwright] Saved failed YouTube page HTML to last_failed_youtube_page.html')
            except Exception as e:
                print(f'[youtube_playwright] Could not save failed HTML: {e}')
        # Export cookies from Playwright session to cookies.txt for yt-dlp
        cookies = await page.context.cookies()
        try:
            with open('cookies.txt', 'w', encoding='utf-8') as f:
                f.write('# Netscape HTTP Cookie File
')
                for c in cookies:
                    domain = c['domain']
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = c['path']
                    secure = 'TRUE' if c.get('secure') else 'FALSE'
                    expiry = int(c.get('expires', 0))
                    name = c['name']
                    value = c['value']
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
        except Exception as e:
            result['cookie_export_error'] = str(e)
        # Get user-agent
        ua = await page.evaluate('navigator.userAgent')
        result['user_agent'] = ua
        await browser.close()
        return result

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--proxy', default=None)
    args = parser.parse_args()
    url = args.url
    proxy = args.proxy
    import asyncio
    result = asyncio.run(get_youtube_streams(url, proxy=proxy))
    import json
    print(json.dumps(result, ensure_ascii=False))
