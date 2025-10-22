# supabase_repo.py
import os
import time
import pandas as pd
import streamlit as st
from supabase import create_client

REQUIRED = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE", "BUCKET_NAME"]

# ★ インスタンスに紐づかないトップレベル関数に変更（selfを受けない）
@st.cache_resource
def get_supabase_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_ROLE"]
    return create_client(url, key)

class Repo:
    """Supabase接続・Storage・DB CRUDを1か所に集約。app.pyからはこれだけ使えばOK。"""

    def __init__(self):
        self._assert_secrets()
        self.bucket = st.secrets["BUCKET_NAME"]
        # ★ ここでトップレベル関数を呼ぶ（selfを渡さない）
        self.cli = get_supabase_client()

    @staticmethod
    def _assert_secrets():
        missing = [k for k in REQUIRED if k not in st.secrets]
        if missing:
            st.error(f"secrets.toml に不足: {', '.join(missing)}")
            st.stop()

    # ---------- Storage (Public) ----------
    def upload_image_public(self, file, prefix: str) -> str | None:
        if not file:
            return None
        ext = os.path.splitext(file.name)[1].lower() or ".png"
        path = f"{self._slug(prefix)}-{int(time.time())}{ext}"
        self.cli.storage.from_(self.bucket).upload(path, file.read(), {"content-type": file.type})
        return self.cli.storage.from_(self.bucket).get_public_url(path)

    # ---------- DB: places ----------
    def fetch_places_df(self) -> pd.DataFrame:
        res = self.cli.table("places").select("*").execute()
        df = pd.DataFrame(res.data or [])
        need = ["id","name","location","rain_ok","duration_min","parking","satisfaction","hours_json","image_url","notes"]
        for c in need:
            if c not in df.columns:
                df[c] = pd.Series(dtype="object")
        return df

    def insert_place(self, row: dict):
        self.cli.table("places").insert(row).execute()

    # ---------- DB: events ----------
    def fetch_events_df(self) -> pd.DataFrame:
        res = self.cli.table("events").select("*").execute()
        df = pd.DataFrame(res.data or [])
        need = ["id","title","location","rain_ok","duration_min","parking","satisfaction","start_dt","end_dt","image_url","notes"]
        for c in need:
            if c not in df.columns:
                df[c] = pd.Series(dtype="object")
        return df

    def insert_event(self, row: dict):
        self.cli.table("events").insert(row).execute()

    # ---------- util ----------
    @staticmethod
    def _slug(text: str) -> str:
        import re
        text = (text or "").strip().lower()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_-]+", "-", text)
        text = re.sub(r"^-+|-+$", "", text)
        return text or "item"
