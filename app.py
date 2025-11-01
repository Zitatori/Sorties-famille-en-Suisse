# app.py  — 完全差し替え版
# ポイント:
# - set_page_config を最優先
# - Supabaseは任意（使えれば使う）。未設定でもアプリは起動する
# - 画像は URL / ローカルの両対応
# - カードのHTMLを開始/終了セットに統一
# - “今開いてる/期間中”等の判定・フィルタは既存ロジックを踏襲

import streamlit as st
st.set_page_config(page_title="Sorties famille en Suisse", page_icon="👨‍👩‍👧", layout="wide")

import os
import io
import json
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional

import pandas as pd
from PIL import Image

# ====== Supabase（任意） ======
USE_SUPABASE = False
repo = None
try:
    from supabase_repo import Repo
    try:
        repo = Repo()          # supabase_repo.py 側は “ANON or SERVICE_ROLE のどちらか”でOK化済み
        USE_SUPABASE = True
    except Exception as e:
        USE_SUPABASE = False   # Secrets未設定など → ローカル保存モードへ
except Exception:
    USE_SUPABASE = False       # モジュール自体が無い → ローカル保存モード

# ====== 定数 ======
APP_TZ = ZoneInfo("Europe/Zurich")
DATA_DIR = "data"
IMG_DIR = os.path.join(DATA_DIR, "images")
PLACES_CSV = os.path.join(DATA_DIR, "places.csv")
EVENTS_CSV = os.path.join(DATA_DIR, "events.csv")

ASSETS_DIR = "assets"
BACKGROUND_IMAGE_PATH = os.path.join(ASSETS_DIR, "bg.png")   # 任意（無ければ何もしない）
HERO_IMAGE_PATH = os.path.join(ASSETS_DIR, "hero.png")       # 任意（無ければ何もしない）

PARKING_OPTIONS = ["Facile", "Moyen", "Difficile"]
WEEKDAYS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
WEEKDAY_IDX = {name: i for i, name in enumerate(WEEKDAYS_FR)}  # 予備

PLACE_COLS = [
    "id", "name", "location", "rain_ok", "duration_min",
    "parking", "satisfaction", "hours_json", "image_path", "notes"
]
EVENT_COLS = [
    "id", "title", "location", "rain_ok", "duration_min",
    "parking", "satisfaction", "start_dt", "end_dt", "image_path", "notes"
]

# ====== ユーティリティ ======
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

def load_image_if_exists(path_or_url: Optional[str]):
    """
    画像ハンドルを返す:
      - http/httpsで始まる → URL文字列をそのまま返す（st.imageに直接渡せる）
      - ローカルパス       → PIL.Image を返す（st.imageに渡せる）
      - 無い/読めない      → None
    """
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

def time_to_str(t: Optional[time]) -> str:
    if t is None:
        return "-"
    return t.strftime("%H:%M")

def parse_time_str(s: Optional[str]) -> Optional[time]:
    if not s or pd.isna(s):
        return None
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except Exception:
        return None

def now_local():
    return datetime.now(APP_TZ)

def is_open_today_intervals(hours_json: Optional[str], dt: datetime) -> list[tuple[time, time]]:
    if not hours_json or pd.isna(hours_json):
        return []
    try:
        data = json.loads(hours_json)
    except Exception:
        return []
    weekday_fr = WEEKDAYS_FR[dt.weekday()]
    day_cfg = data.get(weekday_fr, {})
    if not day_cfg or not day_cfg.get("open", False):
        return []
    intervals = []
    for block in day_cfg.get("intervals", []):
        start = parse_time_str(block.get("start"))
        end = parse_time_str(block.get("end"))
        if start and end:
            intervals.append((start, end))
    return intervals

def is_open_now(hours_json: Optional[str]) -> bool:
    dt = now_local()
    intervals = is_open_today_intervals(hours_json, dt)
    now_t = dt.time()
    for start, end in intervals:
        if start <= now_t <= end:
            return True
    return False

def within_open_now(start_dt_str: Optional[str], end_dt_str: Optional[str]) -> bool:
    if not start_dt_str or not end_dt_str:
        return False
    try:
        start = datetime.fromisoformat(start_dt_str)
        end = datetime.fromisoformat(end_dt_str)
        if start.tzinfo is None:
            start = start.replace(tzinfo=APP_TZ)
        if end.tzinfo is None:
            end = end.replace(tzinfo=APP_TZ)
        now = now_local()
        return start <= now <= end
    except Exception:
        return False

def display_star_rating(stars: Optional[int]) -> str:
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
      .badge {{
        display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px;
        background:#eef; margin-right:6px;
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def hero_header():
    hero = load_image_if_exists(HERO_IMAGE_PATH)
    if hero is not None:
        st.image(hero, use_container_width=True)

def save_uploaded_image(upload, prefix: str) -> Optional[str]:
    """
    画像を保存:
      - Supabaseが使える → Storageにアップロードして“公開URL”を返す
      - 使えない         → ローカル data/images に保存してパスを返す
    """
    if not upload:
        return None

    # Supabase優先
    if USE_SUPABASE and repo is not None:
        try:
            url = repo.upload_image_public(upload, prefix=prefix)
            if url:
                return url  # 公開URLを保存
        except Exception:
            pass  # 失敗時はローカルへフォールバック

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

def sidebar_filters_section(suffix: str = ""):
    st.sidebar.header("Filtres" + suffix)
    q = st.sidebar.text_input("Lieu contient", key=f"q{suffix}")
    pluie = st.sidebar.selectbox("Pluie OK", ["(Tous)", "Oui", "Non"], key=f"pluie{suffix}")
    duree = st.sidebar.slider("Durée (min)", min_value=0, max_value=300, value=(0, 300), step=5, key=f"duree{suffix}")
    parking = st.sidebar.selectbox("Parking", ["(Tous)"] + PARKING_OPTIONS, key=f"park{suffix}")
    satis = st.sidebar.slider("Satisfaction minimale", min_value=0, max_value=5, value=0, key=f"satis{suffix}")
    open_now = st.sidebar.checkbox("Ouvert maintenant", key=f"open{suffix}")
    return q, pluie, duree, parking, satis, open_now

def apply_place_filters(df, q, pluie, duree, parking, satis, open_now_flag):
    out = df.copy()
    if q:
        out = out[out["location"].fillna("").str.contains(q, case=False)]
    if pluie in ["Oui", "Non"]:
        out = out[out["rain_ok"].astype(bool) == (pluie == "Oui")]
    out = out[(out["duration_min"].fillna(0).astype(int) >= duree[0]) &
              (out["duration_min"].fillna(0).astype(int) <= duree[1])]
    if parking in PARKING_OPTIONS:
        out = out[out["parking"] == parking]
    out = out[out["satisfaction"].fillna(0).astype(int) >= int(satis)]
    if open_now_flag:
        out = out[out["hours_json"].apply(is_open_now)]
    return out

def apply_event_filters(df, q, pluie, duree, parking, satis, open_now_flag):
    out = df.copy()
    if q:
        out = out[out["location"].fillna("").str.contains(q, case=False)]
    if pluie in ["Oui", "Non"]:
        out = out[out["rain_ok"].astype(bool) == (pluie == "Oui")]
    out = out[(out["duration_min"].fillna(0).astype(int) >= duree[0]) &
              (out["duration_min"].fillna(0).astype(int) <= duree[1])]
    if parking in PARKING_OPTIONS:
        out = out[out["parking"] == parking]
    out = out[out["satisfaction"].fillna(0).astype(int) >= int(satis)]
    if open_now_flag:
        out = out[out.apply(lambda r: within_open_now(r["start_dt"], r["end_dt"]), axis=1)]
    return out

def place_card(row):
    open_badge = "🟢 Ouvert maintenant" if is_open_now(row.get("hours_json")) else "⚪ Fermé"
    img_obj = load_image_if_exists(row.get("image_path"))
    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        cols = st.columns([1,2])
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
            st.write(f"**Statut :** {open_badge}")
            if row.get("notes"):
                st.caption(row["notes"])

            # Horaires（詳細）
            try:
                hours = json.loads(row.get("hours_json") or "{}")
                parts = []
                for d in WEEKDAYS_FR:
                    dc = hours.get(d, {})
                    if dc.get("open"):
                        ivs = dc.get("intervals", [])
                        iv_str = ", ".join([f'{iv.get("start","")}-{iv.get("end","")}' for iv in ivs])
                    else:
                        iv_str = "Fermé"
                    parts.append(f"**{d}** {iv_str}")
                with st.expander("Horaires détaillés"):
                    st.write("  \n".join(parts))
            except Exception:
                pass
        st.markdown('</div>', unsafe_allow_html=True)

def event_card(row):
    now_badge = "🟢 En cours" if within_open_now(row.get("start_dt"), row.get("end_dt")) else "⚪ Hors créneau"
    img_obj = load_image_if_exists(row.get("image_path"))
    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        cols = st.columns([1,2])
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
            st.write(f"**Statut :** {now_badge}")
            if row.get("notes"):
                st.caption(row["notes"])
        st.markdown('</div>', unsafe_allow_html=True)

def build_hours_input(default_json: Optional[str]):
    defaults = {}
    if default_json:
        try:
            defaults = json.loads(default_json)
        except Exception:
            defaults = {}
    out = {}
    with st.expander("Jours & horaires"):
        for d in WEEKDAYS_FR:
            dc = defaults.get(d, {})
            open_default = bool(dc.get("open", False))
            c1, c2, c3 = st.columns([1,1,1])
            with c1:
                opened = st.checkbox(f"{d} ouvert", value=open_default, key=f"open_{d}")
            start_def = None
            end_def = None
            if dc.get("intervals"):
                try:
                    start_def = parse_time_str(dc["intervals"][0].get("start"))
                    end_def = parse_time_str(dc["intervals"][0].get("end"))
                except Exception:
                    pass
            with c2:
                start_t = st.time_input(f"{d} début", value=start_def or time(9,0), key=f"start_{d}", disabled=not opened)
            with c3:
                end_t = st.time_input(f"{d} fin", value=end_def or time(18,0), key=f"end_{d}", disabled=not opened)
            if opened:
                out[d] = {
                    "open": True,
                    "intervals": [{"start": time_to_str(start_t), "end": time_to_str(end_t)}]
                }
            else:
                out[d] = {"open": False, "intervals": []}
    return json.dumps(out, ensure_ascii=False)

def safe_rerun():
    """Streamlitバージョン差吸収：rerunが無ければexperimental_rerun"""
    fn = getattr(st, "rerun", None)
    if callable(fn):
        fn()
    else:
        fn2 = getattr(st, "experimental_rerun", None)
        if callable(fn2):
            fn2()

# ====== メイン ======
def main():
    ensure_dirs()
    set_background()
    hero_header()

    # ヘッダー
    st.title("🇨🇭 Sorties famille en Suisse")
    if USE_SUPABASE:
        st.caption(f"Heure locale : {now_local().strftime('%Y-%m-%d %H:%M')}  •  Stockage: Supabase")
    else:
        st.caption(f"Heure locale : {now_local().strftime('%Y-%m-%d %H:%M')}  •  Stockage: local (CSV + images)")

    # データ読み込み
    places = load_df(PLACES_CSV, PLACE_COLS)
    events = load_df(EVENTS_CSV, EVENT_COLS)

    tab1, tab2, tab3 = st.tabs(["Explorer", "Ajouter (Lieu)", "Événements"])

    # ---- Explorer（施設） ----
    with tab1:
        q, pluie, duree, parking, satis, open_now_flag = sidebar_filters_section(suffix="_places")
        st.subheader("Lieux pour enfants")
        filtered = apply_place_filters(places, q, pluie, duree, parking, satis, open_now_flag)
        if filtered.empty:
            st.info("Aucun lieu trouvé avec ces filtres.")
        else:
            for _, row in filtered.sort_values(by=["satisfaction", "duration_min"], ascending=[False, True]).iterrows():
                place_card(row)

    # ---- Ajouter (Lieu)（施設追加）----
    with tab2:
        st.subheader("Ajouter un nouveau lieu")
        with st.form("add_place", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Nom du lieu *")
                location = st.text_input("Lieu (ville/région) *")
                rain_ok = st.selectbox("Pluie OK", ["Oui", "Non"]) == "Oui"
                duration_min = st.number_input("Durée (min)", min_value=0, max_value=300, value=10, step=5)
                parking = st.selectbox("Parking", PARKING_OPTIONS)
                satisfaction = st.slider("Satisfaction (1-5)", min_value=1, max_value=5, value=4)
            with col2:
                upload = st.file_uploader("Image (PNG/JPG)", type=["png","jpg","jpeg"])
                notes = st.text_area("Notes")

            hours_json = build_hours_input(default_json=None)
            submitted = st.form_submit_button("Enregistrer")

            if submitted:
                if not name or not location:
                    st.error("Nom et Lieu sont requis.")
                else:
                    img_path = save_uploaded_image(upload, prefix=name) if upload else None
                    new = {
                        "id": f"{slugify(name)}-{int(datetime.now().timestamp())}",
                        "name": name,
                        "location": location,
                        "rain_ok": bool(rain_ok),
                        "duration_min": int(duration_min),
                        "parking": parking,
                        "satisfaction": int(satisfaction),
                        "hours_json": hours_json,
                        "image_path": img_path,
                        "notes": notes,
                    }
                    places = pd.concat([places, pd.DataFrame([new])], ignore_index=True)
                    save_df(places, PLACES_CSV)
                    st.success("Lieu ajouté !")
                    safe_rerun()

    # ---- Événements（不定期）----
    with tab3:
        st.subheader("Événements (irréguliers)")

        with st.expander("Ajouter un événement"):
            with st.form("add_event", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    title = st.text_input("Titre *")
                    location_e = st.text_input("Lieu (ville/région) *")
                    today = now_local().date()
                    start_date = st.date_input("Début (date) *", value=today, key="ev_sd")
                    start_time = st.time_input("Début (heure) *", value=time(9, 0), key="ev_st")
                    end_date = st.date_input("Fin (date) *", value=today, key="ev_ed")
                    end_time = st.time_input("Fin (heure) *", value=time(18, 0), key="ev_et")

                with c2:
                    rain_ok_e = st.selectbox("Pluie OK", ["Oui", "Non"], key="rain_e") == "Oui"
                    duration_min_e = st.number_input("Durée (min)", min_value=0, max_value=600, value=90, step=5, key="dur_e")
                    parking_e = st.selectbox("Parking", PARKING_OPTIONS, key="park_e")
                    satisfaction_e = st.slider("Satisfaction (1-5)", min_value=1, max_value=5, value=4, key="sat_e")
                    upload_e = st.file_uploader("Image (PNG/JPG)", type=["png","jpg","jpeg"], key="up_e")
                    notes_e = st.text_area("Notes", key="notes_e")

                btn = st.form_submit_button("Enregistrer l'événement")
                if btn:
                    if not title or not location_e:
                        st.error("Titre et Lieu sont requis.")
                    else:
                        start_dt = datetime.combine(start_date, start_time).replace(tzinfo=APP_TZ)
                        end_dt = datetime.combine(end_date, end_time).replace(tzinfo=APP_TZ)
                        if end_dt < start_dt:
                            st.error("Fin doit être après Début.")
                        else:
                            img_path_e = save_uploaded_image(upload_e, prefix=title) if upload_e else None
                            new_e = {
                                "id": f"{slugify(title)}-{int(datetime.now().timestamp())}",
                                "title": title,
                                "location": location_e,
                                "rain_ok": bool(rain_ok_e),
                                "duration_min": int(duration_min_e),
                                "parking": parking_e,
                                "satisfaction": int(satisfaction_e),
                                "start_dt": start_dt.isoformat(),
                                "end_dt": end_dt.isoformat(),
                                "image_path": img_path_e,
                                "notes": notes_e,
                            }
                            events = pd.concat([events, pd.DataFrame([new_e])], ignore_index=True)
                            save_df(events, EVENTS_CSV)
                            st.success("Événement ajouté !")
                            safe_rerun()

        st.markdown("---")
        q_ev, pluie_ev, duree_ev, parking_ev, satis_ev, open_now_ev = sidebar_filters_section(suffix="_events")
        filtered_ev = apply_event_filters(events, q_ev, pluie_ev, duree_ev, parking_ev, satis_ev, open_now_ev)
        if filtered_ev.empty:
            st.info("Aucun événement correspondant.")
        else:
            for _, row in filtered_ev.sort_values(by=["start_dt"]).iterrows():
                event_card(row)

def run():
    main()

if __name__ == "__main__":
    run()
