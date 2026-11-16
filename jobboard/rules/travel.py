"""About how long the trip to a job would take from home (config.HOME), when the post gives a street address or ZIP code.

Places are looked up on OpenStreetMap (Nominatim) once each and kept in the `geo` table. Only the job's own
address is sent, never anything about you. The times are estimates from the distance, not live directions:

    driving        = straight line x 1.35 for the roads, at 30 km/h through DC traffic, plus 5 minutes to park
    Metro / bus    = straight line at 25 km/h (Metro runs fairly straight; the Green Line goes from Suitland
                     into the city), plus 15 minutes of walking and waiting
"""
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from ..config import HOME  # (name, latitude, longitude): change it in config.py

NOMINATIM = "https://nominatim.openstreetmap.org/search"
AGENT = "jobboard-local/1.0 (personal job search)"
LOOKUPS_PER_REFRESH = 25   # Nominatim asks for at most one request a second; new addresses beyond this wait for the next refresh


def address_query(location):
    """A searchable address from a job's location, or None when it only names a city ('Washington, DC')."""
    best = None
    for part in re.split(r"\s+·\s+", location or ""):
        p = re.sub(r"\s+", " ", part).strip()
        if not (re.match(r"^\d+\s+\w", p) or re.search(r"\b\d{5}(?:-\d{4})?\b", p)):
            continue
        p = re.sub(r",?\s*(?:ste|suite|unit|#|fl|floor)\.?\s*[\w-]+(?=,|\s|$)", ",", p, flags=re.I)  # suites don't help find the building
        p = re.sub(r"\s*,(\s*,)+", ",", p).strip(", ")
        p = re.sub(r"\b(\d{5})-\d{4}\b", r"\1", p)
        p = re.sub(r",(?=\S)", ", ", p)
        best = best or p
    return best


def geocode(query):
    """(lat, lon) for an address, or None. Raises nothing: a failed lookup just means no travel time."""
    url = NOMINATIM + "?" + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "us"})
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None
    if not data:
        return None
    try:
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def lookup_all(queries, pause=1.1):
    """Look up several new addresses politely. {query: (lat, lon) or None}."""
    out = {}
    for i, q in enumerate(list(queries)[:LOOKUPS_PER_REFRESH]):
        if i:
            time.sleep(pause)
        out[q] = geocode(q)
    return out


def km_between(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def estimate(point):
    """{'km', 'drive', 'transit'} minutes from Suitland to (lat, lon)."""
    km = km_between((HOME[1], HOME[2]), point)
    road = km * 1.35
    return {"km": round(km, 1), "drive": round(road / 30 * 60 + 5), "transit": round(km / 25 * 60 + 15)}
