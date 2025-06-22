import asyncio
from playwright.async_api import async_playwright

async def get_youtube_streams(url):
    '''
    Launch headless Chromium, visit YouTube video URL, extract stream URLs.
    Returns: dict with 'video_urls', 'audio_urls', 'title', 'page_html'
    '''
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
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
        result = {'title': title, 'video_urls': [], 'audio_urls': []}
        if player_json:
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
        await browser.close()
        return result

if __name__ == '__main__':
    import sys
    import json
    url = sys.argv[1]
    data = asyncio.run(get_youtube_streams(url))
    print(json.dumps(data))
