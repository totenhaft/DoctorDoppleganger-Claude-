"""SQLite 데이터베이스 (data/app.db 파일 하나).

초보자 메모:
- SQLite 는 따로 설치할 필요가 없는 파일형 데이터베이스입니다.
- 이 파일을 지우면 계정·원고·영상 기록이 모두 사라지니, 백업은 data 폴더째로 하세요.
"""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

from .config import DB_PATH, DEFAULT_LANGUAGES

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    username     TEXT PRIMARY KEY,
    pw_hash      TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'staff',      -- operator(운영자) / staff(담당자)
    status       TEXT NOT NULL DEFAULT 'pending',    -- pending(첫 로그인 전) / active / disabled
    failed_count INTEGER NOT NULL DEFAULT 0,
    locked       INTEGER NOT NULL DEFAULT 0,
    must_change  INTEGER NOT NULL DEFAULT 1,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scripts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    language   TEXT NOT NULL,
    steps      TEXT NOT NULL,                 -- JSON [{title, body}]
    reviewed   INTEGER NOT NULL DEFAULT 1,    -- 기계번역은 0 (검수 전)
    source     TEXT NOT NULL DEFAULT 'manual',
    created_by TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS avatars (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,                -- video / photo
    src_path    TEXT NOT NULL,                -- 올린 원본
    norm_path   TEXT,                         -- 25fps·최대 20초·1080 이하로 맞춘 파일
    preview_path TEXT,
    orientation TEXT,                         -- landscape / portrait
    width       INTEGER,
    height      INTEGER,
    prep_dir    TEXT,                         -- 입모양 준비 자료 폴더
    status      TEXT NOT NULL,                -- pending / preparing / ready / unprepared / failed
    progress    REAL,
    message     TEXT,
    error       TEXT,
    created_by  TEXT,
    created_at  REAL NOT NULL,
    prepared_at REAL
);
CREATE TABLE IF NOT EXISTS voices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    language   TEXT NOT NULL,
    ref_path   TEXT NOT NULL,                 -- 24kHz 모노 wav
    ref_text   TEXT NOT NULL,                 -- 녹음할 때 읽은 문장 (정확할수록 좋음)
    seconds    REAL,
    created_by TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS videos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    script_id       INTEGER,
    script_snapshot TEXT NOT NULL,            -- 만들 때의 원고 JSON (원고가 바뀌어도 영상은 그대로)
    language        TEXT NOT NULL,
    avatar_id       TEXT NOT NULL,            -- 아바타 번호 또는 demo-landscape 같은 연습용 이름
    avatar_name     TEXT,
    avatar_preview  TEXT,
    voice_id        TEXT,
    aspect          TEXT NOT NULL,            -- '16:9' / '9:16'
    background      TEXT,                     -- JSON 또는 NULL
    style           TEXT NOT NULL,            -- 자막 표시 설정 JSON
    demo            INTEGER NOT NULL DEFAULT 0,
    voice_mode      TEXT NOT NULL DEFAULT 'silent',  -- clone(목소리 흉내) / recording(직접 녹음) / silent(소리 없음, 연습)
    voice_db_id     INTEGER,
    recordings      TEXT,                     -- 직접 녹음: 단계별 파일 경로 JSON
    lipsync         INTEGER NOT NULL DEFAULT 1,
    audio_path      TEXT,
    progress        REAL,
    status          TEXT NOT NULL,            -- queued / voice / lipsync / compose / done / failed / cancelled
    message         TEXT,
    error           TEXT,
    heygen_video_id TEXT,                     -- (이전 버전에서 쓰던 칸, 지금은 안 씀)
    raw_path        TEXT,
    final_path      TEXT,
    thumb_path      TEXT,
    subtitle_srt    TEXT,
    timings         TEXT,
    duration        REAL,
    parent_id       INTEGER,                  -- 꾸미기 바꾸기로 만든 경우 원래 영상 id
    share_slug      TEXT UNIQUE,
    share_enabled   INTEGER NOT NULL DEFAULT 0,
    reviewed        INTEGER NOT NULL DEFAULT 1,
    created_by      TEXT,
    created_at      REAL NOT NULL,
    started_at      REAL,
    finished_at     REAL
);
"""


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    """with db() as c: c.execute(...)  — 끝나면 자동 저장(commit)."""
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


NEW_VIDEO_COLUMNS = {
    "voice_mode": "TEXT NOT NULL DEFAULT 'silent'", "voice_db_id": "INTEGER", "recordings": "TEXT",
    "lipsync": "INTEGER NOT NULL DEFAULT 1", "audio_path": "TEXT", "progress": "REAL",
}


def init_db():
    with db() as c:
        c.executescript(SCHEMA)
        # 이전 버전 데이터베이스에 새 칸 추가
        have = {r["name"] for r in c.execute("PRAGMA table_info(videos)").fetchall()}
        for col, decl in NEW_VIDEO_COLUMNS.items():
            if col not in have:
                c.execute(f"ALTER TABLE videos ADD COLUMN {col} {decl}")


def row(r):
    return dict(r) if r is not None else None


def rows(rs):
    return [dict(r) for r in rs]


def now():
    return time.time()


# ---------------- 설정 ----------------
DEFAULT_STYLE = {
    # 표시 항목
    "show_title": True,          # 왼쪽 위: 병원명 · 영상 제목
    "show_step_title": True,     # 단계 배지
    "speech_caption": True,      # 하단 말 자막
    "step_caption": False,       # 말 자막을 끈 경우, 단계 첫 문장을 박스로 고정 표시
    "caption_mode": "auto",      # auto(말과 매칭) / manual(글자 수 지정)
    "min_chars": 10,
    "max_chars": 25,
    "caption_align": "center",   # left / center / right
    "title_pos": "left",
    "step_pos": "right",
    "show_logo": True,
    "logo_pos": "right",         # left / right (아래쪽)
    "caption_offset": 0,         # 하단 자막 세로 위치 조정 (%; +면 위로)
    "badge_offset": 0,           # 상단 제목/배지 세로 위치 조정 (%; +면 아래로)
    # 글자
    "font": "default",
    "font_size": 54,             # 1080px 기준 픽셀
    "font_weight": 700,
    "line_height": 1.25,
    # 색·외곽선
    "color": "#FFFFFF",
    "opacity": 100,
    "stroke_width": 3,
    "stroke_color": "#111111",
    "shadow": False,
    "shadow_color": "#000000",
    "shadow_opacity": 60,
    "shadow_angle": 45,
    "shadow_distance": 4,
    "shadow_blur": 6,
    # 자막 박스
    "box": False,
    "box_color": "#000000",
    "box_opacity": 55,
}

DEFAULT_SHARE = {
    "heading": "",
    "message": "영상을 끝까지 보시고, 궁금한 점은 병원에 문의해 주세요.",
    "ai_notice": "이 영상의 안내자는 생성형 인공지능(AI)으로 만든 가상 인물입니다. "
                 "영상 내용은 의료진이 검토한 일반 안내이며 개인별 진료를 대신하지 않습니다.",
}

DEFAULT_SETTINGS = {
    "org_name": "연세솔안과",
    "org_name_i18n": {},
    "org_desc": "",
    "default_language": "ko-KR",
    "languages": DEFAULT_LANGUAGES,
    "caption_style": DEFAULT_STYLE,
    "share_page": DEFAULT_SHARE,
    "tts_precision": "float32",   # float32(정확) / float16(빠름·메모리 적게)
    "lipsync_batch": 8,           # 입모양을 한 번에 몇 장씩 그릴지 (메모리 부족하면 줄이기)
    "logo_file": "",
    "anthropic_api_key": "",
    "claude_model": "",
    "public_base_url": "",   # 환자에게 보낼 공유 링크의 앞부분 (예: https://video.우리병원.com)
}

SECRET_KEYS = {"anthropic_api_key"}


def get_setting(key):
    with db() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if r is None:
        v = DEFAULT_SETTINGS.get(key)
        return json.loads(json.dumps(v))  # 기본값 복사본
    return json.loads(r["value"])


def set_setting(key, value):
    with db() as c:
        c.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def merged_style(overrides=None):
    """병원 기본 자막 설정 + (영상별로 바꾼 값)"""
    base = dict(DEFAULT_STYLE)
    base.update(get_setting("caption_style") or {})
    if overrides:
        base.update({k: v for k, v in overrides.items() if k in DEFAULT_STYLE})
    return base
