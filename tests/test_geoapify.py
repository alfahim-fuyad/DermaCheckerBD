"""Tests for the Geoapify Places + Geocoding integration.

These tests exercise:
- successful Places API responses with the expected facility shape
- empty results
- missing API key (503 from the view)
- timeouts (504 from the view)
- non-2xx upstream responses (502 from the view)
- malformed JSON (502 from the view)
- coordinate validation (out-of-range lat/lon -> 400)
- radius validation (not in {1,3,5,10} -> 400)
- geocoding success with multiple matches
- geocoding with empty results
- caching: second call hits the cache, not the network

Production never uses mock data — these tests use ``unittest.mock`` to
patch ``requests.get`` so the Geoapify service is exercised against
fixtures that mirror the real response shape.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import django

BASE_DIR = Path(__file__).resolve().parents[1]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dermacheckerbd.settings")
os.environ.setdefault("ML_MODEL_BACKEND", "mock")
os.environ.setdefault("DJANGO_DEBUG", "True")
# Make sure the Geoapify key is set for most tests.
os.environ.setdefault("GEOAPIFY_API_KEY", "test-key-for-ci")
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

django.setup()

from django.conf import settings  # noqa: E402
from django.test import Client, TestCase  # noqa: E402
from django.core.cache import cache  # noqa: E402

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]


# ---------------------------------------------------------------------------
# Fixtures matching Geoapify's real response shape
# ---------------------------------------------------------------------------
PLACES_FIXTURE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "name": "Square Hospitals",
                "formatted": "Square Hospitals, Pantha Path, Panthopath, Dhaka - 1215, Bangladesh",
                "address_line1": "Square Hospitals",
                "address_line2": "Pantha Path, Panthopath, Dhaka - 1215, Bangladesh",
                "lon": 90.38161918573076,
                "lat": 23.75305172383741,
                "categories": ["healthcare", "healthcare.hospital"],
                "distance": 1464,
                "datasource": {
                    "sourcename": "openstreetmap",
                    "attribution": "© OpenStreetMap contributors",
                    "url": "https://www.openstreetmap.org/copyright",
                },
                "raw": {
                    "name": "স্কয়ার হাসপাতাল",
                    "amenity": "hospital",
                    "healthcare": "hospital",
                    "phone": "+88029661111",
                    "website": "https://www.squarehospital.com",
                },
                "place_id": "abc123",
            },
            "geometry": {"type": "Point", "coordinates": [90.38161918573076, 23.75305172383741]},
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Dhaka Life Care Hospital",
                "formatted": "Dhaka Life Care Hospital, Tejgaon Link Road, Dhaka, Bangladesh",
                "lon": 90.3907513,
                "lat": 23.7644136,
                "categories": ["healthcare", "healthcare.clinic_or_praxis"],
                "distance": 177,
                "datasource": {
                    "sourcename": "openstreetmap",
                    "attribution": "© OpenStreetMap contributors",
                },
                "raw": {
                    "amenity": "clinic",
                    "healthcare": "clinic",
                    "contact:phone": "+88029121597",
                },
                "place_id": "def456",
            },
            "geometry": {"type": "Point", "coordinates": [90.3907513, 23.7644136]},
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Skin & Dermatology Center",
                "formatted": "Skin & Dermatology Center, Dhaka",
                "lon": 90.395,
                "lat": 23.77,
                "categories": [
                    "healthcare",
                    "healthcare.clinic_or_praxis",
                    "healthcare.clinic_or_praxis.dermatology",
                ],
                "distance": 350,
                "datasource": {
                    "sourcename": "openstreetmap",
                    "attribution": "© OpenStreetMap contributors",
                },
                "raw": {
                    "amenity": "clinic",
                    "healthcare": "dermatologist",
                    "speciality": "dermatology",
                },
                "place_id": "ghi789",
            },
            "geometry": {"type": "Point", "coordinates": [90.395, 23.77]},
        },
    ],
}

GEOCODE_FIXTURE = {
    "results": [
        {
            "formatted": "Dhaka, Dhaka Division, Bangladesh",
            "lat": 23.8103,
            "lon": 90.4125,
            "country": "Bangladesh",
            "state": "Dhaka Division",
            "city": "Dhaka",
        },
        {
            "formatted": "Dhaka District, Bangladesh",
            "lat": 23.75,
            "lon": 90.40,
            "country": "Bangladesh",
        },
    ],
}


class _MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code
        self.text = json.dumps(json_data) if json_data is not None else ""

    def json(self):
        if self._json is None:
            raise ValueError("No JSON")
        return self._json


def _get_csrf(client):
    for path in ("/doctors/", "/accounts/login/", "/", "/predict/"):
        resp = client.get(path)
        m = __import__("re").search(
            r"name=['\"]csrfmiddlewaretoken['\"]\s+value=['\"]([^'\"]+)['\"]",
            resp.content.decode(),
        )
        if m:
            return m.group(1)
    return "test-csrf-token"


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------
class GeoapifyServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_search_nearby_success(self):
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(PLACES_FIXTURE)) as m:
            result = geoapify.search_nearby(
                latitude=23.7644, longitude=90.3890,
                radius_km=5, skip_cache=True,
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["facilities"]), 3)
        # Sorted by distance ascending: 177m, 350m, 1464m
        self.assertEqual(result["facilities"][0]["distance_m"], 177)
        self.assertEqual(result["facilities"][2]["distance_m"], 1464)
        # The dermatologist got tagged correctly
        derm = [f for f in result["facilities"] if f["is_dermatologist"]]
        self.assertEqual(len(derm), 1)
        self.assertEqual(derm[0]["name"], "Skin & Dermatology Center")
        # The clinic got the phone from raw.contact:phone
        clinic = [f for f in result["facilities"] if f["is_clinic"]]
        self.assertEqual(clinic[0]["phone"], "+88029121597")
        # Hospital phone from raw.phone
        hosp = [f for f in result["facilities"] if f["is_hospital"]]
        self.assertEqual(hosp[0]["phone"], "+88029661111")
        self.assertEqual(hosp[0]["website"], "https://www.squarehospital.com")
        # Directions URL points to Google Maps
        self.assertIn("google.com/maps/dir/", hosp[0]["directions_url"])
        # The API call used lon,lat order in the circle filter (not lat,lon)
        called_params = m.call_args.kwargs["params"]
        self.assertIn("circle:90.389,23.7644,5000", called_params["filter"])
        # API key was sent
        self.assertEqual(called_params["apiKey"], settings.GEOAPIFY_API_KEY)

    def test_search_nearby_empty_results(self):
        from apps.common.services import geoapify
        empty = {"type": "FeatureCollection", "features": []}
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(empty)):
            result = geoapify.search_nearby(
                latitude=23.76, longitude=90.39,
                radius_km=5, skip_cache=True,
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["facilities"], [])

    def test_search_nearby_dermatologists_only(self):
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(PLACES_FIXTURE)) as m:
            geoapify.search_nearby(
                latitude=23.76, longitude=90.39,
                radius_km=5, dermatologists_only=True, skip_cache=True,
            )
        called_params = m.call_args.kwargs["params"]
        # When dermatologists_only, only the dermatologist category is queried.
        self.assertEqual(
            called_params["categories"],
            "healthcare.clinic_or_praxis.dermatology",
        )

    def test_search_nearby_uses_geoapify_language_parameter(self):
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                               return_value=_MockResponse(PLACES_FIXTURE)) as m:
            geoapify.search_nearby(
                latitude=23.76, longitude=90.39,
                language="bn-BD", skip_cache=True,
            )
        called_params = m.call_args.kwargs["params"]
        self.assertEqual(called_params["lang"], "bn")
        self.assertNotIn("language", called_params)

    def test_search_nearby_missing_key(self):
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.settings, "GEOAPIFY_API_KEY", ""):
            with self.assertRaises(geoapify.GeoapifyError) as ctx:
                geoapify.search_nearby(latitude=23.7, longitude=90.4, skip_cache=True)
        self.assertIn("not configured", str(ctx.exception).lower())

    def test_search_nearby_timeout(self):
        import requests
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                side_effect=requests.exceptions.Timeout()):
            with self.assertRaises(geoapify.GeoapifyError) as ctx:
                geoapify.search_nearby(latitude=23.7, longitude=90.4, skip_cache=True)
        self.assertIn("took too long", str(ctx.exception).lower())

    def test_search_nearby_connection_error(self):
        import requests
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                side_effect=requests.exceptions.ConnectionError()):
            with self.assertRaises(geoapify.GeoapifyError) as ctx:
                geoapify.search_nearby(latitude=23.7, longitude=90.4, skip_cache=True)
        self.assertIn("could not reach", str(ctx.exception).lower())

    def test_search_nearby_http_401(self):
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(None, status_code=401)):
            with self.assertRaises(geoapify.GeoapifyError) as ctx:
                geoapify.search_nearby(latitude=23.7, longitude=90.4, skip_cache=True)
        self.assertIn("invalid or expired", str(ctx.exception).lower())

    def test_search_nearby_http_429(self):
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(None, status_code=429)):
            with self.assertRaises(geoapify.GeoapifyError) as ctx:
                geoapify.search_nearby(latitude=23.7, longitude=90.4, skip_cache=True)
        self.assertIn("busy", str(ctx.exception).lower())

    def test_search_nearby_malformed_json(self):
        from apps.common.services import geoapify
        # _MockResponse with _json=None raises ValueError on .json()
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(None, status_code=200)):
            with self.assertRaises(geoapify.GeoapifyError) as ctx:
                geoapify.search_nearby(latitude=23.7, longitude=90.4, skip_cache=True)
        self.assertIn("invalid response", str(ctx.exception).lower())

    def test_invalid_latitude(self):
        from apps.common.services import geoapify
        with self.assertRaises(geoapify.GeoapifyError):
            geoapify.search_nearby(latitude=999, longitude=90.4, skip_cache=True)
        with self.assertRaises(geoapify.GeoapifyError):
            geoapify.search_nearby(latitude="abc", longitude=90.4, skip_cache=True)

    def test_invalid_longitude(self):
        from apps.common.services import geoapify
        with self.assertRaises(geoapify.GeoapifyError):
            geoapify.search_nearby(latitude=23.7, longitude=999, skip_cache=True)

    def test_invalid_radius(self):
        from apps.common.services import geoapify
        with self.assertRaises(geoapify.GeoapifyError):
            geoapify.search_nearby(latitude=23.7, longitude=90.4, radius_km=7, skip_cache=True)
        with self.assertRaises(geoapify.GeoapifyError):
            geoapify.search_nearby(latitude=23.7, longitude=90.4, radius_km=0, skip_cache=True)

    def test_caching(self):
        """Second call hits the cache, not the network."""
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(PLACES_FIXTURE)) as m:
            r1 = geoapify.search_nearby(latitude=23.76, longitude=90.39, radius_km=5)
            self.assertFalse(r1["cached"])
            r2 = geoapify.search_nearby(latitude=23.76, longitude=90.39, radius_km=5)
            self.assertTrue(r2["cached"])
            self.assertEqual(r1["count"], r2["count"])
        # Only one network call for two searches at the same point.
        self.assertEqual(m.call_count, 1)

    def test_caching_jitter_rounding(self):
        """Two searches within the same 4-decimal rounding bucket
        should hit the same cache entry.

        4 decimal places ≈ 11m at the equator, which is a reasonable
        threshold for GPS jitter — two GPS fixes of the same spot
        typically differ by 5–15m. We use two points that fall in the
        same bucket (delta < 0.00005 so the 4th-decimal rounding
        doesn't cross a boundary).
        """
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(PLACES_FIXTURE)) as m:
            geoapify.search_nearby(latitude=23.7600, longitude=90.3900, radius_km=5)
            # 0.00003 deg ≈ 3m — same bucket when rounded to 4 decimals
            geoapify.search_nearby(latitude=23.76003, longitude=90.39003, radius_km=5)
        self.assertEqual(m.call_count, 1)

    def test_geocode_success(self):
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(GEOCODE_FIXTURE)):
            result = geoapify.geocode(query="Dhaka", skip_cache=True)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["matches"]), 2)
        self.assertEqual(result["matches"][0]["latitude"], 23.8103)
        self.assertEqual(result["matches"][0]["longitude"], 90.4125)
        self.assertEqual(result["matches"][0]["country"], "Bangladesh")

    def test_geocode_empty_results(self):
        from apps.common.services import geoapify
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse({"results": []})):
            result = geoapify.geocode(query="xyznotaplace", skip_cache=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["matches"], [])

    def test_geocode_short_query(self):
        from apps.common.services import geoapify
        with self.assertRaises(geoapify.GeoapifyError):
            geoapify.geocode(query="a", skip_cache=True)

    def test_haversine_distance(self):
        from apps.common.services.geoapify import haversine_km
        # Dhaka to Chittagong ≈ 240 km
        d = haversine_km(23.8103, 90.4125, 22.3569, 91.7832)
        self.assertGreater(d, 200)
        self.assertLess(d, 260)
        # Distance from a point to itself is 0
        self.assertAlmostEqual(haversine_km(23.7, 90.4, 23.7, 90.4), 0.0, places=4)


# ---------------------------------------------------------------------------
# View-layer tests
# ---------------------------------------------------------------------------
class DoctorsViewTests(TestCase):
    def setUp(self):
        cache.clear()
        settings.GEOAPIFY_API_KEY = "test-key-for-ci"
        self.client = Client()

    def test_finder_page_renders(self):
        resp = self.client.get("/doctors/")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # The page must reference MapLibre GL JS, not Leaflet
        self.assertIn("maplibre-gl", body)
        self.assertIn("cdn.jsdelivr.net/npm/maplibre-gl@4.7.1", body)
        self.assertIn('id="mapFallback"', body)
        self.assertIn("docs.map_unavailable", body)
        self.assertIn("if (!r.ok)", body)
        self.assertIn("showError(r.body, r.status, false)", body)
        self.assertNotIn("leaflet", body.lower())
        # The page must NOT embed the API key as a JS variable
        # (the API key only appears inside the map tiles URL — that's
        # acceptable per Geoapify's tile-rendering terms).
        # Check that no "apiKey: '...'" inline JS leaks the key:
        self.assertNotIn("var GEOAPIFY", body)
        self.assertNotIn("GEOAPIFY_API_KEY =", body)
        # Radius selector offers the configured options
        self.assertIn("1 km", body)
        self.assertIn("3 km", body)
        self.assertIn("5 km", body)
        self.assertIn("10 km", body)

    def test_finder_page_when_not_configured(self):
        with mock.patch.object(settings, "GEOAPIFY_API_KEY", ""):
            resp = self.client.get("/doctors/")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # The "not configured" disclaimer is shown
        self.assertIn("not_configured", body)
        self.assertIn("docs.map_not_configured", body)

    def test_search_endpoint_success(self):
        from apps.common.services import geoapify
        csrf = _get_csrf(self.client)
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(PLACES_FIXTURE)):
            resp = self.client.post(
                "/doctors/search/",
                data=json.dumps({
                    "latitude": 23.7644,
                    "longitude": 90.3890,
                    "radius_km": 5,
                    "dermatologists_only": False,
                }),
                content_type="application/json",
                HTTP_X_CSRFCOOKIE=csrf,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["count"], 3)
        self.assertEqual(len(body["facilities"]), 3)
        # API key is never echoed back
        self.assertNotIn("apiKey", json.dumps(body))
        self.assertNotIn("test-key", json.dumps(body))

    def test_search_endpoint_missing_key(self):
        csrf = _get_csrf(self.client)
        with mock.patch.object(settings, "GEOAPIFY_API_KEY", ""):
            resp = self.client.post(
                "/doctors/search/",
                data=json.dumps({
                    "latitude": 23.76, "longitude": 90.39, "radius_km": 5,
                }),
                content_type="application/json",
                HTTP_X_CSRFCOOKIE=csrf,
            )
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"], "not_configured")

    def test_search_endpoint_invalid_coords(self):
        csrf = _get_csrf(self.client)
        resp = self.client.post(
            "/doctors/search/",
            data=json.dumps({
                "latitude": 999, "longitude": 90.39, "radius_km": 5,
            }),
            content_type="application/json",
            HTTP_X_CSRFCOOKIE=csrf,
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"], "invalid_input")

    def test_search_endpoint_invalid_radius(self):
        csrf = _get_csrf(self.client)
        resp = self.client.post(
            "/doctors/search/",
            data=json.dumps({
                "latitude": 23.76, "longitude": 90.39, "radius_km": 7,
            }),
            content_type="application/json",
            HTTP_X_CSRFCOOKIE=csrf,
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"], "invalid_input")

    def test_search_endpoint_missing_coords(self):
        csrf = _get_csrf(self.client)
        resp = self.client.post(
            "/doctors/search/",
            data=json.dumps({"radius_km": 5}),
            content_type="application/json",
            HTTP_X_CSRFCOOKIE=csrf,
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"], "missing_coordinates")

    def test_search_endpoint_invalid_json(self):
        csrf = _get_csrf(self.client)
        resp = self.client.post(
            "/doctors/search/",
            data="not-json{",
            content_type="application/json",
            HTTP_X_CSRFCOOKIE=csrf,
        )
        self.assertEqual(resp.status_code, 400)

    def test_search_endpoint_timeout_returns_504(self):
        import requests
        from apps.common.services import geoapify
        csrf = _get_csrf(self.client)
        with mock.patch.object(geoapify.requests, "get",
                                side_effect=requests.exceptions.Timeout()):
            resp = self.client.post(
                "/doctors/search/",
                data=json.dumps({
                    "latitude": 23.76, "longitude": 90.39, "radius_km": 5,
                }),
                content_type="application/json",
                HTTP_X_CSRFCOOKIE=csrf,
            )
        self.assertEqual(resp.status_code, 504)
        body = resp.json()
        self.assertEqual(body["error"], "timeout")

    def test_search_endpoint_upstream_5xx_returns_502(self):
        from apps.common.services import geoapify
        csrf = _get_csrf(self.client)
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(None, status_code=500)):
            resp = self.client.post(
                "/doctors/search/",
                data=json.dumps({
                    "latitude": 23.76, "longitude": 90.39, "radius_km": 5,
                }),
                content_type="application/json",
                HTTP_X_CSRFCOOKIE=csrf,
            )
        self.assertEqual(resp.status_code, 502)
        body = resp.json()
        self.assertEqual(body["error"], "upstream_error")

    def test_search_endpoint_requires_post(self):
        resp = self.client.get("/doctors/search/")
        self.assertEqual(resp.status_code, 405)

    def test_geocode_endpoint_success(self):
        from apps.common.services import geoapify
        csrf = _get_csrf(self.client)
        with mock.patch.object(geoapify.requests, "get",
                                return_value=_MockResponse(GEOCODE_FIXTURE)):
            resp = self.client.post(
                "/doctors/geocode/",
                data=json.dumps({"query": "Dhaka"}),
                content_type="application/json",
                HTTP_X_CSRFCOOKIE=csrf,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["matches"]), 2)
        self.assertEqual(body["matches"][0]["latitude"], 23.8103)
        # API key never leaks
        self.assertNotIn("test-key", json.dumps(body))

    def test_geocode_endpoint_missing_query(self):
        csrf = _get_csrf(self.client)
        resp = self.client.post(
            "/doctors/geocode/",
            data=json.dumps({"query": ""}),
            content_type="application/json",
            HTTP_X_CSRFCOOKIE=csrf,
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"], "missing_query")

    def test_geocode_endpoint_missing_key(self):
        csrf = _get_csrf(self.client)
        with mock.patch.object(settings, "GEOAPIFY_API_KEY", ""):
            resp = self.client.post(
                "/doctors/geocode/",
                data=json.dumps({"query": "Dhaka"}),
                content_type="application/json",
                HTTP_X_CSRFCOOKIE=csrf,
            )
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertEqual(body["error"], "not_configured")


# ---------------------------------------------------------------------------
# Translation completeness check
# ---------------------------------------------------------------------------
class DoctorsTranslationTests(TestCase):
    def test_all_doctor_keys_have_bn(self):
        import re
        import pathlib
        project = pathlib.Path(BASE_DIR)
        trans = (project / "static" / "js" / "translations.js").read_text(encoding="utf-8")
        # Find every docs.* key used in the doctors template
        tpl = (project / "templates" / "doctors" / "finder.html").read_text(encoding="utf-8")
        keys = set(re.findall(r"data-i18n(?:-[a-z]+)?=\"(docs\.[a-z0-9_.-]+)\"", tpl))
        # Also keys used inside JS as window.DERMA.t('docs.xxx', ...)
        keys |= set(re.findall(r"t\('(docs\.[a-z0-9_.-]+)'", tpl))
        self.assertGreater(len(keys), 5, "expected to find several doctor translation keys")
        # bn block is the first occurrence after "bn:"
        bn_block = trans.split("bn:", 1)[1].split("en:", 1)[0]
        bn_keys = set(re.findall(r"'(docs\.[a-z0-9_.-]+)':", bn_block))
        missing = keys - bn_keys
        self.assertFalse(missing, f"Missing bn translations for: {sorted(missing)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
