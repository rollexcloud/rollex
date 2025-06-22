import subprocess
import sys
import json

def get_streams_with_playwright(url, proxy=None):
    '''
    Calls youtube_playwright.py as a subprocess and parses the result.
    '''
    import shlex
    cmd = [sys.executable, 'youtube_playwright.py', url]
    if proxy:
        cmd += ['--proxy', proxy]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            return {'error': result.stderr.strip() or 'Playwright script error'}
        # Try to parse JSON from output
        try:
            data = json.loads(result.stdout.replace("'", '"'))  # crude fix for single quotes
            return data
        except Exception:
            return {'error': 'Could not parse Playwright output', 'raw': result.stdout}
    except subprocess.TimeoutExpired:
        return {'error': 'Playwright script timed out'}
    except Exception as e:
        return {'error': str(e)}

if __name__ == '__main__':
    import sys
    url = sys.argv[1]
    print(json.dumps(get_streams_with_playwright(url), indent=2))
