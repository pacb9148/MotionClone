"""Check the built static showcase as a static host serves it: no link may point
at the server-only /editor route, which scripts/build_showcase.py never ships."""
from pathlib import Path
import functools, http.server, subprocess, sys, threading, time
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'test-results' / 'showcase'
OUT.mkdir(parents=True, exist_ok=True)
PORT = 4320
HOST = 'showcase.example.test'   # stand-in for a static host: not 127.0.0.1/localhost

subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_showcase.py')], check=True)

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / 'site'))
server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
time.sleep(0.5)

editor_hits = []
errors = []
try:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome')
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: editor_hits.append(r.url) if '/editor' in r.url else None)
        # Serve the real files under a non-local hostname, exactly like a static host.
        page.route(f'http://{HOST}/**', lambda route: route.fulfill(
            response=page.request.fetch(route.request.url.replace(f'http://{HOST}', f'http://127.0.0.1:{PORT}'))))
        page.goto(f'http://{HOST}/', wait_until='domcontentloaded')
        expect(page.locator('.illustrative-demo')).to_be_visible(timeout=8000)
        expect(page.locator('.sample-note')).to_contain_text('illustration')
        hrefs = page.locator('.site-header nav a').evaluate_all('(as) => as.map(a => a.getAttribute("href"))')
        assert '/editor' not in hrefs, f'nav still points at /editor: {hrefs}'
        assert not editor_hits, f'page requested the server-only editor: {editor_hits}'
        page.locator('#editor-link').click()
        page.wait_for_timeout(300)
        assert page.url.endswith('#get-started'), page.url
        page.screenshot(path=str(OUT / 'static.png'), full_page=True)
        assert not errors, errors
        browser.close()
finally:
    server.shutdown()
print('PASS: static build links nowhere near /editor and keeps the illustration fallback')
