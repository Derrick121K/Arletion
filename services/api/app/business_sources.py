"""Low-volume, source-attributed OpenStreetMap business discovery."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_SOURCE = "OpenStreetMap Business Directory"
OSM_ATTRIBUTION = "© OpenStreetMap contributors · ODbL 1.0"

# Only named business-oriented features are imported; no personal contact tags.
CATEGORY_FILTERS = {
    "Construction": {
        "shop": ("building_materials", "hardware", "trade", "doityourself"),
        "craft": ("builder", "carpenter", "plumber", "electrician", "roofer", "plasterer", "tiler"),
        "office": ("construction",),
    },
    "Building materials": {
        "shop": ("building_materials", "hardware", "trade", "doityourself"),
    },
    "Transport and logistics": {
        "office": ("logistics", "shipping", "moving_company"),
        "industrial": ("warehouse",),
        "shop": ("truck", "trailer", "car_repair"),
    },
    "IT and software": {
        "office": ("it", "telecommunication", "company"),
        "shop": ("computer", "electronics"),
    },
    "Training and education": {
        "office": ("educational_institution", "training"),
        "amenity": ("school", "college", "university", "language_school"),
    },
    "Cleaning and facilities": {
        "office": ("cleaning", "janitorial"),
        "craft": ("cleaner", "cleaning"),
    },
    "Security services": {
        "office": ("security",),
        "shop": ("security",),
    },
    "Agriculture": {
        "office": ("agricultural",),
        "shop": ("agrarian", "farm"),
        "craft": ("agricultural_machinery",),
    },
    "Manufacturing": {
        "industrial": ("manufacturing", "factory"),
        "office": ("industrial",),
    },
    "Retail and wholesale": {
        "shop": (),
        "office": ("wholesale",),
    },
    "Professional services": {
        "office": ("accountant", "architect", "lawyer", "insurance", "estate_agent", "consulting", "engineer"),
    },
}


def overpass_query(category: str, latitude: float, longitude: float, radius_m: int, limit: int) -> str:
    filters = CATEGORY_FILTERS.get(category)
    if filters is None:
        raise ValueError("Choose a supported business category.")
    clauses = []
    for key, values in filters.items():
        tag_filter = f'["{key}"]' if not values else f'["{key}"~"^({"|".join(re.escape(value) for value in values)})$",i]'
        clauses.append(
            f'nwr(around:{radius_m},{latitude:.6f},{longitude:.6f})["name"]{tag_filter};'
        )
    return "[out:json][timeout:35];\n(\n" + "\n".join(clauses) + f"\n);\nout center tags meta {limit};"


def _safe_website(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if not re.match(r"^https?://", candidate, re.I):
        candidate = "https://" + candidate
    try:
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        return parsed.hostname.lower().rstrip(".")
    except ValueError:
        return None


def normalize_osm_businesses(payload: dict, category: str, locality: str, province: str) -> list[dict]:
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise ValueError("OpenStreetMap returned an invalid response.")
    seen: set[str] = set()
    results = []
    for element in elements:
        if not isinstance(element, dict) or element.get("type") not in {"node", "way", "relation"}:
            continue
        if not isinstance(element.get("id"), int) or element["id"] <= 0:
            continue
        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
        name = str(tags.get("name") or "").strip()
        if not name or len(name) > 200:
            continue
        if any(key in tags for key in ("disused:shop", "abandoned:shop", "vacant")):
            continue
        external_id = f"{element['type']}/{element['id']}"
        if external_id in seen:
            continue
        seen.add(external_id)
        website = _safe_website(tags.get("contact:website") or tags.get("website") or tags.get("url"))
        timestamp = element.get("timestamp")
        updated_at = None
        if timestamp:
            try:
                updated_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
            except ValueError:
                updated_at = None
        url = f"https://www.openstreetmap.org/{element['type']}/{element['id']}"
        results.append({
            "external_id": external_id,
            "name": name,
            "category": category,
            "locality": str(tags.get("addr:suburb") or tags.get("addr:city") or locality)[:120],
            "province": str(tags.get("addr:province") or province)[:100],
            "website_domain": website,
            "latitude": element.get("lat") or (element.get("center") or {}).get("lat"),
            "longitude": element.get("lon") or (element.get("center") or {}).get("lon"),
            "source_url": url,
            "source_updated_at": updated_at,
            "tags": {
                key: tags[key] for key in (
                    "shop", "office", "craft", "industrial", "amenity",
                    "addr:suburb", "addr:city", "addr:province",
                ) if key in tags
            },
        })
    return results


def fetch_osm_businesses(category: str, latitude: float, longitude: float, radius_m: int, locality: str, province: str, limit: int = 100) -> list[dict]:
    query = overpass_query(category, latitude, longitude, radius_m, limit)
    try:
        with httpx.Client(
            timeout=httpx.Timeout(45, connect=10),
            headers={"User-Agent": "Arletion/0.2 (+https://github.com/Derrick121K/Arletion)"},
            follow_redirects=False,
        ) as client:
            response = client.post(OVERPASS_URL, data={"data": query})
            response.raise_for_status()
            if len(response.content) > 8_000_000:
                raise ValueError("OpenStreetMap response exceeded the 8 MB safety limit.")
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RuntimeError("OpenStreetMap could not complete this search. Retry later or reduce the search radius.") from error
    return normalize_osm_businesses(payload, category, locality, province)
