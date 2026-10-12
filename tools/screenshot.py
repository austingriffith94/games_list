"""Rebuild both reports and screenshot every dashboard tab (light/dark/phone) and PDF page, so a UI review
works from pixels instead of guessing. Optionally also screenshots the entry app on a throwaway copy of the
database. Needs PyMuPDF and Playwright (see requirements-dev.txt; `playwright install chromium` once), and
must run in the project env (`game1` on Windows, not bare python/python3 - see PROJECT_CONTEXT.md):

    python tools/screenshot.py [--app] [--tab TAB ...] [--no-rebuild]

Writes PNGs to screenshots/ (git-ignored):
    screenshots/pdf/p01.png ...                         one per PDF page
    screenshots/dashboard/<tab>_<theme>_<width>.png      theme in {light,dark}, width in {1280,390}
    screenshots/app/<tab>_<theme>_<width>.png            only with --app

--tab restricts the dashboard/app pass to the given tab key(s) (e.g. --tab overview --tab stats), for a
quick look at one area instead of the whole set. --no-rebuild skips the two `python build_*.py` calls and
screenshots whatever games_list_dashboard.html / games_list_report.pdf already exist.
"""
import argparse, os, shutil, socket, subprocess, sys, tempfile, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'screenshots')
DASH_HTML = os.path.join(BASE, 'games_list_dashboard.html')
PDF = os.path.join(BASE, 'games_list_report.pdf')

# dashboard tabs (dashboard.template.html TABS) and app tabs (static/app.html NAMES), in nav order
DASH_TABS = ['overview', 'scores', 'years', 'time', 'hours', 'stats', 'mosaic', 'games']
APP_TABS = ['log', 'games', 'gallery', 'stats', 'top', 'halo', 'checks', 'history', 'reports']


def rebuild():
    for script in ('build_html.py', 'build_pdf.py'):
        print('rebuilding:', script)
        subprocess.run([sys.executable, script], cwd=BASE, check=True)


def shoot_pdf():
    import fitz  # PyMuPDF
    d = os.path.join(OUT, 'pdf')
    os.makedirs(d, exist_ok=True)
    doc = fitz.open(PDF)
    for i, page in enumerate(doc):
        page.get_pixmap(dpi=100).save(os.path.join(d, f'p{i + 1:02d}.png'))
    print(f'PDF: {len(doc)} pages -> {d}')


def shoot_dashboard(page, tabs):
    d = os.path.join(OUT, 'dashboard')
    os.makedirs(d, exist_ok=True)
    url = 'file:///' + DASH_HTML.replace('\\', '/')
    for width in (1280, 390):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(url)
        page.wait_for_timeout(300)
        for theme in ('light', 'dark'):
            page.evaluate(f"document.documentElement.dataset.theme='{theme}'")
            for tab in tabs:
                page.evaluate(f"show('{tab}')")
                page.wait_for_timeout(250)
                page.screenshot(path=os.path.join(d, f'{tab}_{theme}_{width}.png'), full_page=True)
    print(f'dashboard: {len(tabs)} tabs x 2 themes x 2 widths -> {d}')


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def shoot_app(page, tabs):
    d = os.path.join(OUT, 'app')
    os.makedirs(d, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='gamelist_shot_')
    db_copy = os.path.join(tmp, 'gamelist.db')
    shutil.copy(os.path.join(BASE, 'gamelist.db'), db_copy)
    backups = os.path.join(tmp, 'backups')
    port = free_port()
    env = dict(os.environ, GAMELIST_BACKUPS=backups, GAMELIST_OUT=tmp)
    proc = subprocess.Popen(
        [sys.executable, 'app.py', '--db', db_copy, '--port', str(port), '--no-browser'],
        cwd=BASE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f'http://127.0.0.1:{port}/'
        for _ in range(50):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError(f'app.py did not come up on port {port}')
        for width in (1280, 390):
            page.set_viewport_size({'width': width, 'height': 900})
            for theme in ('light', 'dark'):
                for tab in tabs:
                    page.goto(f'{url}#{tab}')
                    page.evaluate(f"document.documentElement.dataset.theme='{theme}'")
                    page.wait_for_timeout(400)
                    page.screenshot(path=os.path.join(d, f'{tab}_{theme}_{width}.png'), full_page=True)
        print(f'app: {len(tabs)} tabs x 2 themes x 2 widths -> {d}')
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app', action='store_true', help='also screenshot the entry app on a throwaway DB copy')
    ap.add_argument('--tab', action='append', dest='tabs', help='restrict to this tab (repeatable); default is every tab')
    ap.add_argument('--no-rebuild', action='store_true', help='skip the build_html.py/build_pdf.py rebuild')
    a = ap.parse_args()

    if not a.no_rebuild:
        rebuild()
    else:
        for p in (DASH_HTML, PDF):
            if not os.path.exists(p):
                sys.exit(f'--no-rebuild given but {p} does not exist; run once without it first')

    # --tab is one flat list of keys; each pass only takes the ones that are actually its own tabs
    # (the dashboard and the app don't share tab names, e.g. "stats" means different things in each)
    dash_tabs = [t for t in DASH_TABS if t in a.tabs] if a.tabs else DASH_TABS
    app_tabs = [t for t in APP_TABS if t in a.tabs] if a.tabs else APP_TABS

    shoot_pdf()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.on('pageerror', lambda e: print('  JS error:', e))
        if dash_tabs:
            shoot_dashboard(page, dash_tabs)
        if a.app:
            if app_tabs:
                shoot_app(page, app_tabs)
            else:
                print('app: no requested --tab matches an app tab, skipping')
        browser.close()
    print('done:', OUT)


if __name__ == '__main__':
    main()
