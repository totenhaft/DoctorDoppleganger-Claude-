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
VIDEO_DIR = DATA_DIR / "videos"      # 음성·입모양 영상 + 완성본 mp4
WORK_DIR = DATA_DIR / "work"         # 만드는 동안 잠깐 쓰는 파일
LOGO_DIR = DATA_DIR / "logo"
FONT_DIR = DATA_DIR / "fonts"        # 병원이 올린 글꼴
AVATAR_DIR = DATA_DIR / "avatars"    # 원장님 영상·사진과 입모양 준비 자료
VOICE_DIR = DATA_DIR / "voices"      # 원장님 목소리 녹음 (목소리 흉내용)
REC_DIR = DATA_DIR / "recordings"    # 영상마다 직접 녹음해 올린 음성
LOG_DIR = DATA_DIR / "logs"          # 엔진 실행 기록 (문제 생겼을 때 확인용)

for d in (DATA_DIR, VIDEO_DIR, WORK_DIR, LOGO_DIR, FONT_DIR, AVATAR_DIR, VOICE_DIR, REC_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---- 영상 엔진 (engines/ 폴더, install_engines.bat 으로 설치) ----
ENGINE_DIR = Path(os.environ.get("DD_ENGINE_DIR", BASE_DIR / "engines"))  # 보통은 바꿀 필요 없음
ENGINE_PY = ENGINE_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
TTS_MODEL_DIR = ENGINE_DIR / "models" / "Qwen3-TTS-12Hz-0.6B-Base"
AVATAR_MAX_SECONDS = 20   # 아바타 원본 영상은 앞 20초만 씀 (앞뒤로 반복 재생)
PAUSE_SENTENCE = 0.35     # 문장 사이 쉬는 시간(초)
PAUSE_STEP = 0.7          # 단계 사이 쉬는 시간(초)

# ---- 원고 제한 (사이트와 같은 규칙) ----
MAX_STEPS = 4
MAX_TITLE = 60            # 스크립트 제목 최대 글자
MAX_STEP_TITLE = 40       # 단계 제목 최대 글자
MAX_SCRIPT_CHARS = 5000   # 단계를 합친 원고 최대 글자
MAX_VIDEO_SECONDS = 300   # 예상 길이가 이보다 길면 만들지 않음 (너무 긴 영상 방지)

# 말하는 속도 추정치 (공백 제외 글자/초). 실제와 다를 수 있는 '추정'입니다.
CHARS_PER_SEC = {"ko": 5.5, "ja": 6.5, "zh": 4.5, "default": 14.0}

# ---- 로그인 ----
SESSION_HOURS = 12
MAX_LOGIN_FAILS = 5
MIN_PASSWORD_LEN = 10

# ---- 단계 색 (영상 배지와 화면에 같이 씀) ----
STEP_COLORS = ["#2F6BFF", "#12A37F", "#E07B16", "#8B5CF6"]

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"

# 화면에서 고를 수 있는 기본 언어 목록 (설정에서 더하거나 뺄 수 있음)
DEFAULT_LANGUAGES = [
    {"code": "ko-KR", "label": "한국어"},
    {"code": "en-US", "label": "English"},
    {"code": "zh-CN", "label": "中文"},
    {"code": "ja-JP", "label": "日本語"},
]
# tts: 목소리 엔진(Qwen3-TTS)이 쓰는 언어 이름. None 이면 목소리 흉내가 안 되고 '직접 녹음'만 가능
LANGUAGE_PRESETS = [
    {"code": "ko-KR", "label": "한국어", "tts": "Korean"},
    {"code": "en-US", "label": "English", "tts": "English"},
    {"code": "zh-CN", "label": "中文", "tts": "Chinese"},
    {"code": "ja-JP", "label": "日本語", "tts": "Japanese"},
    {"code": "ru-RU", "label": "Русский", "tts": "Russian"},
    {"code": "es-ES", "label": "Español", "tts": "Spanish"},
    {"code": "fr-FR", "label": "Français", "tts": "French"},
    {"code": "de-DE", "label": "Deutsch", "tts": "German"},
    {"code": "pt-BR", "label": "Português", "tts": "Portuguese"},
    {"code": "it-IT", "label": "Italiano", "tts": "Italian"},
    {"code": "vi-VN", "label": "Tiếng Việt", "tts": None},
    {"code": "mn-MN", "label": "Монгол", "tts": None},
    {"code": "th-TH", "label": "ไทย", "tts": None},
    {"code": "id-ID", "label": "Bahasa Indonesia", "tts": None},
    {"code": "uz-UZ", "label": "Oʻzbek", "tts": None},
]


def tts_language(code):
    for p in LANGUAGE_PRESETS:
        if p["code"] == code:
            return p["tts"]
    return None
