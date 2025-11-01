# supabase_repo.py
REPO_VERSION = "no-crash-when-secrets-missing-2025-11-01"

import os
import time
import pandas as pd

# streamlit はオプション扱い（無くても動く）
try:
    import streamlit as st  # type: ignore
except Exception:
    st = None  # st.secretsを参照しなくても済むようにする

# 新SDK想定
from supabase import create_client, Client  # pip: supabase>=2.6

REQUIRED_BASE = ["SUPABASE_URL", "BUCKET_NAME"]

def _get_secret(name: str) -> str | None:
    """st.secrets -> env の順で探す。st自体が無いケースもOK。"""
    val = None
    if st is not None:
        try:
            # st.secrets は dict 互換
            val = st.secrets.get(name)  # type: ignore[attr-defined]
        except Exception:
            val = None
    return val or os.getenv(name)

def _get_key() -> str | None:
    """公開は ANON 推奨。ローカルは SERVICE_ROLE でも可。どちらかあればOK。"""
    return _get_secret("SUPABASE_ANON_KEY") or _get_secret("SUPABASE_SERVICE_ROLE")

def is_supabase_configured() -> bool:
    """URL と BUCKET と（ANON or SERVICE_ROLE）の有無だけ確認。"""
    if not _get_secret("SUPABASE_URL"): return False
    if not _get_secret("BUCKET_NAME"): return False
    if not _get_key(): return False
    return True

def _assert_or_raise():
    missing = []
    if not _get_secret("SUPABASE_URL"): missing.append("SUPABASE_URL")
    if not _get_secret("BUCKET_NAME"): missing.append("BUCKET_NAME")
    if not _get_key(): missing.append("SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE")
    if missing:
        # ❗ここは raise のみにする（st.error/st.stop は使わない）
        raise RuntimeError("Missing secrets: " + ", ".join(missing))

# クライアントは必要になった時にだけ作る
def get_supabase_client() -> Client:
    _assert_or_raise()
    url = _get_secret("SUPABASE_URL")
    key = _get_key()
    return create_client(url, key)  # type: ignore[arg-type]

class Repo:
    """Supabase接続・Storage・DB CRUD."""
    def __init__(self):
        _assert_or_raise()
        self.bucket = _get_secret("BUCKET_NAME")
        self.cli = get_supabase_client()

    # ---------- Storage ----------
    def upload_image_public(self, file, prefix: str) -> str | None:
        if not file:
            return None
        ext = os.path.splitext(file.name)[1].lower() or ".png"
        path = f"{self._slug(prefix)}-{int(time.time())}{ext}"
        data = file.read()
        self.cli.storage.from_(self.bucket).upload(
            path=path,
            file=data,
            file_options={"contentType": getattr(file, "type", "application/octet-stream"), "upsert": True},
        )
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
