"""Streamlit interface for the fake follower detector."""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from predict_core import (
    load_artifacts, predict_account, verdict_label, build_feature_frame,
    RAW_FEATURES, RAW_LABELS, FEATURE_COLS,
)

# Paths resolve relative to this file so the app runs from any working directory
HERE = Path(__file__).parent

st.set_page_config(page_title="TrustLens - Fake Follower Detection",
                   page_icon="🛡️", layout="wide")

REAL_GREEN = "#16a34a"
FAKE_RED = "#dc2626"


@st.cache_resource
def get_model():
    return load_artifacts()


@st.cache_data
def get_meta():
    with open(HERE / "artifacts" / "meta.json") as f:
        return json.load(f)


@st.cache_data
def get_importance():
    return pd.read_csv(HERE / "artifacts" / "feature_importance.csv")


@st.cache_data
def get_master():
    return pd.read_csv(HERE / "master_dataset.csv")


try:
    model, scaler, thresholds = get_model()
    meta = get_meta()
    MODEL_READY = True
except Exception as e:
    MODEL_READY = False
    MODEL_ERR = str(e)


def gauge(prob_fake: float):
    """Semicircular real/fake gauge."""
    fig, ax = plt.subplots(figsize=(4.2, 2.3), subplot_kw={"aspect": "equal"})
    fig.patch.set_alpha(0)
    ax.axis("off")
    theta = np.linspace(np.pi, 0, 200)
    for i in range(len(theta) - 1):
        frac = i / len(theta)
        color = plt.cm.RdYlGn_r(frac)
        ax.plot([np.cos(theta[i]), np.cos(theta[i + 1])],
                [np.sin(theta[i]), np.sin(theta[i + 1])],
                color=color, lw=16, solid_capstyle="butt")
    ang = np.pi * (1 - prob_fake)
    ax.plot([0, 0.82 * np.cos(ang)], [0, 0.82 * np.sin(ang)],
            color="#111", lw=3, zorder=5)
    ax.add_patch(plt.Circle((0, 0), 0.05, color="#111", zorder=6))
    ax.text(-1, -0.18, "Real", ha="center", color=REAL_GREEN, fontweight="bold")
    ax.text(1, -0.18, "Fake", ha="center", color=FAKE_RED, fontweight="bold")
    ax.text(0, -0.35, f"{prob_fake:.0%} fake", ha="center", fontsize=13,
            fontweight="bold")
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.45, 1.1)
    return fig


def importance_chart(imp: pd.DataFrame, top=10):
    imp = imp.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6, 4))
    fig.patch.set_alpha(0)
    ax.barh(imp["feature"], imp["importance"], color="#2563eb")
    ax.set_xlabel("Importance (XGBoost gain)")
    ax.set_title(f"Top {top} features driving the classification")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    return fig


def render_results(raw: dict, summary: dict | None):
    _, prob_fake, feats = predict_account(raw, model, scaler, thresholds)
    v = verdict_label(prob_fake)
    verdict, color, confidence = v["text"], v["color"], v["confidence"]

    left, right = st.columns([1, 1])
    with left:
        if summary:
            pic = summary.get("profile_pic_url")
            cols = st.columns([1, 3])
            if pic:
                try:
                    cols[0].image(pic, width=90)
                except Exception:
                    pass
            badge = " ✅" if summary.get("verified") else ""
            cols[1].markdown(f"### @{summary.get('username','')}{badge}")
            cols[1].markdown(f"**{summary.get('full_name','')}**")
            if summary.get("biography"):
                cols[1].caption(summary["biography"])
        st.markdown("#### Extracted features")
        show = pd.DataFrame({
            "Attribute": [RAW_LABELS[k] for k in RAW_FEATURES],
            "Value": [
                ("Yes" if raw[k] else "No") if k in ("profile_pic", "private")
                else (f"{raw[k]:.3f}" if k == "username_digit_ratio" else f"{raw[k]:,}")
                for k in RAW_FEATURES
            ],
        })
        st.dataframe(show, hide_index=True, width="stretch")

    with right:
        st.markdown(
            f"<div style='padding:18px;border-radius:12px;background:{color}22;"
            f"border:2px solid {color};text-align:center'>"
            f"<div style='font-size:12px;letter-spacing:1px;color:#666'>TRUSTLENS VERDICT</div>"
            f"<div style='font-size:30px;font-weight:800;color:{color}'>{verdict}</div>"
            f"<div style='font-size:15px;margin-top:4px'>Model confidence "
            f"<b>{confidence:.1%}</b></div></div>",
            unsafe_allow_html=True,
        )
        st.pyplot(gauge(prob_fake), width="stretch")
        if v["band"] == "uncertain":
            st.info("Confidence below 60% - flagged for manual review "
                    "rather than a hard verdict.")

    st.divider()
    st.markdown("#### Comparison with dataset averages")
    _why_table(raw)


def _why_table(raw: dict):
    """Account values next to the per-class averages."""
    m = get_master()
    real = m[m["fake"] == 0]
    fake = m[m["fake"] == 1]
    rows = []
    for k in RAW_FEATURES:
        rows.append({
            "Attribute": RAW_LABELS[k],
            "This account": (f"{raw[k]:.3f}" if k == "username_digit_ratio"
                             else f"{raw[k]:,}"),
            "Typical REAL": f"{real[k].mean():.2f}",
            "Typical FAKE": f"{fake[k].mean():.2f}",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("The model uses all 18 engineered features; this table shows the 7 "
               "raw inputs against the per-class averages.")


st.sidebar.title("🛡️ TrustLens")
st.sidebar.caption("Fake Follower Detection module")

if MODEL_READY:
    st.sidebar.metric("Model", meta["model"])
    st.sidebar.metric("Test accuracy", f"{meta['test_accuracy']:.1%}")
    st.sidebar.metric("F1-macro", f"{meta['test_f1_macro']:.3f}")
    st.sidebar.metric("Training accounts", f"{meta['n_accounts']:,}")
else:
    st.sidebar.error("Model not trained yet.\nRun: python train_and_save.py")

st.sidebar.divider()
# token: environment variable, then Streamlit secrets, then manual entry
env_token = os.environ.get("APIFY_API_TOKEN", "")
if not env_token:
    try:
        env_token = st.secrets.get("APIFY_API_TOKEN", "")
    except Exception:
        env_token = ""
if env_token:
    st.sidebar.success("Apify token loaded from environment ✅")
    token = env_token
else:
    st.sidebar.warning("No APIFY_API_TOKEN in environment.")
    token = st.sidebar.text_input("Paste Apify token (optional)", type="password")
if token:
    os.environ["APIFY_API_TOKEN"] = token


st.title("Fake Follower / Bot Account Detection")
st.markdown("Enter any **public Instagram username**. TrustLens scrapes it live via "
            "Apify, extracts 7 account features, and classifies it **Real or Fake** "
            "using an XGBoost model trained on two merged datasets.")

if not MODEL_READY:
    st.error(f"{MODEL_ERR}\n\nRun `python train_and_save.py` and refresh.")
    st.stop()

tab_check, tab_model = st.tabs(["🔎 Check an account", "📊 How the model works"])

with tab_check:
    c1, c2 = st.columns([3, 1])
    username = c1.text_input("Instagram username", value="ali.ahmad.r8",
                             placeholder="e.g. ali.ahmad.r8",
                             help="Username, @username, or a full profile URL "
                                  "like https://www.instagram.com/ali.ahmad.r8/")
    c2.write("")
    c2.write("")
    go = c2.button("🔍 Analyze", type="primary", width="stretch")

    with st.expander("No token / no internet? Enter the 7 values manually (offline)"):
        with st.form("manual"):
            mc = st.columns(4)
            m_pic = mc[0].selectbox("Profile picture", ["Yes", "No"])
            m_priv = mc[1].selectbox("Private", ["No", "Yes"])
            m_digit = mc[2].number_input("Username digit ratio", 0.0, 1.0, 0.0, 0.01)
            m_bio = mc[3].number_input("Bio length", 0, 5000, 0)
            mc2 = st.columns(3)
            m_posts = mc2[0].number_input("Posts", 0, 10_000_000, 0)
            m_followers = mc2[1].number_input("Followers", 0, 1_000_000_000, 0)
            m_follows = mc2[2].number_input("Following", 0, 1_000_000_000, 0)
            manual_go = st.form_submit_button("Classify manually", type="secondary")

    if go and username.strip():
        from apify_scraper import scrape_profile, profile_to_raw_features, profile_summary
        with st.spinner(f"Scraping @{username} via Apify... (10-40s on first run)"):
            try:
                profile = scrape_profile(username)
                raw = profile_to_raw_features(profile)
                summary = profile_summary(profile)
                st.success(f"Fetched @{summary['username']} successfully.")
                render_results(raw, summary)
            except Exception as e:
                st.error(f"Scrape failed: {e}")
                st.info("Use the manual entry box above to run the demo offline.")

    if manual_go:
        raw = {
            "profile_pic": 1 if m_pic == "Yes" else 0,
            "username_digit_ratio": float(m_digit),
            "description_length": int(m_bio),
            "private": 1 if m_priv == "Yes" else 0,
            "posts_count": int(m_posts),
            "followers_count": int(m_followers),
            "follows_count": int(m_follows),
        }
        render_results(raw, None)

with tab_model:
    st.subheader("The dataset")
    m = get_master()
    d1, d2, d3 = st.columns(3)
    d1.metric("Total accounts", f"{len(m):,}")
    d2.metric("Real", f"{(m['fake'] == 0).sum():,}")
    d3.metric("Fake", f"{(m['fake'] == 1).sum():,}")
    st.markdown("Built by merging **InstaFake** (Akyon & Kalfaoglu) and the "
                "**IFSG / Goyal** Instagram datasets down to 7 shared attributes.")
    st.bar_chart(m["source_dataset"].value_counts())

    st.subheader("Which attributes decide Real vs Fake?")
    ca, cb = st.columns([1, 1])
    with ca:
        st.pyplot(importance_chart(get_importance()), width="stretch")
    with cb:
        real, fake = m[m["fake"] == 0], m[m["fake"] == 1]
        comp = pd.DataFrame({
            "Attribute": [RAW_LABELS[k] for k in RAW_FEATURES],
            "Avg REAL": [round(real[k].mean(), 2) for k in RAW_FEATURES],
            "Avg FAKE": [round(fake[k].mean(), 2) for k in RAW_FEATURES],
        })
        st.dataframe(comp, hide_index=True, width="stretch")
        st.caption("Fake accounts typically follow far more people, have far fewer "
                   "followers, fewer posts, shorter bios, and more digits in the username.")

    st.subheader("Model performance (held-out test set)")
    p1, p2, p3 = st.columns(3)
    p1.metric("XGBoost accuracy", f"{meta['test_accuracy']:.1%}")
    p2.metric("XGBoost F1-macro", f"{meta['test_f1_macro']:.3f}")
    p3.metric("Random Forest acc.", f"{meta.get('rf_test_accuracy', 0):.1%}")
