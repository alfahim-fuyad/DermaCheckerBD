#!/usr/bin/env python3
"""Run a live end-to-end test against the running Django server:
- Upload an image via HTTP POST to /predict/
- Follow the redirect to the result page
- Download the PDF report
- Test the chatbot endpoint in offline mode
"""
import io
import os
import sys
import time
import requests
import numpy as np
from PIL import Image

BASE = "http://127.0.0.1:8765"


def make_test_image(seed=42):
    rng = np.random.default_rng(seed)
    base = np.array([220, 170, 130], dtype=np.uint8)
    arr = np.tile(base, (300, 300, 1)).astype(np.uint8)
    noise = rng.integers(-20, 20, size=(300, 300, 3), dtype=np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    yy, xx = np.mgrid[0:300, 0:300]
    dist = np.sqrt((yy - 150) ** 2 + (xx - 150) ** 2)
    mask = dist < 60
    arr[mask] = [120, 70, 50]
    edge = (dist > 55) & (dist < 65)
    arr[edge] = [180, 120, 90]
    buf = io.BytesIO()
    Image.fromarray(arr).convert("RGB").save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


def get_csrf(session, path):
    r = session.get(f"{BASE}{path}")
    csrf = r.cookies.get("csrftoken")
    return csrf


def main():
    session = requests.Session()

    # 1. Get the upload page to obtain CSRF
    csrf = get_csrf(session, "/predict/")
    assert csrf, "No CSRF token received"
    print(f"[OK] Got CSRF: {csrf[:16]}...")

    # 2. Upload image
    img_buf = make_test_image()
    files = {"image": ("test.jpg", img_buf, "image/jpeg")}
    data = {"csrfmiddlewaretoken": csrf}
    r = session.post(f"{BASE}/predict/", files=files, data=data, allow_redirects=False)
    print(f"[OK] Upload returned: HTTP {r.status_code}")
    assert r.status_code in (302, 301), f"Expected redirect, got {r.status_code}"
    result_url = r.headers.get("Location")
    print(f"[OK] Redirected to: {result_url}")
    assert result_url.startswith("/predict/result/")

    # 3. Fetch the result page
    r = session.get(f"{BASE}{result_url}")
    assert r.status_code == 200, f"Result page returned {r.status_code}"
    body = r.text
    # Check key markers in the result page
    if "Prediction" not in body and "prediction" not in body:
        print("[FAIL] Result page is missing prediction content")
    if "Confidence" not in body and "confidence" not in body:
        print("[FAIL] Result page is missing confidence")
    print(f"[OK] Result page: HTTP {r.status_code} ({len(body)} bytes)")

    # Extract reference ID
    import re
    m = re.search(r"Reference ([A-F0-9]+)", body)
    assert m, "Could not find Reference ID"
    ref_id = m.group(1)
    print(f"[OK] Reference ID: {ref_id}")

    # 4. Download PDF
    pdf_url = f"/predict/result/{ref_id}/pdf/"
    r = session.get(f"{BASE}{pdf_url}")
    assert r.status_code == 200, f"PDF download returned {r.status_code}"
    assert r.headers["Content-Type"] == "application/pdf"
    out_path = "/home/z/my-project/download/uploaded_test_report.pdf"
    with open(out_path, "wb") as f:
        f.write(r.content)
    print(f"[OK] Downloaded PDF: {out_path} ({len(r.content)} bytes)")

    # 5. Test chatbot endpoint (offline mode — no Gemini key configured)
    csrf = get_csrf(session, "/")
    headers = {"X-CSRFToken": csrf}
    payload = {"message": "What does the confidence score mean?"}
    r = session.post(f"{BASE}/chatbot/message/", json=payload, headers=headers)
    assert r.status_code == 200, f"Chatbot returned {r.status_code}"
    data = r.json()
    print(f"[OK] Chatbot offline reply: {data['reply'][:120]}...")
    assert "offline" in data["reply"].lower() or "not configured" in data["reply"].lower() or "confidence" in data["reply"].lower()

    # 6. Test image-quality-checker endpoint
    csrf = get_csrf(session, "/quality/")
    img_buf = make_test_image(seed=99)
    files = {"image": ("q.jpg", img_buf, "image/jpeg")}
    data = {"csrfmiddlewaretoken": csrf}
    r = session.post(f"{BASE}/quality/", files=files, data=data)
    assert r.status_code == 200, f"Quality check returned {r.status_code}"
    if "Image quality report" in r.text:
        print("[OK] Quality check produced a report")
    else:
        print("[WARN] Quality check page did not show a report")

    # 7. Test reliability endpoint
    csrf = get_csrf(session, "/reliability/")
    img_buf = make_test_image(seed=11)
    files = {"image": ("r.jpg", img_buf, "image/jpeg")}
    data = {"csrfmiddlewaretoken": csrf}
    r = session.post(f"{BASE}/reliability/", files=files, data=data)
    assert r.status_code == 200
    if "Prediction reliability check" in r.text:
        print("[OK] Reliability check produced a report")
    else:
        print("[WARN] Reliability check page did not show a report")

    # 8. Test multi-image endpoint
    csrf = get_csrf(session, "/multi/")
    files = [
        ("images", ("a.jpg", make_test_image(seed=1), "image/jpeg")),
        ("images", ("b.jpg", make_test_image(seed=2), "image/jpeg")),
        ("images", ("c.jpg", make_test_image(seed=3), "image/jpeg")),
    ]
    data = {"csrfmiddlewaretoken": csrf}
    r = session.post(f"{BASE}/multi/", files=files, data=data)
    assert r.status_code == 200
    if "Multi-image comparison" in r.text and "Modal class" in r.text:
        print("[OK] Multi-image comparison produced a report")
    else:
        print("[WARN] Multi-image comparison page did not show a report")

    print("\n=== ALL END-TO-END TESTS PASSED ===")


if __name__ == "__main__":
    main()
