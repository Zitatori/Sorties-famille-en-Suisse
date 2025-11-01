# supabase_repo.py  ←これに置き換え
REPO_VERSION = "relaxed-keys-2025-10-30"

import os
import time
import pandas as pd
import streamlit as st
from supabase import create_client, Client

REQUIRED_BASE = ["SUPABASE_URL", "BUCKET_NAME"]
def _get_secret(name: str):
    try:
        val = st.secrets.get(name)  # st.secrets が無い環境もあるので try
    except Exception:
        val = None
    return val or os.getenv(name)

def _get_key():
    # どちらか片方あればOK（公開はANON推奨）
    return _get_secret("SUPABASE_ANON_KEY") or _get_secret("SUPABASE_SERVICE_ROLE")

def _assert_secrets_or_raise():
    missing = [k for k in REQUIRED_BASE if not _get_secret(k)]
    if not _get_key():
        missing.append("SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE")
    if missing:
        # 旧版の st.error/st.stop は廃止。必ず raise にする（アプリ側で捕捉して優しく落とす）
        raise RuntimeError("Missing secrets: " + ", ".join(missing))

@st.cache_resource
def get_supabase_client() -> Client:
    _assert_secrets_or_raise()
    url = _get_secret("SUPABASE_URL")
    key = _get_key()
    return create_client(url, key)  # type: ignore[arg-type]

class Repo:
    def __init__(self):
        _assert_secrets_or_raise()
        self.bucket = _get_secret("BUCKET_NAME")
        self.cli = get_supabase_client()

    def upload_image_public(self, file, prefix: str) -> str | None:
        if not file:
            return None
        import os
        ext = os.path.splitext(file.name)[1].lower() or ".png"
        path = f"{self._slug(prefix)}-{int(time.time())}{ext}"
        data = file.read()
        self.cli.storage.from_(self.bucket).upload(
            path=path,
            file=data,
            file_options={"contentType": file.type, "upsert": True},
        )
        return self.cli.storage.from_(self.bucket).get_public_url(path)

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

    @staticmethod
    def _slug(text: str) -> str:
        import re
        text = (text or "").strip().lower()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_-]+", "-", text)
        text = re.sub(r"^-+|-+$", "", text)
        return text or "item"
