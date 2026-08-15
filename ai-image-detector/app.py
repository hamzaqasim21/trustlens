"""TrustLens Module 6.7 - AI-generated profile image detector"""
import json

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from PIL import Image

from image_predict_core import (
    load_probe, load_clip, analyze_image, face_backend, face_backend_notes,
    detect_face, crop_face, killswitch_triggered, DEFAULT_MIN_CONFIDENCE,
)

st.set_page_config(page_title="TrustLens - AI Image Detector",
                   page_icon="🛡️", layout="wide")

GREEN, RED, AMBER, GREY = "#16a34a", "#dc2626", "#d97706", "#6b7280"
BAND_COLOR = {"real": GREEN, "fake": RED, "uncertain": AMBER, "not_applicable": GREY}


@st.cache_resource(show_spinner="Loading CLIP encoder...")
def get_model():
    probe, scaler, meta = load_probe()
    visual, preprocess = load_clip(meta.get("clip_arch", "ViT-B-32"),
                                   meta.get("clip_pretrained", "openai"))
    return probe, scaler, meta, visual, preprocess


@st.cache_data
def get_meta_only():
    from image_predict_core import load_meta
    return load_meta()


def gauge(p_ai: float):
    fig, ax = plt.subplots(figsize=(4.2, 2.3), subplot_kw={"aspect": "equal"})
    fig.patch.set_alpha(0)
    ax.axis("off")
    theta = np.linspace(np.pi, 0, 200)
    for i in range(len(theta) - 1):
        ax.plot([np.cos(theta[i]), np.cos(theta[i + 1])],
                [np.sin(theta[i]), np.sin(theta[i + 1])],
                color=plt.cm.RdYlGn_r(i / len(theta)), lw=16, solid_capstyle="butt")
    ang = np.pi * (1 - p_ai)
    ax.plot([0, 0.82 * np.cos(ang)], [0, 0.82 * np.sin(ang)], color="#111", lw=3, zorder=5)
    ax.add_patch(plt.Circle((0, 0), 0.05, color="#111", zorder=6))
    ax.text(-1, -0.18, "Real", ha="center", color=GREEN, fontweight="bold")
    ax.text(1, -0.18, "AI", ha="center", color=RED, fontweight="bold")
    ax.text(0, -0.35, f"{p_ai:.0%} AI", ha="center", fontsize=13, fontweight="bold")
    ax.set_xlim(-1.2, 1.2); ax.set_ylim(-0.45, 1.1)
    return fig


def show_verdict(v, img):
    color = BAND_COLOR[v.band]
    left, right = st.columns([1, 1])

    with left:
        st.image(img, caption="submitted image", width="stretch")
        box = detect_face(img)
        if box is not None:
            st.caption("Face passed to the classifier:")
            st.image(crop_face(img, box), width=170)

    with right:
        st.markdown(
            f"<div style='padding:18px;border-radius:12px;background:{color}22;"
            f"border:2px solid {color};text-align:center'>"
            f"<div style='font-size:12px;letter-spacing:1px;color:#666'>VERDICT</div>"
            f"<div style='font-size:26px;font-weight:800;color:{color}'>{v.verdict}</div>"
            + (f"<div style='font-size:15px;margin-top:6px'>confidence "
               f"<b>{v.confidence:.1%}</b></div>" if v.confidence is not None else "")
            + "</div>", unsafe_allow_html=True)

        if v.p_ai is not None:
            st.pyplot(gauge(v.p_ai), width="stretch")

        if v.band == "not_applicable":
            st.info("No human face found, so the AI-face check does not apply.")
        elif v.band == "uncertain":
            st.warning("Confidence below the threshold — flagged for manual review.")
        elif killswitch_triggered(v):
            st.error("Kill-switch: synthetic face detected with high confidence.")

    st.divider()
    st.markdown("#### Module output")
    st.json(v.to_dict())


st.sidebar.title("🛡️ TrustLens")
st.sidebar.caption("Module 6.7 — AI-Generated Image Detector")

try:
    meta = get_meta_only()
    ARTIFACTS_OK = True
except Exception as e:
    ARTIFACTS_OK = False
    ARTIFACT_ERR = str(e)

if ARTIFACTS_OK:
    st.sidebar.metric("Encoder", meta.get("clip_arch", "?"))
    st.sidebar.metric("Classifier", meta.get("classifier", "?"))
    exp = meta.get("experiment_A_vs_B", [])
    diff = next((r for r in exp if "DIFFUSION" in str(r.get("test set", ""))), None)
    if diff:
        st.sidebar.metric("Accuracy on diffusion", f"{diff['B acc']:.1%}")
    st.sidebar.metric("Training images", f"{meta.get('train_size', 0):,}")
    st.sidebar.divider()

    backend = face_backend()
    if backend == "mtcnn":
        st.sidebar.caption("Face detector: MTCNN")
    elif backend == "opencv":
        st.sidebar.caption("Face detector: OpenCV cascade")
    else:
        st.sidebar.error("No face detector available.")

    with st.sidebar.expander("Environment", expanded=(backend == "unavailable")):
        import sys, sklearn
        try:
            import cv2
            cv_ver = cv2.__version__
        except Exception:
            cv_ver = "not installed"
        st.caption(f"Python `{sys.version.split()[0]}`")
        st.caption(f"OpenCV `{cv_ver}`")
        st.caption(f"scikit-learn `{sklearn.__version__}`")
        for n in face_backend_notes():
            st.caption(n)
else:
    st.sidebar.error("Artifacts missing")

st.sidebar.divider()
min_conf = st.sidebar.slider("Abstain below this confidence", 0.50, 0.95,
                             float(meta.get("min_confidence", DEFAULT_MIN_CONFIDENCE))
                             if ARTIFACTS_OK else DEFAULT_MIN_CONFIDENCE, 0.01)

st.title("AI-Generated Profile Image Detection")
st.markdown("Upload a photo. The module checks whether the image contains a human face, "
            "then classifies that face as a real photograph or AI-generated.")

if not ARTIFACTS_OK:
    st.error(ARTIFACT_ERR)
    st.markdown("Place `image_probe.pkl`, `image_scaler.pkl` and `image_meta.json` "
                "in the `artifacts/` folder.")
    st.stop()

tab_check, tab_results, tab_how = st.tabs(
    ["Check an image", "Model results", "How it works"])

with tab_check:
    up = st.file_uploader(
        "Choose an image",
        type=["jpg", "jpeg", "jfif", "jpe", "png", "webp", "bmp", "tif", "tiff"],
    )

    if up is not None:
        img = Image.open(up)
        probe, scaler, meta, visual, preprocess = get_model()
        with st.spinner("Analysing..."):
            v = analyze_image(img, probe, scaler, visual, preprocess,
                              min_confidence=min_conf)
        show_verdict(v, img)

with tab_results:
    st.subheader("Effect of training-set diversity")
    st.markdown("""
Two detectors trained on the same real images and the same number of fakes. The only
difference is the diversity of the fakes.

* **Model A** — fakes from StyleGAN only
* **Model B** — fakes from GAN, diffusion and face-swap
""")
    exp = meta.get("experiment_A_vs_B", [])
    if exp:
        df = pd.DataFrame(exp)
        st.dataframe(df, hide_index=True, width="stretch")

        plot_df = df.set_index("test set")[["A acc", "B acc"]]
        plot_df.columns = ["A: GAN only", "B: mixed"]
        fig, ax = plt.subplots(figsize=(7, 3.6))
        plot_df.plot(kind="bar", ax=ax, rot=0, color=[RED, GREEN])
        ax.axhline(0.5, ls="--", c="gray", lw=1, label="_nolegend_")
        ax.text(0.02, 0.52, "chance", color="gray", fontsize=8,
                transform=ax.get_yaxis_transform())
        ax.set_ylabel("accuracy"); ax.set_ylim(0, 1.05); ax.legend(fontsize=8)
        for c in ax.containers:
            ax.bar_label(c, fmt="%.2f", fontsize=8, padding=2)
        st.pyplot(fig, width="stretch")

        d = next((r for r in exp if "DIFFUSION" in str(r["test set"])), None)
        if d:
            st.info(f"On diffusion-generated faces the GAN-only model scores "
                    f"{d['A acc']:.1%} against a 50% chance baseline, while the mixed "
                    f"model scores {d['B acc']:.1%}.")

    rob = meta.get("robustness", [])
    if rob:
        st.subheader("Accuracy vs image size")
        rdf = pd.DataFrame(rob)
        c1, c2 = st.columns([1, 1])
        c1.dataframe(rdf, hide_index=True, width="stretch")
        fig2, ax2 = plt.subplots(figsize=(5, 3))
        ax2.plot(rdf["size_px"], rdf["accuracy"], "o-")
        ax2.invert_xaxis(); ax2.set_ylim(0, 1.05); ax2.grid(alpha=.3)
        ax2.set_xlabel("image size (px)"); ax2.set_ylabel("accuracy")
        c2.pyplot(fig2, width="stretch")

    with st.expander("Limitations"):
        for lim in meta.get("known_limitations", []):
            st.markdown(f"- {lim}")

with tab_how:
    st.subheader("Pipeline")
    st.code("""image
  |
  |-- Stage 0  face gate (MTCNN)
  |      no face  -> "NOT A PERSON"
  |      face     -> crop with 0.35 margin
  |
  '-- Stage 1  frozen CLIP ViT -> probe -> REAL / AI-GENERATED / UNCERTAIN""",
            language="text")

    st.subheader("Choice of backbone")
    st.markdown("""
The backbone is a frozen CLIP Vision Transformer rather than a fine-tuned CNN. A CNN trained
on one generator learns that generator's artifacts and does not transfer to new ones, while
CLIP's pretrained features generalise to unseen generators. Only a small classifier is
trained on top.

Reference: Ojha, Li and Lee, *Towards Universal Fake Image Detectors that Generalize Across
Generative Models*, CVPR 2023.
""")

    st.subheader("Training data")
    src = meta.get("training_sources", {})
    c1, c2 = st.columns(2)
    c1.markdown("**Real**")
    for s in src.get("real", []):
        c1.markdown(f"- {s}")
    c2.markdown("**AI-generated**")
    for s in src.get("fake", []):
        c2.markdown(f"- {s}")

    st.subheader("Output format")
    st.code(json.dumps({
        "band": "fake", "verdict": "AI-GENERATED FACE", "face_detected": True,
        "confidence": 0.94, "p_ai": 0.94, "image_risk": 94,
        "face_size": "312x312", "reason": "Face detected and analysed. P(AI-generated) = 94.0%."
    }, indent=2), language="json")
    st.caption("image_risk feeds the Trust Score Engine at 10% weight; a fake verdict with "
               "confidence above 0.90 raises the kill-switch.")
