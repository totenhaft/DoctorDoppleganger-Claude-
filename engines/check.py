"""엔진 상태 점검 — 엔진 가상환경에서 실행하면 결과를 JSON 한 줄로 출력합니다.

    engines\\.venv\\Scripts\\python engines\\check.py
"""
import json
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUSE = HERE / "MuseTalk"
TTS_MODELS = {"0.6B": HERE / "models" / "Qwen3-TTS-12Hz-0.6B-Base",
              "1.7B": HERE / "models" / "Qwen3-TTS-12Hz-1.7B-Base"}

MUSE_FILES = [
    "models/musetalkV15/unet.pth", "models/musetalkV15/musetalk.json",
    "models/sd-vae/config.json", "models/whisper/config.json", "models/whisper/preprocessor_config.json",
    "models/dwpose/dw-ll_ucoco_384.onnx", "models/face-parse-bisent/79999_iter.pth",
    "models/face-parse-bisent/resnet18-5c106cde.pth",
    "musetalk/utils/face_detection/detection/sfd/s3fd.pth",
]


def main():
    out = {"python": platform.python_version(), "errors": []}
    try:
        import torch
        out["torch"] = torch.__version__
        out["cuda"] = bool(torch.cuda.is_available())
        if out["cuda"]:
            p = torch.cuda.get_device_properties(0)
            out["gpu"] = p.name
            out["vram_gb"] = round(p.total_memory / 1024 ** 3, 1)
            out["bf16"] = bool(torch.cuda.is_bf16_supported())
    except Exception as e:
        out["cuda"] = False
        out["errors"].append(f"torch: {e}")

    # 목소리 엔진
    out["tts_models"] = [k for k, d in TTS_MODELS.items()
                         if (d / "config.json").exists() and (d / "speech_tokenizer").exists()]
    tts_ok = bool(out["tts_models"])
    if not tts_ok:
        out["errors"].append("목소리 모델 파일이 없습니다")
    try:
        import qwen_tts  # noqa: F401
    except Exception as e:
        tts_ok = False
        out["errors"].append(f"qwen_tts: {e}")
    out["tts_ready"] = tts_ok

    # 입모양 엔진
    missing = [f for f in MUSE_FILES if not (MUSE / f).exists()]
    lip_ok = (MUSE / "musetalk").exists() and not missing
    if missing:
        out["errors"].append("입모양 모델 파일이 없습니다: " + ", ".join(missing[:3]))
    try:
        import diffusers  # noqa: F401
        import onnxruntime  # noqa: F401
        import cv2  # noqa: F401
    except Exception as e:
        lip_ok = False
        out["errors"].append(f"lipsync 패키지: {e}")
    out["lipsync_ready"] = lip_ok
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
