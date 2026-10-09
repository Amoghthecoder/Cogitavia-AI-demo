import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus

# ---------------- settings ----------------
# Find this at chrome://version (while in your account) -> "Profile Path" -> last folder name.
# Usually "Default" or "Profile 1".
CHROME_PROFILE = "Default"

# Epic Games launch link for Fortnite.
FORTNITE_URI = (
    "com.epicgames.launcher://apps/"
    "fn%3A4fe75bbc5a674f4f9b356b5c90567da5%3AFortnite?action=launch&silent=true"
)

# ---------------- helpers ----------------
def find_chrome():
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def find_start_menu_shortcut(name):
    roots = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
    ]
    name = name.lower()
    for root in roots:
        if not root.exists():
            continue
        for lnk in root.rglob("*.lnk"):
            if name in lnk.stem.lower():
                return str(lnk)
    return None


# ---------------- actions ----------------
def open_chrome(url=None):
    exe = find_chrome()
    if not exe:
        return "Couldn't find Chrome."
    args = [exe, f"--profile-directory={CHROME_PROFILE}"]
    if url:
        args.append(url)
    subprocess.Popen(args)
    return "Opening Chrome."


def google_search(query=None):
    if query:
        open_chrome(f"https://www.google.com/search?q={quote_plus(query)}")
        return f"Searching Google for {query}."
    open_chrome("https://www.google.com")
    return "Opening Google."


def open_roblox():
    lnk = find_start_menu_shortcut("roblox player")
    if not lnk:
        return "Couldn't find Roblox Player."
    os.startfile(lnk)
    return "Opening Roblox."


def open_spotify():
    os.startfile("spotify:")
    return "Opening Spotify."


def open_fortnite():
    os.startfile(FORTNITE_URI)
    return "Launching Fortnite."


# ---------------- router ----------------
# Checked in order. "google chrome" must come before plain "google".
APPS = [
    (["google chrome", "chrome", "browser"], open_chrome),
    (["roblox", "roblocks", "road blocks"], open_roblox),
    (["spotify"], open_spotify),
    (["fortnite", "fortnight", "fort night"], open_fortnite),
    (["google search", "google"], google_search),
]

SEARCH_PATTERN = re.compile(
    r"^(?:please |hey jarvis |jarvis )?(?:search(?: for| up)?|google|look up) (.+?)(?: on google| in chrome)?$"
)


def normalize(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_phrase(text, phrase):
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def handle(text):
    t = normalize(text)
    if not t:
        return "Sorry, I didn't catch that."

    # 1. Searches: "search for X", "look up X", "google X"
    m = SEARCH_PATTERN.match(t)
    if m and m.group(1) not in ("chrome", "search"):
        return google_search(m.group(1))

    # 2. App launches
    for aliases, action in APPS:
        if any(has_phrase(t, a) for a in aliases):
            try:
                return action()
            except Exception as e:
                return f"Error: {e}"

    return "Sorry, I don't know how to do that yet."
