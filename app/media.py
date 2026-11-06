"""소리·영상 파일 다루기 (ffmpeg 사용) — 음성 이어 붙이기, 아바타 원본 다듬기, 입모양 없이 반복 영상 만들기."""
import json
import wave
from pathlib import Path

from .compose import _tool, run
from .config import AVATAR_MAX_SECONDS, PAUSE_SENTENCE, PAUSE_STEP

SR = 24000
# 앞뒤 무음을 잘라냄 (쉬는 시간은 이어 붙일 때 일정하게 다시 넣음)
# 주의: ffmpeg 6.x 에서 start_silence 옵션과 loudnorm 을 같이 쓰면 멈추는 문제가 있어 쓰지 않음
_AF_CLEAN = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
             "silenceremove=start_periods=1:start_threshold=-45dB,areverse")


def to_wav(src, dst, trim=True, loudnorm=True):
    """어떤 소리 파일이든 24kHz 모노 16bit wav 로 (앞뒤 무음 자르기·소리 크기 맞추기)"""
    filters = []
    if trim:
        filters.append(_AF_CLEAN)
    if loudnorm:
        filters.append("loudnorm=I=-18:TP=-1.5:LRA=11")
    cmd = [_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1"]
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd += ["-ar", str(SR), "-c:a", "pcm_s16le", str(dst)]
    run(cmd)
    return wav_seconds(dst)


def wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _read_pcm(path):
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"음성 형식이 맞지 않습니다: {path}")
        return w.readframes(w.getnframes())


def silence(seconds):
    return b"\x00\x00" * int(round(seconds * SR))


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def assemble(segments, out_path, lead=0.3, tail=0.6):
    """segments: [{"step", "text", "wav"}] (문장 순서) → 쉬는 시간을 넣어 이어 붙이고 문장별 시각을 돌려줌"""
    pcm = bytearray(silence(lead))
    t = lead
    placed = []
    for i, s in enumerate(segments):
        if i > 0:
            gap = PAUSE_STEP if s["step"] != segments[i - 1]["step"] else PAUSE_SENTENCE
            pcm += silence(gap)
            t += gap
        data = _read_pcm(s["wav"])
        dur = len(data) / 2 / SR
        placed.append({"step": s["step"], "text": s["text"], "start": round(t, 3), "end": round(t + dur, 3)})
        pcm += data
        t += dur
    pcm += silence(tail)
    write_wav(out_path, bytes(pcm))
    return placed, round(t + tail, 3)


def timings_from_placed(placed, n_steps, duration, method):
    """문장별 시작·끝 → compose 가 쓰는 시각 정보 (글자별 시각은 문장 안에서 고르게)"""
    sents = []
    for p in placed:
        text = p["text"]
        L = max(1, len(text))
        span = p["end"] - p["start"]
        chars = [round(p["start"] + span * k / L, 2) for k in range(len(text))]
        sents.append({"step": p["step"], "text": text, "start": round(max(0, p["start"] - 0.05), 2),
                      "end": round(p["end"] + 0.15, 2), "chars": chars})
    for a, b in zip(sents, sents[1:]):
        a["end"] = min(a["end"], b["start"])
    steps = []
    for si in range(n_steps):
        ss = [s for s in sents if s["step"] == si]
        steps.append({"start": ss[0]["start"] if ss else None})
    for si in range(n_steps):
        if steps[si]["start"] is None:
            steps[si]["start"] = steps[si - 1]["start"] if si else 0.0
    if steps:
        steps[0]["start"] = 0.0
    for si in range(n_steps):
        steps[si]["end"] = steps[si + 1]["start"] if si + 1 < n_steps else duration
    return {"method": method, "duration": duration, "sentences": sents, "steps": steps}


# ---------------- 아바타 원본 ----------------
def probe_media(path):
    out = run([_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height:format=duration", "-of", "json", str(path)])
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    return st.get("width"), st.get("height"), float((d.get("format") or {}).get("duration") or 0)


SCALE = "scale=-2:'trunc(min(1080,ih)/2)*2'"


def normalize_avatar(kind, src, folder):
    """원본을 25fps·최대 20초·세로 1080 이하·짝수 크기로 맞추고 미리보기 그림을 만듭니다."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    preview = folder / "preview.jpg"
    if kind == "photo":
        norm = folder / "source.png"
        run([_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
             "-vf", f"{SCALE},scale='trunc(iw/2)*2':'trunc(ih/2)*2'", "-frames:v", "1", str(norm)])
        run([_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(norm),
             "-vf", "scale=480:-2", "-frames:v", "1", str(preview)])
    else:
        norm = folder / "source.mp4"
        run([_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
             "-t", str(AVATAR_MAX_SECONDS), "-an", "-vf", f"fps=25,{SCALE}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(norm)])
        run([_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-ss", "0.5", "-i", str(norm),
             "-vf", "scale=480:-2", "-frames:v", "1", str(preview)])
    w, h, dur = probe_media(norm)
    if not w:
        raise ValueError("영상 정보를 읽지 못했습니다.")
    if kind == "video" and dur < 3:
        raise ValueError("영상이 너무 짧습니다. 5초 이상 찍은 영상을 올려 주세요.")
    return {"norm": str(norm), "preview": str(preview), "width": w, "height": h, "duration": dur,
            "orientation": "portrait" if h > w else "landscape"}


def loop_visual(kind, source, audio, out):
    """입모양 맞추기 없이: 아바타 영상(또는 사진)을 음성 길이만큼 반복하고 소리를 붙입니다."""
    if kind == "video":
        inp = ["-stream_loop", "-1", "-i", str(source)]
    else:
        inp = ["-loop", "1", "-framerate", "25", "-i", str(source)]
    run([_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", *inp, "-i", str(audio),
         "-map", "0:v", "-map", "1:a", "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", "25", "-c:a", "aac", "-b:a", "160k", str(out)])
