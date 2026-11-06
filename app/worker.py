"""작업 대기열 — 프로그램 안에서 한 번에 하나씩 순서대로 처리합니다.

두 가지 일을 합니다.
 A. 아바타 준비: 원장님 영상(사진)을 다듬고, 입모양 엔진이 쓸 얼굴 자료를 미리 계산 (아바타마다 한 번)
 B. 영상 만들기
    1/3 음성 만들기 — 원장님 목소리 흉내(목소리 엔진) 또는 직접 녹음 파일 정리
    2/3 입모양 맞추기 — 입모양 엔진(MuseTalk). 끄면 아바타 영상을 그대로 반복
    3/3 꾸미기 입히기 — 병원명·단계 배지·자막·로고 합성

브라우저를 닫아도 프로그램(검은 명령창)이 켜져 있으면 계속 진행됩니다.
프로그램을 껐다 켜면 멈췄던 작업부터 이어서 합니다.
"""
import json
import threading
import time
import traceback
from pathlib import Path

from . import compose, demo, engines, media
from .config import (AVATAR_DIR, TTS_MODEL_DIR, VIDEO_DIR, WORK_DIR, tts_language)
from .db import db, get_setting, now, row
from .textutil import estimate_seconds
from .timing import build_sentences, compute

_wake = threading.Event()
_thread = None
RUNNING = ("voice", "lipsync", "compose")


def wake():
    _wake.set()


def start():
    global _thread
    with db() as c:
        c.execute("UPDATE videos SET status='queued', message='프로그램을 다시 켜서 이어서 진행합니다' "
                  "WHERE status IN ('voice','lipsync','compose','avatar','timing')")
        c.execute("UPDATE avatars SET status='pending', message='프로그램을 다시 켜서 이어서 준비합니다' "
                  "WHERE status='preparing'")
        c.execute("DELETE FROM avatars WHERE status='uploading'")   # 올리다 끊긴 것
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_loop, name="video-worker", daemon=True)
        _thread.start()


def _set(table, rid, **kw):
    if not kw:
        return
    cols = ", ".join(f"{k}=?" for k in kw)
    with db() as c:
        c.execute(f"UPDATE {table} SET {cols} WHERE id=?", (*kw.values(), rid))


def _get(table, rid):
    with db() as c:
        return row(c.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone())


def _loop():
    while True:
        with db() as c:
            av = row(c.execute("SELECT * FROM avatars WHERE status='pending' ORDER BY id LIMIT 1").fetchone())
            v = None if av else row(c.execute("SELECT * FROM videos WHERE status='queued' ORDER BY id LIMIT 1").fetchone())
        if not av and not v:
            _wake.wait(timeout=5)
            _wake.clear()
            continue
        try:
            if av:
                prepare_avatar(av)
            else:
                process_video(v)
        except Exception as e:  # 어떤 오류든 기록하고 다음 작업으로
            traceback.print_exc()
            if av:
                _set("avatars", av["id"], status="failed", error=str(e)[:2000], message=None)
            else:
                _set("videos", v["id"], status="failed", error=str(e)[:2000], message=None, finished_at=now())


# =====================================================================
# A. 아바타 준비
# =====================================================================
def prepare_avatar(av):
    aid = av["id"]
    folder = AVATAR_DIR / str(aid)
    _set("avatars", aid, status="preparing", progress=0.02, message="원본을 다듬고 있습니다", error=None)
    if not av["norm_path"] or not Path(av["norm_path"]).exists():
        info = media.normalize_avatar(av["kind"], av["src_path"], folder)
        _set("avatars", aid, norm_path=info["norm"], preview_path=info["preview"], width=info["width"],
             height=info["height"], orientation=info["orientation"])
        av = _get("avatars", aid)
    st = engines.status()
    if not st.get("lipsync_ready"):
        _set("avatars", aid, status="unprepared", progress=None,
             message="입모양 엔진이 설치되면 준비할 수 있습니다. 지금은 입모양 없이 쓸 수 있습니다.")
        return

    def prog(frac, msg):
        _set("avatars", aid, progress=round(0.05 + 0.95 * frac, 3), message=msg)

    prep = folder / "prep"
    engines.run("lipsync_musetalk.py", ["prepare", "--src", av["norm_path"], "--out", prep,
                                         "--ffmpeg", compose._tool("ffmpeg")], prog, log_name=f"avatar{aid}-prepare")
    _set("avatars", aid, status="ready", prep_dir=str(prep), progress=1.0, message=None, prepared_at=now())


# =====================================================================
# B. 영상 만들기
# =====================================================================
def process_video(v):
    vid = v["id"]
    steps = json.loads(v["script_snapshot"])["steps"]
    work = WORK_DIR / f"v{vid}"
    work.mkdir(parents=True, exist_ok=True)
    if not v["started_at"]:
        _set("videos", vid, started_at=now())

    raw = v["raw_path"]
    timings = json.loads(v["timings"]) if v["timings"] else None
    if not (raw and Path(raw).exists() and timings):
        # ---------- 1/3 음성 ----------
        audio = v["audio_path"]
        if not (audio and Path(audio).exists() and timings):
            _set("videos", vid, status="voice", progress=0.0, error=None, message="음성을 만들고 있습니다")
            audio, timings = make_audio(v, steps, work)
            _set("videos", vid, audio_path=audio, timings=json.dumps(timings, ensure_ascii=False),
                 duration=timings["duration"])
        if _get("videos", vid)["status"] == "cancelled":
            return
        # ---------- 2/3 입모양 ----------
        _set("videos", vid, status="lipsync", progress=0.0, message="입모양을 맞추고 있습니다")
        raw = str(VIDEO_DIR / f"v{vid}_raw.mp4")
        make_visual(v, audio, raw, work)
        _set("videos", vid, raw_path=raw)

    # ---------- 3/3 꾸미기 ----------
    _set("videos", vid, status="compose", progress=None, message="자막과 로고를 입히고 있습니다")
    v = _get("videos", vid)
    style = json.loads(v["style"])
    final = str(VIDEO_DIR / f"v{vid}_final.mp4")
    thumb = str(VIDEO_DIR / f"v{vid}_thumb.jpg")
    dur = compose.compose(raw, final, thumb, steps=steps, timings=timings, style=style,
                          org_name=_org_name(v["language"]), title=v["title"],
                          logo_path=compose.logo_file_path(get_setting("logo_file")), workdir=str(work))
    _set("videos", vid, status="done", final_path=final, thumb_path=thumb, duration=dur, message=None,
         error=None, progress=None, finished_at=now())


def _org_name(language):
    name = get_setting("org_name") or ""
    i18n = get_setting("org_name_i18n") or {}
    if language and not language.startswith("ko") and i18n.get(language):
        return i18n[language]
    return name


def _prog(vid, base, span):
    def f(frac, msg):
        _set("videos", vid, progress=round(base + span * frac, 3), message=msg)
    return f


def make_audio(v, steps, work):
    """→ (음성 wav 경로, 시각 정보)"""
    vid = v["id"]
    out = str(VIDEO_DIR / f"v{vid}_voice.wav")
    mode = v["voice_mode"]

    if mode == "clone":
        voice = _get("voices", v["voice_db_id"]) if v["voice_db_id"] else None
        if not voice:
            raise ValueError("고른 목소리가 지워졌습니다. 목소리를 다시 골라 새로 만들어 주세요.")
        lang = tts_language(v["language"])
        if not lang:
            raise ValueError("이 언어는 목소리 엔진이 지원하지 않습니다. '직접 녹음'으로 만들어 주세요.")
        sents = build_sentences(steps)
        items = [{"text": s["text"], "out": str(work / f"tts_{i:03d}.wav")} for i, s in enumerate(sents)]
        job = {"model": str(TTS_MODEL_DIR), "language": lang, "ref_audio": voice["ref_path"],
               "ref_text": voice["ref_text"], "dtype": get_setting("tts_precision") or "float32",
               "seed": 1234, "items": items}
        job_path = work / "tts_job.json"
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        engines.run("tts_qwen.py", ["--job", job_path], _prog(vid, 0, 1), log_name=f"video{vid}-voice")
        segs = []
        for s, it in zip(sents, items):
            clean = it["out"].replace(".wav", "_24k.wav")
            media.to_wav(it["out"], clean, trim=True, loudnorm=False)
            segs.append({"step": s["step"], "text": s["text"], "wav": clean})
        joined = str(work / "voice_joined.wav")
        placed, dur = media.assemble(segs, joined)
        media.to_wav(joined, out, trim=False, loudnorm=True)   # 전체 소리 크기를 한 번에 맞춤 (길이는 그대로)
        return out, media.timings_from_placed(placed, len(steps), dur, "tts")

    if mode == "recording":
        recs = json.loads(v["recordings"] or "[]")
        if len(recs) != len(steps) or not all(r and Path(r).exists() for r in recs):
            raise ValueError("단계별 녹음 파일이 모자랍니다. 단계마다 녹음을 올려 주세요.")
        sents = build_sentences(steps)
        placed_all, segs = [], []
        for si, rec in enumerate(recs):
            clean = str(work / f"rec_{si}.wav")
            media.to_wav(rec, clean, trim=True, loudnorm=True)
            segs.append({"step": si, "text": f"step{si}", "wav": clean})
        placed_steps, dur = media.assemble(segs, out)
        # 단계 안의 문장 시각은 글자 수 비율로 나눔
        for si, ps in enumerate(placed_steps):
            ss = [s for s in sents if s["step"] == si]
            total = sum(len(s["text"]) for s in ss) or 1
            t = ps["start"]
            span = ps["end"] - ps["start"]
            for s in ss:
                d = span * len(s["text"]) / total
                placed_all.append({"step": si, "text": s["text"], "start": t, "end": t + d})
                t += d
        return out, media.timings_from_placed(placed_all, len(steps), dur, "recording")

    # silent — 소리 없는 연습 영상 (말하는 시간은 글자 수로 추정)
    dur = max(4.0, estimate_seconds(steps, v["language"]))
    media.write_wav(out, media.silence(dur))
    return out, compute(steps, None, dur)


def make_visual(v, audio, raw, work):
    vid = v["id"]
    if demo.is_demo(v["avatar_id"]):
        media.loop_visual("photo", demo.demo_source(v["avatar_id"], WORK_DIR), audio, raw)
        return
    av = _get("avatars", int(v["avatar_id"]))
    if not av or not av["norm_path"] or not Path(av["norm_path"]).exists():
        raise ValueError("아바타 원본을 찾지 못했습니다. 아바타를 다시 등록해 주세요.")
    if v["lipsync"] and v["voice_mode"] != "silent":
        if av["status"] != "ready" or not av["prep_dir"]:
            raise ValueError("이 아바타는 입모양 준비가 아직 안 됐습니다. [아바타·목소리]에서 준비를 마친 뒤 다시 시도하거나, "
                             "입모양 맞추기를 끄고 만들어 주세요.")
        batch = int(get_setting("lipsync_batch") or 8)
        engines.run("lipsync_musetalk.py", ["infer", "--avatar", av["prep_dir"], "--audio", audio, "--out", raw,
                                            "--ffmpeg", compose._tool("ffmpeg"), "--batch", batch],
                    _prog(vid, 0, 1), log_name=f"video{vid}-lipsync")
    else:
        media.loop_visual(av["kind"], av["norm_path"], audio, raw)
