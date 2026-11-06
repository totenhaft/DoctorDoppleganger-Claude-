"""목소리 엔진 (Qwen3-TTS, Apache-2.0) — 엔진 전용 가상환경(engines/.venv)에서 실행됩니다.

    python tts_qwen.py --job job.json

job.json 예:
{
  "model": "engines/models/Qwen3-TTS-12Hz-1.7B-Base",
  "language": "Korean",
  "ref_audio": "data/voices/1/ref.wav",
  "ref_text": "안녕하세요. 연세솔안과 원장입니다. ...",
  "dtype": "auto",
  "items": [{"text": "첫 문장입니다.", "out": "work/s0.wav"}, ...]
}

원장님이 읽은 15~30초 녹음(ref_audio)과 그 원고(ref_text)로 목소리를 흉내 내어,
items 의 문장을 한 문장씩 wav 로 만듭니다. 문장 단위로 만들기 때문에 자막 시점이 정확히 맞습니다.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path


def say(p, msg=""):
    print(f"PROGRESS {max(0.0, min(1.0, p)):.3f} {msg}", flush=True)


def fail(msg):
    print("ERROR " + msg, flush=True)
    sys.exit(2)


def trim_silence(wav, sr, thr=0.01, pad=0.08):
    """앞뒤 무음을 잘라 문장 사이 간격을 일정하게"""
    import numpy as np
    a = np.abs(wav)
    idx = np.where(a > thr * max(1e-6, a.max()))[0]
    if len(idx) == 0:
        return wav
    s = max(0, idx[0] - int(pad * sr))
    e = min(len(wav), idx[-1] + int(pad * sr))
    return wav[s:e]


def expected_seconds(text):
    n = len(re.sub(r"\s+", "", text))
    hangul = len(re.findall(r"[가-힣]", text))
    rate = 5.5 if hangul > n * 0.3 else 13.0
    return max(1.0, n / rate)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    a = ap.parse_args()
    job = json.loads(Path(a.job).read_text(encoding="utf-8"))

    import numpy as np
    import soundfile as sf
    import torch
    try:
        from qwen_tts import Qwen3TTSModel
    except ImportError:
        fail("qwen-tts 패키지가 없습니다. engines\\install 을 먼저 실행해 주세요.")

    cuda = torch.cuda.is_available()
    want = job.get("dtype") or "auto"
    if not cuda:
        dtype = torch.float32
    elif want == "auto":  # RTX 30·40 시리즈처럼 bfloat16 을 지원하면 bf16, 아니면(RTX 20 등) float32
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float32
    else:
        dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16}.get(want, torch.float32)
    print(f"model={Path(job['model']).name} dtype={dtype}", flush=True)
    say(0.02, "목소리 모델을 불러오고 있습니다" + ("" if cuda else " (그래픽카드가 없어 매우 느립니다)"))
    try:
        model = Qwen3TTSModel.from_pretrained(job["model"], device_map="cuda:0" if cuda else "cpu",
                                              dtype=dtype, attn_implementation="sdpa")
    except Exception as e:
        fail(f"목소리 모델을 불러오지 못했습니다: {e}")

    say(0.1, "원장님 목소리 특징을 익히고 있습니다")
    ref_text = (job.get("ref_text") or "").strip()
    prompt = model.create_voice_clone_prompt(ref_audio=job["ref_audio"], ref_text=ref_text or None,
                                             x_vector_only_mode=not bool(ref_text))

    items = job["items"]
    out_info = []
    t0 = time.time()
    for i, it in enumerate(items):
        text = it["text"].strip()
        exp = expected_seconds(text)
        best = None
        for attempt in range(3):  # 너무 길거나 짧게 나오면 다시 만들어 봄
            torch.manual_seed(int(job.get("seed", 1234)) + i * 7 + attempt * 101)
            wavs, sr = model.generate_voice_clone(
                text=text, language=job.get("language", "Korean"), voice_clone_prompt=prompt,
                max_new_tokens=int(12 * max(8.0, exp * 3.0)) + 24)
            w = trim_silence(np.asarray(wavs[0], dtype=np.float32), sr)
            dur = len(w) / sr
            ok = exp * 0.35 <= dur <= max(exp * 2.6, exp + 4)
            if best is None or abs(dur - exp) < abs(best[1] - exp):
                best = (w, dur)
            if ok:
                break
        w, dur = best
        peak = float(np.abs(w).max()) or 1.0
        w = w / peak * 0.89  # 소리 크기 맞추기
        Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)
        sf.write(it["out"], w, sr)
        out_info.append({"out": it["out"], "seconds": round(dur, 3)})
        el = time.time() - t0
        left = el / (i + 1) * (len(items) - i - 1)
        say(0.12 + 0.86 * (i + 1) / len(items), f"문장 {i + 1}/{len(items)} 읽는 중 · 남은 시간 약 {int(left // 60)}분 {int(left % 60)}초")
    say(1.0, "음성을 다 만들었습니다")
    print("RESULT " + json.dumps({"items": out_info, "sample_rate": sr}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        msg = str(e)
        if "out of memory" in msg.lower():
            msg = "그래픽카드 메모리가 부족합니다. 다른 프로그램을 끄고 다시 시도해 주세요."
        fail(msg[:500])
