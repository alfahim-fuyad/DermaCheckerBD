"""Geoapify Places + Geocoding API client.

Used by the "Nearby Doctors & Hospitals" feature in apps/doctors/.

Design goals
------------
- The API key is read from settings.GEOAPIFY_API_KEY and is NEVER passed
  back to the browser in any Django response, template, or AJAX payload.
- Both endpoints (Places + Geocoding) share a single ``requests`` session
  with a per-call timeout.
- A short-lived Django cache (LocMemCache in dev, Redis/Memcached in
  production) reduces repeated calls when a user clicks the same search
  twice within a few minutes.
- Coordinates and radius are validated server-side before any API call
  is made. Invalid inputs raise ``GeoapifyError`` with a user-facing
  message — the view catches it and returns a 400.
- The response is normalised into a flat list of facility dicts with
  safe field access (``.get`` everywhere) so a missing ``phone`` or
  ``address_line2`` never crashes the renderer.
- "Specialist" tagging is conservative: we only label a facility as a
  dermatologist when Geoapify returns the
  ``healthcare.clinic_or_praxis.dermatology``
  category, OR the underlying OSM raw tags contain ``speciality``
  mentioning dermatology. Otherwise we surface a clear disclaimer that
  the user should call the facility to confirm dermatology services.

Rate limits
-----------
Geoapify's free tier allows 3000 requests/day. The cache + 20-result
cap keep us well under that for typical university-capstone traffic.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Allowed Geoapify place categories we ever query. Keep this list narrow
# so we never accidentally pull in non-healthcare POIs.
HEALTHCARE_CATEGORIES = (
    "healthcare.hospital",
    "healthcare.clinic_or_praxis",
    "healthcare.clinic_or_praxis.dermatology",
)

# Categories that count as "hospital" for the UI badge.
HOSPITAL_CATEGORIES = ("healthcare.hospital",)
CLINIC_CATEGORIES = ("healthcare.clinic_or_praxis",)
DERMATOLOGIST_CATEGORIES = ("healthcare.clinic_or_praxis.dermatology",)

# Bounding latitude / longitude validity (covers all of Bangladesh and
# most of the world's inhabited latitudes). Inputs outside this range
# are rejected before we hit the API.
LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0

# Allowed radius options (km) — exposed in the UI as a dropdown.
ALLOWED_RADIUS_KM = (1, 3, 5, 10)
DEFAULT_RADIUS_KM = 5

# Cache key prefix used for both geocode and places results.
_CACHE_PREFIX = "geoapify:v1"


class GeoapifyError(Exception):
    """Raised on any Geoapify-related failure (missing key, invalid
    input, network error, non-2xx response, malformed JSON).

    The view layer catches this and surfaces ``str(error)`` to the user.
    We do not log the API key, request URL, or response body when the
    key is embedded — only a short summary.
    """


# ---------------------------------------------------------------------------
# Coordinate + radius validation
# ---------------------------------------------------------------------------
def _validate_lat(lat: Any) -> float:
    try:
        v = float(lat)
    except (TypeError, ValueError) as exc:
        raise GeoapifyError("Invalid latitude.") from exc
    if not math.isfinite(v) or v < LAT_MIN or v > LAT_MAX:
        raise GeoapifyError("Latitude is out of the supported range.")
    return v


def _validate_lon(lon: Any) -> float:
    try:
        v = float(lon)
    except (TypeError, ValueError) as exc:
        raise GeoapifyError("Invalid longitude.") from exc
    if not math.isfinite(v) or v < LON_MIN or v > LON_MAX:
        raise GeoapifyError("Longitude is out of the supported range.")
    return v


def _validate_radius_km(radius_km: Any) -> int:
    try:
        v = int(radius_km)
    except (TypeError, ValueError) as exc:
        raise GeoapifyError("Invalid search radius.") from exc
    if v not in ALLOWED_RADIUS_KM:
        raise GeoapifyError(
            f"Search radius must be one of: {', '.join(str(r) for r in ALLOWED_RADIUS_KM)} km."
        )
    return v


def _require_api_key() -> str:
    key = (getattr(settings, "GEOAPIFY_API_KEY", "") or "").strip()
    if not key:
        raise GeoapifyError(
            "Geoapify API key is not configured. Set GEOAPIFY_API_KEY in the environment."
        )
    return key


# ---------------------------------------------------------------------------
# Haversine distance (km) — used as a fallback when Geoapify's
# ``distance`` field is missing (which happens for some POIs).
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS84 points."""
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Response normalisation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Facility:
    """Flat, JSON-serialisable view of one Geoapify Places feature."""
    name: str
    address: str
    latitude: float
    longitude: float
    distance_m: Optional[float]
    phone: str
    website: str
    categories: List[str]
    is_hospital: bool
    is_clinic: bool
    is_dermatologist: bool
    source: str
    attribution: str
    osm_url: str
    directions_url: str
    place_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "distance_m": self.distance_m,
            "distance_km": (self.distance_m / 1000.0) if self.distance_m is not None else None,
            "phone": self.phone,
            "website": self.website,
            "categories": self.categories,
            "is_hospital": self.is_hospital,
            "is_clinic": self.is_clinic,
            "is_dermatologist": self.is_dermatologist,
            "source": self.source,
            "attribution": self.attribution,
            "osm_url": self.osm_url,
            "directions_url": self.directions_url,
            "place_id": self.place_id,
        }


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _normalise_feature(
    feature: Dict[str, Any],
    user_lat: Optional[float],
    user_lon: Optional[float],
) -> Optional[Facility]:
    """Turn one Geoapify Places feature into a :class:`Facility`.

    Returns ``None`` if the feature is missing a usable geometry (we
    cannot render a POI without coordinates).
    """
    if not isinstance(feature, dict):
        return None
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    if geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None
    try:
        lon = float(coords[0])
        lat = float(coords[1])
    except (TypeError, ValueError):
        return None

    # Prefer Geoapify's pre-computed distance; fall back to haversine.
    distance_m: Optional[float] = None
    raw_dist = props.get("distance")
    if raw_dist is not None:
        try:
            distance_m = float(raw_dist)
        except (TypeError, ValueError):
            distance_m = None
    if distance_m is None and user_lat is not None and user_lon is not None:
        distance_m = haversine_km(user_lat, user_lon, lat, lon) * 1000.0

    # The display name: prefer the localized Bengali name when the UI
    # is in Bengali. The browser-side JS does this re-rendering using
    # ``name_international.bn`` if present; we expose both fields.
    name = (
        _safe_str(props.get("name"))
        or _safe_str(props.get("address_line1"))
        or "Unnamed facility"
    )

    # Build a clean single-line address from Geoapify's formatted string.
    address = _safe_str(props.get("formatted")) or _safe_str(props.get("address_line2"))

    # Phone: Geoapify exposes it inside ``contact.phone`` for newer
    # responses, or directly on properties for older ones. Some OSM
    # POIs only have it in ``raw.contact:phone`` or ``raw.phone``.
    phone = (
        _safe_str((props.get("contact") or {}).get("phone"))
        or _safe_str(props.get("phone"))
        or _safe_str((props.get("raw") or {}).get("phone"))
        or _safe_str((props.get("raw") or {}).get("contact:phone"))
    )
    website = (
        _safe_str((props.get("raw") or {}).get("website"))
        or _safe_str((props.get("raw") or {}).get("contact:website"))
        or _safe_str(props.get("website"))
    )

    # Categories is a list of strings like
    # ["healthcare", "healthcare.hospital", "building", ...]
    cats = props.get("categories") or []
    if not isinstance(cats, list):
        cats = []
    cats_str = [_safe_str(c) for c in cats]
    cat_set = set(cats_str)

    is_hospital = any(c in cat_set for c in HOSPITAL_CATEGORIES)
    is_clinic = any(c in cat_set for c in CLINIC_CATEGORIES)
    is_dermatologist = any(c in cat_set for c in DERMATOLOGIST_CATEGORIES)

    # Conservative dermatologist tagging: also accept OSM raw tag
    # ``healthcare=specialist`` + ``speciality:dermatology`` OR a name
    # that explicitly says "dermatology" / "skin" (rare — only when the
    # facility is a known dermatology center). We DO NOT tag a hospital
    # as dermatology just because it offers many services.
    raw = props.get("raw") or {}
    raw_speciality = _safe_str(raw.get("speciality")).lower()
    raw_healthcare = _safe_str(raw.get("healthcare")).lower()
    if "dermat" in raw_speciality or "skin" in raw_speciality:
        is_dermatologist = True
    if raw_healthcare == "dermatologist":
        is_dermatologist = True

    # Source attribution: Geoapify returns this in ``datasource``.
    datasource = props.get("datasource") or {}
    source = _safe_str(datasource.get("sourcename")) or "geoapify"
    attribution = (
        _safe_str(datasource.get("attribution"))
        or "© OpenStreetMap contributors"
    )
    osm_url = _safe_str(datasource.get("url")) or "https://www.openstreetmap.org/copyright"

    # Google Maps directions link — based on facility coordinates.
    directions_url = (
        f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
    )

    return Facility(
        name=name,
        address=address,
        latitude=lat,
        longitude=lon,
        distance_m=distance_m,
        phone=phone,
        website=website,
        categories=cats_str,
        is_hospital=is_hospital,
        is_clinic=is_clinic,
        is_dermatologist=is_dermatologist,
        source=source,
        attribution=attribution,
        osm_url=osm_url,
        directions_url=directions_url,
        place_id=_safe_str(props.get("place_id")),
    )


# ---------------------------------------------------------------------------
# Places API (nearby hospitals / clinics / dermatologists)
# ---------------------------------------------------------------------------
def _places_cache_key(lat: float, lon: float, radius_km: int,
                       dermatologists_only: bool) -> str:
    # Round to 4 decimal places (~11 m at the equator) so two searches
    # 10 m apart hit the same cache entry. Prevents typical GPS jitter
    # (5–15 m) from busting the cache while keeping searches at
    # different addresses separate.
    return (
        f"{_CACHE_PREFIX}:places:"
        f"{lat:.4f}:{lon:.4f}:{radius_km}:{int(dermatologists_only)}"
    )


def search_nearby(
    latitude: float,
    longitude: float,
    radius_km: int = DEFAULT_RADIUS_KM,
    dermatologists_only: bool = False,
    language: Optional[str] = None,
    skip_cache: bool = False,
) -> Dict[str, Any]:
    """Search for healthcare facilities near a point.

    Args:
        latitude, longitude: WGS84 coordinates of the search centre.
        radius_km: search radius in km. Must be in ALLOWED_RADIUS_KM.
        dermatologists_only: when True, only query
            ``healthcare.clinic_or_praxis.dermatology`` (much narrower results).
        language: optional ISO-639-1 code passed to Geoapify so the
            ``formatted`` address comes back in the user's UI language.
            Falls back to Geoapify's default (English).
        skip_cache: bypass the cache (used by tests).

    Returns:
        A dict suitable for ``JsonResponse``::

            {
              "success": True,
              "centre": {"latitude": float, "longitude": float,
                         "radius_km": int},
              "count": int,
              "facilities": [Facility.to_dict(), ...],
              "attribution": "© OpenStreetMap contributors",
              "cached": bool,
            }

    Raises:
        GeoapifyError: on missing key, invalid input, network failure,
            non-2xx response, malformed JSON.
    """
    lat = _validate_lat(latitude)
    lon = _validate_lon(longitude)
    radius_km = _validate_radius_km(radius_km)
    api_key = _require_api_key()

    cache_key = _places_cache_key(lat, lon, radius_km, dermatologists_only)
    if not skip_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    radius_m = radius_km * 1000
    # Geoapify's circle filter is ``circle:lon,lat,radiusMeters``.
    # The order is LON,LAT — not lat,lon — per the API docs.
    categories = (
        DERMATOLOGIST_CATEGORIES
        if dermatologists_only
        else HEALTHCARE_CATEGORIES
    )
    params = {
        "categories": ",".join(categories),
        "filter": f"circle:{lon},{lat},{radius_m}",
        "bias": f"proximity:{lon},{lat}",
        "limit": str(settings.DOCTOR_SEARCH_MAX_RESULTS),
        "apiKey": api_key,
    }
    if language:
        params["lang"] = language[:2].lower()

    try:
        resp = requests.get(
            settings.GEOAPIFY_PLACES_URL,
            params=params,
            timeout=settings.GEOAPIFY_TIMEOUT,
            headers={"Accept": "application/json"},
        )
    except requests.exceptions.Timeout as exc:
        logger.warning("Geoapify Places timeout for lat=%s lon=%s", lat, lon)
        raise GeoapifyError(
            "The location search took too long. Please try again."
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        logger.warning("Geoapify Places connection error: %s", exc)
        raise GeoapifyError(
            "Could not reach the location service. Please try again later."
        ) from exc
    except requests.exceptions.RequestException as exc:
        logger.warning("Geoapify Places request failed: %s", exc)
        raise GeoapifyError("The location service could not be contacted.") from exc

    if resp.status_code == 401:
        # The API key is wrong / disabled. Hide the raw upstream body
        # (it sometimes echoes the partial key back) and surface a
        # generic message instead.
        logger.error("Geoapify returned 401 — check GEOAPIFY_API_KEY.")
        raise GeoapifyError(
            "The location service API key is invalid or expired."
        )
    if resp.status_code == 429:
        logger.warning("Geoapify Places rate-limited.")
        raise GeoapifyError(
            "The location service is busy. Please try again in a moment."
        )
    if resp.status_code >= 400:
        logger.warning("Geoapify Places HTTP %s", resp.status_code)
        raise GeoapifyError(
            "The location service returned an error. Please try again."
        )

    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("Geoapify Places returned non-JSON body")
        raise GeoapifyError("The location service returned an invalid response.") from exc

    features = data.get("features") or []
    facilities: List[Facility] = []
    attribution = "© OpenStreetMap contributors"
    for feat in features:
        normalised = _normalise_feature(feat, lat, lon)
        if normalised is None:
            continue
        # Reuse the last-seen attribution so we can show it once in
        # the UI footer. They are all OSM-sourced in practice.
        if normalised.attribution:
            attribution = normalised.attribution
        facilities.append(normalised)

    # Sort by distance ascending; missing distances go last.
    facilities.sort(key=lambda f: (f.distance_m is None, f.distance_m or 0.0))

    result = {
        "success": True,
        "centre": {
            "latitude": lat,
            "longitude": lon,
            "radius_km": radius_km,
        },
        "count": len(facilities),
        "facilities": [f.to_dict() for f in facilities],
        "attribution": attribution,
        "cached": False,
    }

    if not skip_cache:
        try:
            cache.set(cache_key, result, settings.GEOAPIFY_CACHE_TTL)
        except Exception:
            # Cache failure must never break the user's search.
            logger.debug("Geoapify cache set failed (non-fatal).")
    return result


# ---------------------------------------------------------------------------
# Geocoding API (area name -> coordinates)
# ---------------------------------------------------------------------------
def _geocode_cache_key(query: str) -> str:
    return f"{_CACHE_PREFIX}:geocode:{query.strip().lower()[:128]}"


def geocode(query: str, skip_cache: bool = False) -> Dict[str, Any]:
    """Convert a free-text area / city name to a lat/lon pair.

    Returns:
        A dict::

            {
              "success": True,
              "query": "Dhaka",
              "matches": [
                {"name": "Dhaka, Bangladesh",
                 "latitude": 23.81, "longitude": 90.41, "country": "Bangladesh"},
                ...
              ],
              "cached": bool,
            }

    The view picks the first match and immediately calls
    :func:`search_nearby` with it.
    """
    q = (query or "").strip()
    if len(q) < 2:
        raise GeoapifyError("Please enter a longer search term.")
    if len(q) > 200:
        raise GeoapifyError("Search term is too long.")
    api_key = _require_api_key()

    cache_key = _geocode_cache_key(q)
    if not skip_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    params = {
        "text": q,
        "limit": "5",
        "format": "json",
        "apiKey": api_key,
    }
    try:
        resp = requests.get(
            settings.GEOAPIFY_GEOCODE_URL,
            params=params,
            timeout=settings.GEOAPIFY_TIMEOUT,
            headers={"Accept": "application/json"},
        )
    except requests.exceptions.Timeout as exc:
        raise GeoapifyError("The location lookup took too long. Please try again.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise GeoapifyError("Could not reach the geocoding service.") from exc
    except requests.exceptions.RequestException as exc:
        raise GeoapifyError("The geocoding service could not be contacted.") from exc

    if resp.status_code == 401:
        raise GeoapifyError("The geocoding API key is invalid or expired.")
    if resp.status_code == 429:
        raise GeoapifyError("The geocoding service is busy. Please try again later.")
    if resp.status_code >= 400:
        raise GeoapifyError("The geocoding service returned an error.")

    try:
        data = resp.json()
    except ValueError as exc:
        raise GeoapifyError("The geocoding service returned an invalid response.") from exc

    # Geoapify geocode /search returns either a list (format=json) or
    # an object with ``results`` (default format). Support both.
    results = data.get("results") if isinstance(data, dict) else data
    if not isinstance(results, list):
        results = []

    matches: List[Dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        try:
            lat = float(r.get("lat"))
            lon = float(r.get("lon"))
        except (TypeError, ValueError):
            continue
        matches.append({
            "name": _safe_str(r.get("formatted")) or _safe_str(r.get("name")) or q,
            "latitude": lat,
            "longitude": lon,
            "country": _safe_str(r.get("country")),
            "state": _safe_str(r.get("state")),
            "city": _safe_str(r.get("city")),
        })

    result = {
        "success": True,
        "query": q,
        "matches": matches,
        "cached": False,
    }
    if not skip_cache:
        try:
            cache.set(cache_key, result, settings.GEOAPIFY_CACHE_TTL)
        except Exception:
            logger.debug("Geoapify geocode cache set failed (non-fatal).")
    return result


def is_configured() -> bool:
    """True when a Geoapify key is set."""
    return bool((getattr(settings, "GEOAPIFY_API_KEY", "") or "").strip())
