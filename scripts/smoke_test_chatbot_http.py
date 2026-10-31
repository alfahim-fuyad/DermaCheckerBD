"""End-to-end HTTP smoke test for the multi-provider chatbot views."""
from django.test.utils import setup_databases
from django.test.runner import DiscoverRunner


def _clear_cache():
    from django.core.cache import cache
    cache.clear()


def main():
    runner = DiscoverRunner(verbosity=0)
    old_config = runner.setup_databases()

    import json
    from unittest.mock import patch
    from django.contrib.auth import get_user_model
    from django.test import Client
    from apps.chatbot.faqs import FAQS
    from apps.common.services.ai_providers import GeminiProvider
    from apps.common.services.ai_providers.base import ProviderResult

    User = get_user_model()
    client = Client()

    print("=== HTTP smoke test: chatbot views ===\n")

    # --- 1. Anonymous FAQ button click (English) ---
    print("[1] Anonymous FAQ button click (English)")
    _clear_cache()
    first = FAQS[0]
    r = client.post(
        "/chatbot/message/",
        data=json.dumps({"faq_id": first["id"], "language": "en"}),
        content_type="application/json",
    )
    print(f"    status={r.status_code}, scope={r.json().get('scope')}, authed={r.json().get('authed')}, faq_id={r.json().get('faq_id')}")
    print(f"    reply starts: {r.json()['reply'][:60]}...")
    assert r.status_code == 200
    assert r.json()["scope"] == "public"
    assert r.json()["authed"] is False
    assert r.json()["faq_id"] == first["id"]
    print("    PASS\n")

    # --- 2. Anonymous FAQ button click (Bengali) ---
    print("[2] Anonymous FAQ button click (Bengali)")
    _clear_cache()
    r = client.post(
        "/chatbot/message/",
        data=json.dumps({"faq_id": first["id"], "language": "bn"}),
        content_type="application/json",
    )
    print(f"    status={r.status_code}, reply starts: {r.json()['reply'][:60]}...")
    assert r.status_code == 200
    assert "DermaCheckerBD" in r.json()["reply"]
    print("    PASS\n")

    # --- 3. Anonymous free-text that matches a FAQ ---
    print("[3] Anonymous free-text matching FAQ")
    _clear_cache()
    r = client.post(
        "/chatbot/message/",
        data=json.dumps({"message": "What is DermaCheckerBD?", "language": "en"}),
        content_type="application/json",
    )
    print(f"    status={r.status_code}, faq_id={r.json().get('faq_id')}")
    assert r.status_code == 200
    assert r.json()["faq_id"] == "what_is"
    print("    PASS\n")

    # --- 4. Anonymous free-text unrelated -> guidance ---
    print("[4] Anonymous free-text unrelated -> guidance with FAQ list")
    _clear_cache()
    r = client.post(
        "/chatbot/message/",
        data=json.dumps({"message": "what is the weather?", "language": "en"}),
        content_type="application/json",
    )
    print(f"    status={r.status_code}, has faqs={('faqs' in r.json())}, faq count={len(r.json().get('faqs', []))}")
    assert r.status_code == 200
    assert "faqs" in r.json()
    assert len(r.json()["faqs"]) == 7
    print("    PASS\n")

    # --- 5. Authenticated AI reply (cascade mocked to Gemini) ---
    print("[5] Authenticated AI reply via cascade (Gemini mocked)")
    _clear_cache()
    user = User.objects.create_user(username="smoke-user", password="Pass!2024")
    client.force_login(user)
    with patch.object(GeminiProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GeminiProvider, "chat", classmethod(lambda cls, **kw: ProviderResult(
             text="Multi-provider AI reply", provider="gemini", model="gemini-2.0-flash", latency_ms=100,
         ))):
        r = client.post(
            "/chatbot/message/",
            data=json.dumps({"message": "Tell me about skin lesions", "language": "en"}),
            content_type="application/json",
        )
    print(f"    status={r.status_code}, authed={r.json().get('authed')}, scope={r.json().get('scope')}, provider={r.json().get('provider')}")
    print(f"    reply: {r.json()['reply']!r}")
    assert r.status_code == 200
    assert r.json()["authed"] is True
    assert r.json()["scope"] == "private"
    assert r.json()["provider"] == "gemini"
    assert r.json()["reply"] == "Multi-provider AI reply"
    print("    PASS\n")

    # --- 6. Authenticated user clicking FAQ button still works ---
    print("[6] Authenticated FAQ button click returns canned answer")
    _clear_cache()
    r = client.post(
        "/chatbot/message/",
        data=json.dumps({"faq_id": "disclaimer", "language": "en"}),
        content_type="application/json",
    )
    print(f"    status={r.status_code}, authed={r.json().get('authed')}, faq_id={r.json().get('faq_id')}")
    assert r.status_code == 200
    assert r.json()["authed"] is True
    assert r.json()["faq_id"] == "disclaimer"
    assert "No" in r.json()["reply"] or "not" in r.json()["reply"].lower()
    print("    PASS\n")

    # --- 7. /chatbot/history/ requires login ---
    print("[7] /chatbot/history/ requires login")
    _clear_cache()
    anon = Client()
    r = anon.get("/chatbot/history/")
    print(f"    status={r.status_code} (302 = redirect to login)")
    assert r.status_code == 302
    assert "/accounts/login" in r.url or "login" in r.url
    print("    PASS\n")

    # --- 8. /chatbot/history/ works for authenticated user ---
    print("[8] /chatbot/history/ works for authenticated user")
    _clear_cache()
    r = client.get("/chatbot/history/")
    print(f"    status={r.status_code}, messages={r.json().get('messages')}")
    assert r.status_code == 200
    assert "messages" in r.json()
    print("    PASS\n")

    # --- 9. /chatbot/providers/ shows provider health ---
    print("[9] /chatbot/providers/ shows provider health")
    _clear_cache()
    r = client.get("/chatbot/providers/")
    print(f"    status={r.status_code}")
    print(f"    order: {r.json().get('order')}")
    print(f"    any_configured: {r.json().get('any_configured')}")
    for p in r.json().get("providers", []):
        print(f"      {p['name']}: configured={p['configured']}, cooldown={p['cooldown']}")
    assert r.status_code == 200
    assert r.json()["order"] == ["gemini", "groq", "openrouter"]
    print("    PASS\n")

    # --- 10. /chatbot/usage/ requires staff ---
    print("[10] /chatbot/usage/ requires staff access")
    _clear_cache()
    r = client.get("/chatbot/usage/")
    print(f"    status={r.status_code} (403 for non-staff)")
    assert r.status_code == 403
    print("    PASS\n")

    print("=== All HTTP smoke tests passed ===")
    runner.teardown_databases(old_config)


if __name__ == "__main__":
    main()
