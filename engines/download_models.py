"""모델 파일 내려받기 — install.py 가 엔진 가상환경에서 자동으로 실행합니다. (약 7~9GB)

이미 받은 파일은 건너뛰므로, 중간에 끊겨도 다시 실행하면 이어서 받습니다.
모든 모델은 상업적 사용이 허용된 라이선스입니다 (README 의 '사용한 공개 모델' 참고).
"""
import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

HERE = Path(__file__).resolve().parent
MUSE = HERE / "MuseTalk"
M = MUSE / "models"

# (저장소, 파일, 저장 폴더)
FILES = [
    ("TMElyralab/MuseTalk", "musetalkV15/musetalk.json", M),
    ("TMElyralab/MuseTalk", "musetalkV15/unet.pth", M),
    ("stabilityai/sd-vae-ft-mse", "config.json", M / "sd-vae"),
    ("stabilityai/sd-vae-ft-mse", "diffusion_pytorch_model.bin", M / "sd-vae"),
    ("openai/whisper-tiny", "config.json", M / "whisper"),
    ("openai/whisper-tiny", "pytorch_model.bin", M / "whisper"),
    ("openai/whisper-tiny", "preprocessor_config.json", M / "whisper"),
    ("yzd-v/DWPose", "dw-ll_ucoco_384.onnx", M / "dwpose"),
    ("ManyOtherFunctions/face-parse-bisent", "79999_iter.pth", M / "face-parse-bisent"),
    ("ManyOtherFunctions/face-parse-bisent", "resnet18-5c106cde.pth", M / "face-parse-bisent"),
]
S3FD_URL = "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth"
S3FD_PATH = MUSE / "musetalk" / "utils" / "face_detection" / "detection" / "sfd" / "s3fd.pth"
TTS = {"0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base"}


def pick_tts(choice):
    """auto: 그래픽카드 메모리 12GB 이상(RTX 4080 등)이면 고품질 1.7B, 아니면 0.6B"""
    if choice in TTS:
        return [choice]
    if choice == "both":
        return ["0.6B", "1.7B"]
    try:
        import torch
        vram = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3 if torch.cuda.is_available() else 0
    except Exception:
        vram = 0
    print(f"그래픽카드 메모리: {vram:.1f}GB → 목소리 모델 {'1.7B (고품질)' if vram >= 12 else '0.6B'}")
    return ["1.7B"] if vram >= 12 else ["0.6B"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tts", default="auto", choices=["auto", "0.6B", "1.7B", "both"])
    a = ap.parse_args()
    if not (MUSE / "musetalk").exists():
        sys.exit("MuseTalk 코드가 없습니다. install.py 를 먼저 실행해 주세요.")
    total = len(FILES) + 2
    for n, (repo, name, folder) in enumerate(FILES, 1):
        target = folder / name
        if target.exists() and target.stat().st_size > 0:
            print(f"[{n}/{total}] 이미 있음: {target.relative_to(HERE)}")
            continue
        print(f"[{n}/{total}] 내려받는 중: {repo} / {name}", flush=True)
        folder.mkdir(parents=True, exist_ok=True)
        hf_hub_download(repo_id=repo, filename=name, local_dir=str(folder))

    n = len(FILES) + 1
    if not S3FD_PATH.exists():
        print(f"[{n}/{total}] 내려받는 중: 얼굴 찾기 모델 (s3fd)", flush=True)
        tmp = S3FD_PATH.with_suffix(".part")
        with urllib.request.urlopen(S3FD_URL, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.rename(S3FD_PATH)
    else:
        print(f"[{n}/{total}] 이미 있음: s3fd")

    for size in pick_tts(a.tts):
        repo = TTS[size]
        print(f"[{total}/{total}] 내려받는 중: 목소리 모델 {repo} ({'약 4.5GB' if size == '1.7B' else '약 2.5GB'})", flush=True)
        snapshot_download(repo_id=repo, local_dir=str(HERE / "models" / repo.split("/")[1]))
    print("모델을 모두 받았습니다.")


if __name__ == "__main__":
    main()
