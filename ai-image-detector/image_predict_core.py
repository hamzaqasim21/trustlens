"""
TrustLens Module 6.7 - AI-generated profile image detector.

Inference path: face gate -> frozen CLIP -> trained probe -> three-band verdict.
Kept in one place so training and serving use identical preprocessing.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from PIL import Image

ARTIFACT_DIR = Path(__file__).parent / "artifacts"

DEFAULT_MIN_CONFIDENCE = 0.60
MIN_FACE_PX = 48
CROP_MARGIN = 0.35          # must match the crop used during training


@dataclass
class ImageVerdict:
    band: str                 # real | fake | uncertain | not_applicable
    verdict: str
    face_detected: bool
    confidence: float | None
    p_ai: float | None
    image_risk: int | None    # 0-100, consumed by the Trust Score Engine
    reason: str
    face_size: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def verdict_from_probability(p_ai: float, min_confidence: float = DEFAULT_MIN_CONFIDENCE):
    conf = max(p_ai, 1.0 - p_ai)
    if conf < min_confidence:
        return "uncertain", "UNCERTAIN - needs review", conf
    if p_ai >= 0.5:
        return "fake", "AI-GENERATED FACE", conf
    return "real", "REAL PHOTO", conf


# --------------------------------------------------------------------------- artifacts
def load_meta(artifact_dir: Path | str = ARTIFACT_DIR) -> dict:
    p = Path(artifact_dir) / "image_meta.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Copy the trained artifacts into artifacts/.")
    with open(p) as f:
        return json.load(f)


def load_probe(artifact_dir: Path | str = ARTIFACT_DIR):
    """Returns (probe, scaler, meta)."""
    import joblib
    d = Path(artifact_dir)
    for fn in ("image_probe.pkl", "image_scaler.pkl", "image_meta.json"):
        if not (d / fn).exists():
            raise FileNotFoundError(f"Missing {fn} in {d}. Copy the trained artifacts there.")
    return joblib.load(d / "image_probe.pkl"), joblib.load(d / "image_scaler.pkl"), load_meta(d)


# --------------------------------------------------------------------------- encoder
def load_clip(arch: str = "ViT-B-32", pretrained: str = "openai"):
    """Load CLIP and keep only the vision tower - the text tower is unused here and
    dropping it roughly halves memory."""
    import torch
    import open_clip

    torch.set_num_threads(1)
    model, _, preprocess = open_clip.create_model_and_transforms(arch, pretrained=pretrained)
    model.eval()
    visual = model.visual
    del model
    for p in visual.parameters():
        p.requires_grad_(False)
    return visual, preprocess


def embed_image(pil_img: Image.Image, visual, preprocess) -> np.ndarray:
    import torch
    with torch.no_grad():
        x = preprocess(pil_img.convert("RGB")).unsqueeze(0)
        f = visual(x)
        f = f / f.norm(dim=-1, keepdim=True)
    return f.cpu().numpy().astype("float32")


# --------------------------------------------------------------------------- face gate
_FACE_STATE: dict = {"backend": None, "detector": None, "notes": []}


def _haar_cascade_path() -> str | None:
    local = Path(__file__).parent / "assets" / "haarcascade_frontalface_default.xml"
    if local.exists():
        return str(local)
    try:
        import cv2
        p = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if os.path.exists(p):
            return p
    except Exception:
        pass
    return None


def _init_face_detector():
    """MTCNN if available (matches training), otherwise the OpenCV cascade."""
    if _FACE_STATE["backend"] is not None:
        return
    notes = _FACE_STATE["notes"]

    try:
        from facenet_pytorch import MTCNN
        _FACE_STATE["detector"] = MTCNN(keep_all=True, device="cpu")
        _FACE_STATE["backend"] = "mtcnn"
        return
    except Exception as e:
        notes.append(f"MTCNN unavailable ({type(e).__name__}: {e})")

    try:
        import cv2
        if not hasattr(cv2, "CascadeClassifier"):
            raise RuntimeError(f"OpenCV {cv2.__version__} has no CascadeClassifier; "
                               "requires opencv-python-headless<5")
        path = _haar_cascade_path()
        if path is None:
            raise RuntimeError("haarcascade XML not found")
        clf = cv2.CascadeClassifier(path)
        if clf.empty():
            raise RuntimeError(f"cascade failed to load: {path}")
        _FACE_STATE["detector"] = clf
        _FACE_STATE["backend"] = "opencv"
        return
    except Exception as e:
        notes.append(f"OpenCV cascade unavailable ({type(e).__name__}: {e})")

    _FACE_STATE["backend"] = "none"
    raise RuntimeError("No face detector available:\n  - " + "\n  - ".join(notes))


def face_backend() -> str:
    try:
        _init_face_detector()
        return _FACE_STATE["backend"]
    except Exception:
        return "unavailable"


def face_backend_notes() -> list[str]:
    return list(_FACE_STATE["notes"])


def detect_face(img: Image.Image, min_prob: float = 0.90):
    """Largest face as (x1, y1, x2, y2), or None."""
    _init_face_detector()
    img = img.convert("RGB")
    det = _FACE_STATE["detector"]

    if _FACE_STATE["backend"] == "mtcnn":
        boxes, probs = det.detect(img)
        if boxes is None:
            return None
        keep = [(b, p) for b, p in zip(boxes, probs) if p is not None and p >= min_prob]
        if not keep:
            return None
        b, _ = max(keep, key=lambda t: (t[0][2] - t[0][0]) * (t[0][3] - t[0][1]))
        return tuple(float(v) for v in b)

    import cv2
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    faces = det.detectMultiScale(gray, 1.1, 5)
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return (float(x), float(y), float(x + w), float(y + h))


def crop_face(img: Image.Image, box, margin: float = CROP_MARGIN) -> Image.Image:
    img = img.convert("RGB")
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    mx, my = w * margin, h * margin
    return img.crop((max(0, int(x1 - mx)), max(0, int(y1 - my)),
                     min(img.width, int(x2 + mx)), min(img.height, int(y2 + my))))


# --------------------------------------------------------------------------- module
def analyze_image(img: Image.Image | str, probe, scaler, visual, preprocess,
                  min_confidence: float = DEFAULT_MIN_CONFIDENCE,
                  min_face_px: int = MIN_FACE_PX) -> ImageVerdict:
    if isinstance(img, (str, os.PathLike)):
        img = Image.open(img)
    img = img.convert("RGB")

    box = detect_face(img)
    if box is None:
        return ImageVerdict(
            band="not_applicable", verdict="NOT A PERSON - no human face found",
            face_detected=False, confidence=None, p_ai=None, image_risk=None,
            reason="The picture is not a human face, so the AI-face check does not apply.")

    face = crop_face(img, box)
    if min(face.size) < min_face_px:
        return ImageVerdict(
            band="uncertain", verdict="UNCERTAIN - face too small to judge",
            face_detected=True, confidence=None, p_ai=None, image_risk=None,
            face_size=f"{face.size[0]}x{face.size[1]}",
            reason=f"Detected face is {face.size[0]}x{face.size[1]} px, below the "
                   f"{min_face_px}px floor.")

    feat = embed_image(face, visual, preprocess)
    p_ai = float(probe.predict_proba(scaler.transform(feat))[0][1])
    band, text, conf = verdict_from_probability(p_ai, min_confidence)

    return ImageVerdict(
        band=band, verdict=text, face_detected=True,
        confidence=round(conf, 4), p_ai=round(p_ai, 4),
        image_risk=int(round(p_ai * 100)),
        face_size=f"{face.size[0]}x{face.size[1]}",
        reason=f"Face detected and analysed. P(AI-generated) = {p_ai:.1%}.")


def killswitch_triggered(v: ImageVerdict, threshold: float = 0.90) -> bool:
    return v.band == "fake" and v.confidence is not None and v.confidence >= threshold
