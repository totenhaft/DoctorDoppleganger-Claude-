"""영상 엔진(목소리·입모양) 설치 — 처음 한 번만 실행합니다. 약 10~12GB 를 내려받고 20~60분 걸립니다.

    python engines/install.py          (그래픽카드용, 권장)
    python engines/install.py --cpu    (그래픽카드 없이 시험만 — 영상 하나에 몇 시간 걸릴 수 있음)

하는 일
 1. engines/.venv 에 엔진 전용 파이썬 환경을 만듭니다 (웹 프로그램과 패키지가 섞이지 않게).
 2. PyTorch(CUDA 12.4) 와 목소리·입모양 패키지를 설치합니다.
 3. MuseTalk 코드(MIT)를 받아 engines/MuseTalk 에 둡니다.
 4. 모델 파일을 받습니다 (download_models.py).
 5. 제대로 설치됐는지 점검합니다 (check.py).
중간에 끊겨도 다시 실행하면 이미 된 단계는 건너뜁니다.
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
MUSE = HERE / "MuseTalk"
MUSE_COMMIT = "0a89dec45a0192b824e3cf4daf96c239440c5ed8"   # 2025-09 기준, 시험한 버전으로 고정
MUSE_ZIP = f"https://github.com/TMElyralab/MuseTalk/archive/{MUSE_COMMIT}.zip"
TORCH = ["torch==2.6.0", "torchvision==0.21.0", "torchaudio==2.6.0"]


def py():
    return str(VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))


def run(cmd, **kw):
    print("  >", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode != 0:
        raise SystemExit(f"\n[실패] 위 명령이 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요. (코드 {r.returncode})")


def step(n, msg):
    print(f"\n========== {n}/5 {msg} ==========", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", action="store_true", help="그래픽카드 없이 설치 (매우 느림, 시험용)")
    ap.add_argument("--skip-models", action="store_true")
    ap.add_argument("--tts", default="auto", choices=["auto", "0.6B", "1.7B", "both"],
                    help="목소리 모델 크기 (auto: 그래픽카드 12GB 이상이면 1.7B)")
    a = ap.parse_args()

    if sys.version_info < (3, 10) or sys.version_info >= (3, 14):
        sys.exit("파이썬 3.10~3.13 이 필요합니다. README 의 1단계를 확인해 주세요.")
    gpu = shutil.which("nvidia-smi")
    if not a.cpu:
        if not gpu:
            sys.exit("NVIDIA 그래픽카드 드라이버(nvidia-smi)를 찾지 못했습니다.\n"
                     "그래픽카드 드라이버를 최신으로 설치한 뒤 다시 실행하거나, 시험만 하려면 --cpu 를 붙여 실행하세요.")
        subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])

    step(1, "엔진 전용 파이썬 환경 만들기")
    if not Path(py()).exists():
        run([sys.executable, "-m", "venv", VENV])
    else:
        print("  이미 있음 — 건너뜀")
    run([py(), "-m", "pip", "install", "--upgrade", "pip", "-q"])

    step(2, "PyTorch 와 엔진 패키지 설치 (몇 GB, 시간이 걸립니다)")
    index = "https://download.pytorch.org/whl/cpu" if a.cpu else "https://download.pytorch.org/whl/cu124"
    run([py(), "-m", "pip", "install", *TORCH, "--index-url", index])
    run([py(), "-m", "pip", "install", "-r", HERE / "requirements.txt"])

    step(3, "MuseTalk 코드 받기")
    if (MUSE / "musetalk").exists():
        print("  이미 있음 — 건너뜀")
    else:
        print(f"  {MUSE_ZIP}", flush=True)
        with urllib.request.urlopen(MUSE_ZIP, timeout=300) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(HERE)
        src = HERE / f"MuseTalk-{MUSE_COMMIT}"
        if MUSE.exists():
            shutil.rmtree(MUSE)
        src.rename(MUSE)

    step(4, "모델 파일 받기 (약 6~7GB)")
    if a.skip_models:
        print("  --skip-models — 건너뜀")
    else:
        run([py(), HERE / "download_models.py", "--tts", a.tts])

    step(5, "설치 점검")
    out = subprocess.run([py(), HERE / "check.py"], capture_output=True, text=True, encoding="utf-8")
    print(out.stdout or out.stderr)
    print("\n설치를 마쳤습니다. 웹 프로그램의 [설정 → 영상 엔진]에서 「다시 확인」을 누르면 상태가 바뀝니다.")


if __name__ == "__main__":
    main()
