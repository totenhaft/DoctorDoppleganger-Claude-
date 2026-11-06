"""영상 엔진(목소리·입모양)을 실행하고 상태를 확인합니다.

엔진은 무거운 패키지(PyTorch 등)가 많아 웹 프로그램과 다른 파이썬 환경(engines/.venv)에 설치합니다.
웹 프로그램은 그 환경의 파이썬으로 engines/*.py 를 따로 실행하고, 출력되는 줄을 읽어 진행 상황을 압니다.
  PROGRESS 0.42 설명   → 진행률
  RESULT {...}         → 결과
  ERROR 설명           → 실패 이유
"""
import json
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

from .config import ENGINE_DIR, ENGINE_PY, LOG_DIR, TTS_MODELS

GPU_LOCK = threading.Lock()   # 그래픽카드는 한 번에 한 작업만 (메모리 부족 방지)


class EngineError(Exception):
    pass


_status = {"t": 0, "data": None}


def installed():
    return ENGINE_PY.exists()


def status(force=False):
    """{installed, cuda, gpu, vram_gb, tts_ready, lipsync_ready, errors}"""
    if not force and _status["data"] and time.time() - _status["t"] < 120:
        return _status["data"]
    if not installed():
        data = {"installed": False, "cuda": False, "tts_ready": False, "lipsync_ready": False,
                "errors": ["엔진이 아직 설치되지 않았습니다. install_engines.bat 을 실행해 주세요."]}
    else:
        try:
            p = subprocess.run([str(ENGINE_PY), str(ENGINE_DIR / "check.py")], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=180, creationflags=_flags(), env=_env())
            line = [l for l in (p.stdout or "").splitlines() if l.strip().startswith("{")]
            data = json.loads(line[-1]) if line else {"errors": [(p.stderr or "점검 실패")[-400:]]}
        except Exception as e:
            data = {"errors": [f"엔진 점검 실패: {e}"]}
        data["installed"] = True
        data.setdefault("tts_ready", False)
        data.setdefault("lipsync_ready", False)
        data.setdefault("cuda", False)
    _status.update(t=time.time(), data=data)
    return data


def _has_model(size):
    return (TTS_MODELS[size] / "config.json").exists()


def tts_model_dir():
    """설정과 그래픽카드 메모리에 맞는 목소리 모델 폴더 (12GB 이상이면 고품질 1.7B 우선)"""
    from .db import get_setting
    choice = get_setting("tts_model") or "auto"
    vram = status().get("vram_gb") or 0
    if choice == "1.7B" or (choice == "auto" and vram >= 12):
        order = ["1.7B", "0.6B"]
    else:
        order = ["0.6B", "1.7B"]
    for size in order:
        if _has_model(size):
            return TTS_MODELS[size]
    return TTS_MODELS[order[0]]


def tts_precision():
    from .db import get_setting
    return get_setting("tts_precision") or "auto"


def lipsync_batch():
    from .db import get_setting
    b = int(get_setting("lipsync_batch") or 0)
    if b > 0:
        return b
    return 16 if (status().get("vram_gb") or 0) >= 12 else 8


def _flags():
    return 0x08000000 if platform.system() == "Windows" else 0  # 윈도우에서 검은 창 안 뜨게


def _env():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("HF_HUB_OFFLINE", "1")          # 설치 뒤에는 인터넷 없이 동작
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    return env


def run(script, args, on_progress=None, log_name="engine"):
    """엔진 스크립트를 실행하고 RESULT 를 돌려줍니다. 실패하면 EngineError."""
    if not installed():
        raise EngineError("영상 엔진이 설치되지 않았습니다. 프로그램 폴더의 install_engines.bat 을 먼저 실행해 주세요.")
    cmd = [str(ENGINE_PY), str(ENGINE_DIR / script), *[str(a) for a in args]]
    log_path = LOG_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{log_name}.log"
    result, error, tail = None, None, []
    with GPU_LOCK, open(log_path, "w", encoding="utf-8") as log:
        log.write(" ".join(cmd) + "\n")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace", creationflags=_flags(), env=_env(), cwd=str(ENGINE_DIR))
        for line in p.stdout:
            log.write(line)
            line = line.rstrip("\n")
            if line.startswith("PROGRESS "):
                parts = line.split(" ", 2)
                try:
                    frac = float(parts[1])
                except ValueError:
                    frac = None
                if on_progress and frac is not None:
                    on_progress(frac, parts[2] if len(parts) > 2 else "")
            elif line.startswith("RESULT "):
                try:
                    result = json.loads(line[7:])
                except json.JSONDecodeError:
                    pass
            elif line.startswith("ERROR "):
                error = line[6:]
            else:
                tail = (tail + [line])[-15:]
        code = p.wait()
    if code != 0 or result is None:
        msg = error or "엔진이 예상과 다르게 끝났습니다."
        detail = "\n".join(t for t in tail if t.strip())[-800:]
        raise EngineError(f"{msg}\n(자세한 기록: {log_path.name})" + (f"\n{detail}" if detail and not error else ""))
    return result
