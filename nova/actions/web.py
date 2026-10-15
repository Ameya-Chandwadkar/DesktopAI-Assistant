"""URL normalisation and validation. Only plain http(s) web addresses are ever opened."""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urlsplit

YOUTUBE_HOME = "https://www.youtube.com"

# Spoken names that map straight to a site. Users add their own in Settings.
BUILTIN_SITES = {
    "youtube": YOUTUBE_HOME,
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "wikipedia": "https://www.wikipedia.org",
    "maps": "https://maps.google.com",
    "google drive": "https://drive.google.com",
}

_HOST_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$", re.I)
_CONTROL_RE = re.compile(r"[\x00-\x20\x7f]")
MAX_URL_LEN = 2048


class UrlError(ValueError):
    pass


def spoken_to_url_text(text: str) -> str:
    """'google dot com slash maps' -> 'google.com/maps' (speech engines spell punctuation out)."""
    t = text.strip().lower()
    t = re.sub(r"\s+dot\s+", ".", t)
    t = re.sub(r"\s+slash\s+", "/", t)
    return t


def looks_like_domain(text: str) -> bool:
    t = spoken_to_url_text(text)
    if " " in t:
        return False
    host = re.sub(r"^https?://", "", t).split("/")[0].split(":")[0]
    return bool(_HOST_RE.match(host)) or host == "localhost"


def validate_url(url: str) -> str:
    """Return a safe http(s) URL or raise UrlError. Adds https:// if no scheme is given."""
    if not isinstance(url, str) or not url.strip():
        raise UrlError("The address is empty.")
    url = url.strip()
    if len(url) > MAX_URL_LEN:
        raise UrlError("That address is too long.")
    if _CONTROL_RE.search(url):
        raise UrlError("The address contains spaces or control characters.")
    if "://" not in url:
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) and not re.match(r"^[^/]+:\d+(/|$)", url):
            raise UrlError("Only http and https addresses can be opened.")
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UrlError("Only http and https addresses can be opened.")
    if parts.username is not None or parts.password is not None or "@" in (parts.netloc or ""):
        raise UrlError("Addresses with embedded credentials are not allowed.")
    host = parts.hostname or ""
    if not (_HOST_RE.match(host) or host == "localhost"):
        raise UrlError(f"'{host or url}' does not look like a valid website address.")
    return url


def youtube_search_url(query: str) -> str:
    return f"{YOUTUBE_HOME}/results?search_query={quote_plus(query)}"
