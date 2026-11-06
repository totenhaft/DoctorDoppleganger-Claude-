"""프로그램 전체에서 쓰는 경로와 고정값.

초보자 메모:
- 실제 데이터(원고, 영상, 계정, API 키)는 모두 data/ 폴더에 저장됩니다.
- data/ 폴더는 .gitignore 에 들어 있어서 GitHub 에 올라가지 않습니다.
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DD_DATA_DIR", BASE_DIR / "data"))
STATIC_DIR = BASE_DIR / "static"

DB_PATH = DATA_DIR / "app.db"
VIDEO_DIR = DATA_DIR / "videos"      # 아바타 원본 + 완성본 mp4
WORK_DIR = DATA_DIR / "work"         # 합성할 때 잠깐 쓰는 그림 파일
LOGO_DIR = DATA_DIR / "logo"
FONT_DIR = DATA_DIR / "fonts"        # 병원이 올린 글꼴

for d in (DATA_DIR, VIDEO_DIR, WORK_DIR, LOGO_DIR, FONT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---- 원고 제한 (사이트와 같은 규칙) ----
MAX_STEPS = 4
MAX_TITLE = 60            # 스크립트 제목 최대 글자
MAX_STEP_TITLE = 40       # 단계 제목 최대 글자
MAX_SCRIPT_CHARS = 5000   # 단계를 합친 원고 최대 글자
MAX_VIDEO_SECONDS = 300   # 예상 길이가 이보다 길면 만들지 않음 (비용 보호)

# 말하는 속도 추정치 (공백 제외 글자/초). 실제와 다를 수 있는 '추정'입니다.
CHARS_PER_SEC = {"ko": 5.5, "ja": 6.5, "zh": 4.5, "default": 14.0}

# ---- 로그인 ----
SESSION_HOURS = 12
MAX_LOGIN_FAILS = 5
MIN_PASSWORD_LEN = 10

# ---- 단계 색 (영상 배지와 화면에 같이 씀) ----
STEP_COLORS = ["#2F6BFF", "#12A37F", "#E07B16", "#8B5CF6"]

HEYGEN_BASE = "https://api.heygen.com"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"

# 화면에서 고를 수 있는 기본 언어 목록 (설정에서 더하거나 뺄 수 있음)
DEFAULT_LANGUAGES = [
    {"code": "ko-KR", "label": "한국어"},
    {"code": "en-US", "label": "English"},
    {"code": "zh-CN", "label": "中文"},
    {"code": "ja-JP", "label": "日本語"},
]
LANGUAGE_PRESETS = [
    {"code": "ko-KR", "label": "한국어", "heygen": "Korean"},
    {"code": "en-US", "label": "English", "heygen": "English"},
    {"code": "zh-CN", "label": "中文", "heygen": "Chinese"},
    {"code": "ja-JP", "label": "日本語", "heygen": "Japanese"},
    {"code": "vi-VN", "label": "Tiếng Việt", "heygen": "Vietnamese"},
    {"code": "mn-MN", "label": "Монгол", "heygen": "Mongolian"},
    {"code": "ru-RU", "label": "Русский", "heygen": "Russian"},
    {"code": "th-TH", "label": "ไทย", "heygen": "Thai"},
    {"code": "id-ID", "label": "Bahasa Indonesia", "heygen": "Indonesian"},
    {"code": "es-ES", "label": "Español", "heygen": "Spanish"},
    {"code": "fr-FR", "label": "Français", "heygen": "French"},
    {"code": "de-DE", "label": "Deutsch", "heygen": "German"},
    {"code": "ar-SA", "label": "العربية", "heygen": "Arabic"},
    {"code": "uz-UZ", "label": "Oʻzbek", "heygen": "Uzbek"},
    {"code": "kk-KZ", "label": "Қазақ", "heygen": "Kazakh"},
]
