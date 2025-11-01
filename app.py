# app.py
import streamlit as st
st.set_page_config(page_title="Sorties famille en Suisse", page_icon="👨‍👩‍👧", layout="wide")

import os, io, json
from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd
from PIL import Image

# ===== Supabase 設定（存在すれば使う） =====
USE_SUPABASE = False
repo = None
try:
    import supabase_repo as S
    st.sidebar.write("Repo version:", getattr(S, "REPO_VERSION", "unknown"))
    st.sidebar.write("Repo file:", getattr(S, "__file__", "unknown"))
    if S.is_supabase_configured():
        try:
            repo = S.Repo()
            USE_SUPABASE = True
        except Exception as e:
            USE_SUPABASE = False
    else:
        USE_SUPABASE = False
except Exception:
    USE_SUPABASE = False

# ===== 定数 =====
APP_TZ = ZoneInfo("Europe/Zurich")
DATA_DIR = "data"
IMG_DIR = os.path.join(DATA_DIR, "images")
PLACES_CSV = os.path.join(DATA_DIR, "places.csv")
EVENTS_CSV = os.path.join(DATA_DIR, "events.csv")

ASSETS_DIR = "assets"
BACKGROUND_IMAGE_PATH = os.path.join(ASSETS_DIR, "bg.png")
HERO_IMAGE_PATH = os.path.join(ASSETS_DIR, "hero.png")

PARKING_OPTIONS = ["Facile", "Moyen", "Difficile"]
WEEKDAYS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

PLACE_COLS = [
    "id", "name", "location", "rain_ok", "duration_min",
    "parking", "satisfaction", "hours_json", "image_path", "notes"
]
EVENT_COLS = [
    "id", "title", "location", "rain_ok", "duration_min",
    "parking", "satisfaction", "start_dt", "end_dt", "image_path", "notes"
]

# ===== ユーティリティ =====
def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

def slugify(text: str) -> str:
    import re
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "item"

def load_df(csv_path: str, cols: list) -> pd.DataFrame:
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            df = pd.DataFrame(columns=cols)
    else:
        df = pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = pd.Series(dtype="object")
    return df

def save_df(df: pd.DataFrame, csv_path: str):
    df.to_csv(csv_path, index=False)

def load_image_if_exists(path_or_url: str | None):
    if not path_or_url:
        return None
    if isinstance(path_or_url, str) and path_or_url.startswith(("http://", "https://")):
        return path_or_url
    if os.path.exists(path_or_url):
        try:
            return Image.open(path_or_url)
        except Exception:
            return None
    return None

def now_local():
    return datetime.now(APP_TZ)

def display_star_rating(stars: int | None) -> str:
    try:
        s = int(stars)
    except Exception:
        s = 0
    s = max(0, min(5, s))
    return "★" * s + "☆" * (5 - s)

def set_background():
    img = load_image_if_exists(BACKGROUND_IMAGE_PATH)
    if not img or isinstance(img, str):
        return
    import base64
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    css = f"""
    <style>
      .stApp {{
        background-image: url("data:image/png;base64,{b64}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
      }}
      .card {{
        background-color: rgba(255,255,255,0.88);
        border-radius: 16px;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def hero_header():
    hero = load_image_if_exists(HERO_IMAGE_PATH)
    if hero is not None:
        st.image(hero, use_container_width=True)

def save_uploaded_image(upload, prefix: str) -> str | None:
    if not upload:
        return None
    # Supabase優先
    if USE_SUPABASE and repo is not None:
        try:
            url = repo.upload_image_public(upload, prefix=prefix)
            if url:
                return url
        except Exception:
            pass
    # ローカル保存
    ext = os.path.splitext(upload.name)[1].lower() or ".png"
    fname = f"{slugify(prefix)}-{int(datetime.now().timestamp())}{ext}"
    path = os.path.join(IMG_DIR, fname)
    try:
        with open(path, "wb") as f:
            f.write(upload.read())
        return path
    except Exception:
        return None

def place_card(row):
    img_obj = load_image_if_exists(row.get("image_path"))
    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        cols = st.columns([1, 2])
        with cols[0]:
            if img_obj is None:
                st.write("*(Aucune image)*")
            else:
                st.image(img_obj, use_container_width=True)
        with cols[1]:
            st.subheader(row.get("name") or "Sans nom")
            st.write(f"**Lieu :** {row.get('location','')}")
            st.write(f"**Pluie :** {'Oui' if bool(row.get('rain_ok')) else 'Non'}")
            st.write(f"**Durée :** {int(row.get('duration_min') or 0)} min")
            st.write(f"**Parking :** {row.get('parking','')}")
            st.write(f"**Satisfaction :** {display_star_rating(int(row.get('satisfaction') or 0))}")
            if row.get("notes"):
                st.caption(row["notes"])
        st.markdown("</div>", unsafe_allow_html=True)

def event_card(row):
    img_obj = load_image_if_exists(row.get("image_path"))
    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        cols = st.columns([1, 2])
        with cols[0]:
            if img_obj is None:
                st.write("*(Aucune image)*")
            else:
                st.image(img_obj, use_container_width=True)
        with cols[1]:
            st.subheader(row.get("title") or "Événement")
            st.write(f"**Lieu :** {row.get('location','')}")
            st.write(f"**Pluie :** {'Oui' if bool(row.get('rain_ok')) else 'Non'}")
            st.write(f"**Durée :** {int(row.get('duration_min') or 0)} min")
            st.write(f"**Parking :** {row.get('parking','')}")
            st.write(f"**Satisfaction :** {display_star_rating(int(row.get('satisfaction') or 0))}")
            st.write(f"**Période :** {row.get('start_dt','')} → {row.get('end_dt','')}")
            if row.get("notes"):
                st.caption(row["notes"])
        st.markdown("</div>", unsafe_allow_html=True)

# ===== メイン =====
def main():
    ensure_dirs()
    set_background()
    hero_header()

    st.title("🇨🇭 Sorties famille en Suisse")
    st.caption(
        f"Heure locale : {now_local().strftime('%Y-%m-%d %H:%M')} • "
        f"Mode: {'Supabase' if USE_SUPABASE else 'Local'}"
    )

    places = load_df(PLACES_CSV, PLACE_COLS)
    events = load_df(EVENTS_CSV, EVENT_COLS)

    tab1, tab2, tab3 = st.tabs(["Explorer", "Ajouter (Lieu)", "Événements"])

    with tab1:
        st.subheader("Lieux pour enfants")
        if places.empty:
            st.info("Aucun lieu enregistré.")
        else:
            for _, row in places.iterrows():
                place_card(row)

    with tab2:
        st.subheader("Ajouter un nouveau lieu")
        with st.form("add_place", clear_on_submit=True):
            name = st.text_input("Nom du lieu *")
            location = st.text_input("Lieu (ville/région) *")
            rain_ok = st.selectbox("Pluie OK", ["Oui", "Non"]) == "Oui"
            duration_min = st.number_input("Durée (min)", 0, 300, 10, 5)
            parking = st.selectbox("Parking", PARKING_OPTIONS)
            satisfaction = st.slider("Satisfaction (1-5)", 1, 5, 4)
            upload = st.file_uploader("Image", type=["png","jpg","jpeg"])
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Enregistrer")
            if submitted:
                if not name or not location:
                    st.error("Nom et Lieu sont requis.")
                else:
                    img_path = save_uploaded_image(upload, prefix=name)
                    new = {
                        "id": f"{slugify(name)}-{int(datetime.now().timestamp())}",
                        "name": name,
                        "location": location,
                        "rain_ok": bool(rain_ok),
                        "duration_min": int(duration_min),
                        "parking": parking,
                        "satisfaction": int(satisfaction),
                        "image_path": img_path,
                        "notes": notes,
                    }
                    places = pd.concat([places, pd.DataFrame([new])], ignore_index=True)
                    save_df(places, PLACES_CSV)
                    st.success("Lieu ajouté !")
                    st.experimental_rerun()

    with tab3:
        st.subheader("Événements")
        with st.form("add_event", clear_on_submit=True):
            title = st.text_input("Titre *")
            location_e = st.text_input("Lieu (ville/région) *")
            start_date = st.date_input("Début", value=datetime.now(APP_TZ).date())
            end_date = st.date_input("Fin", value=datetime.now(APP_TZ).date())
            duration_min = st.number_input("Durée (min)", 0, 600, 60, 5)
            parking = st.selectbox("Parking", PARKING_OPTIONS)
            satisfaction = st.slider("Satisfaction (1-5)", 1, 5, 4)
            upload = st.file_uploader("Image", type=["png","jpg","jpeg"], key="event_image")
            notes = st.text_area("Notes", key="event_notes")
            submitted = st.form_submit_button("Enregistrer")
            if submitted:
                if not title or not location_e:
                    st.error("Titre et Lieu sont requis.")
                else:
                    img_path = save_uploaded_image(upload, prefix=title)
                    new_e = {
                        "id": f"{slugify(title)}-{int(datetime.now().timestamp())}",
                        "title": title,
                        "location": location_e,
                        "rain_ok": True,
                        "duration_min": int(duration_min),
                        "parking": parking,
                        "satisfaction": int(satisfaction),
                        "start_dt": str(start_date),
                        "end_dt": str(end_date),
                        "image_path": img_path,
                        "notes": notes,
                    }
                    events = pd.concat([events, pd.DataFrame([new_e])], ignore_index=True)
                    save_df(events, EVENTS_CSV)
                    st.success("Événement ajouté !")
                    st.experimental_rerun()

        if events.empty:
            st.info("Aucun événement enregistré.")
        else:
            for _, row in events.iterrows():
                event_card(row)

if __name__ == "__main__":
    main()
