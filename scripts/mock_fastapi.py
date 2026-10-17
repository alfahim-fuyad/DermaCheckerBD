"""Minimal FastAPI mock server — drop-in stand-in for the real ResNet50
service while you develop the Django integration locally.

Run:
    pip install "fastapi<0.115" uvicorn python-multipart pillow
    python scripts/mock_fastapi.py
    # -> listens on http://127.0.0.1:8000

Then in Django's .env:
    ML_MODEL_BACKEND=api
    AI_API_URL=http://127.0.0.1:8000

It returns deterministic, plausible-looking probabilities that follow
the EXACT same JSON shape the real service is expected to return:

    {
      "success": true,
      "predicted_class": "nv",
      "confidence": 0.6210,
      "probabilities": {"akiec": 0.05, "bcc": 0.05, ..., "nv": 0.62, ...}
    }

The probabilities are seeded from the uploaded file's first 1024 bytes —
the same file always produces the same prediction. This is enough to
verify the Django -> FastAPI round-trip end-to-end without needing the
actual Keras model.

NOTE: Install ``fastapi<0.115`` if you hit ``ForwardRef('UploadFile')``
resolution errors — newer FastAPI + pydantic 2.14 combos are sometimes
picky about the UploadFile type adapter.
"""

import hashlib
import io
import math

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image

CLASS_ORDER = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]

app = FastAPI(title="DermaCheckerBD Mock AI", version="0.1.0")

# Allow local Django (any port) to call us during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001", "http://127.0.0.1:8001",
                   "http://localhost:8002", "http://127.0.0.1:8002"],
    allow_methods=["POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    # Validate that it's actually an image (same check the real FastAPI
    # server would do in production). Use PIL — the real server should too,
    # so corrupt PNGs are rejected before the model sees them.
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Not a valid image: {exc}") from exc

    # Deterministic seed: hash first 1024 bytes so the same upload always
    # produces the same prediction.
    h = hashlib.sha1(raw[:1024]).digest()
    seeds = list(h[:7])
    base = [-0.4, -0.2, -0.1, -1.2, 0.2, 1.6, -1.0]  # bias toward 'nv'
    noise = [(b - 128) / 128.0 for b in seeds]
    logits = [b + n * 1.2 for b, n in zip(base, noise)]

    # Softmax with temperature 0.6 (peaks the distribution a bit).
    t = 0.6
    z = [x / t for x in logits]
    m = max(z)
    exps = [math.exp(x - m) for x in z]
    total = sum(exps)
    probs = [e / total for e in exps]

    probabilities = {k: round(float(p), 4) for k, p in zip(CLASS_ORDER, probs)}
    top_idx = max(range(len(probs)), key=lambda i: probs[i])
    return JSONResponse({
        "success": True,
        "predicted_class": CLASS_ORDER[top_idx],
        "confidence": probabilities[CLASS_ORDER[top_idx]],
        "probabilities": probabilities,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
