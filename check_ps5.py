import os, re, json, sys, requests
from playwright.sync_api import sync_playwright

PRODUCTS = [
    {"name": "PS5 Slim Disc (Certified Refurbished)",
     "url": "https://www.playstation.com/nl-nl/ps5/certified-refurbished-ps5-slim/product/PSD001-PSDE00233_59-PS5GRADEDCLIZSLE/"},
    {"name": "PS5 Disc (Certified Refurbished)",
     "url": "https://www.playstation.com/nl-nl/ps5/certified-refurbished/product/PSD001-PSDE01840_63-PS5GRADEDCEC7XZE/"},
]
TOPIC = os.environ["NTFY_TOPIC"].strip().replace("https://", "").replace("ntfy.sh/", "").strip("/")
STATE_FILE = "state.json"
ADD_RE = re.compile(r"toevoegen aan (winkel)?(wagen|mandje)|in (de )?winkelwagen|add to (cart|basket)|nu kopen|buy now|bestel", re.I)


def notify(title, msg, url=None):
    headers = {"Title": title, "Priority": "urgent", "Tags": "video_game"}
    if url:
        headers["Click"] = url
    r = requests.post(f"https://ntfy.sh/{TOPIC}", data=msg.encode("utf-8"), headers=headers, timeout=20)
    r.raise_for_status()


def check(page, url):
    """Geeft (beschikbaar, set met knoppen) of None als de pagina niet goed laadde."""
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)
    buttons = page.evaluate(
        """() => Array.from(document.querySelectorAll('button')).map(b => ({
            t: (b.innerText || '').trim(),
            d: b.disabled || b.getAttribute('aria-disabled') === 'true'}))"""
    )
    print("  titel:", page.title())
    print("  knoppen:", [(b["t"], b["d"]) for b in buttons if b["t"]])
    if not buttons:
        return None
    available = any(ADD_RE.search(b["t"]) and not b["d"] for b in buttons)
    keys = {f"{b['t']}|{'uit' if b['d'] else 'aan'}" for b in buttons if b["t"]}
    return available, keys


def main():
    if os.environ.get("TEST") == "true":
        notify("Test PS5 tracker", "Als je dit ziet, werken de meldingen!")
        print("Testmelding verstuurd.")
        return

    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    unknown = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="nl-NL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        )
        page = ctx.new_page()
        for prod in PRODUCTS:
            name, url = prod["name"], prod["url"]
            print(name)
            try:
                res = check(page, url)
            except Exception as e:
                print("  fout:", e)
                res = None
            if res is None:
                unknown += 1
                continue
            available, keys = res
            print("  beschikbaar:", available)

            old = state.get(url)
            if isinstance(old, bool):
                old = {"available": old, "seen": None}
            if old is None:
                old = {"available": False, "seen": None}

            just_available = available and not old["available"]
            if just_available:
                notify(f"{name} is beschikbaar!", "Snel kopen bij PlayStation Direct.", url)

            seen = old["seen"]
            if seen is not None:
                new = sorted(keys - set(seen))
                if new and not just_available:
                    notify(f"Let op: {name} is veranderd",
                           "Nieuwe knop: " + ", ".join(new)[:200] + ". Check de pagina!", url)
                seen_all = set(seen) | keys
            else:
                seen_all = keys
            state[url] = {"available": available, "seen": sorted(seen_all)}
        browser.close()

    json.dump(state, open(STATE_FILE, "w"), indent=2)
    if unknown:
        sys.exit(1)


main()
