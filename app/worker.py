"""영상 만들기 대기열 — 프로그램 안에서 한 번에 하나씩 순서대로 처리합니다.

단계
 1/3 아바타 영상 만들기 (HeyGen, 보통 5~10분) — 연습 모드는 몇 초
 2/3 말하는 시점 맞추기 (몇 초)
 3/3 꾸미기 입히기 (자막·로고 합성, 1~3분)

창(브라우저)을 닫아도 프로그램(검은 명령창)이 켜져 있으면 계속 진행됩니다.
프로그램을 껐다 켜면 멈췄던 영상부터 이어서 진행합니다.
"""
import json
import threading
import time
import traceback
from pathlib import Path

from . import compose, demo, heygen
from .config import VIDEO_DIR, WORK_DIR
from .db import db, get_setting, now, row
from .textutil import joined_script, parse_srt

POLL_SEC = 10
AVATAR_TIMEOUT = 90 * 60  # 90분 넘게 끝나지 않으면 실패 처리

_wake = threading.Event()
_thread = None


def wake():
    _wake.set()


def start():
    global _thread
    with db() as c:
        # 프로그램이 꺼질 때 진행 중이던 영상은 다시 대기열로
        c.execute("UPDATE videos SET status='queued', message='프로그램을 다시 켜서 이어서 진행합니다' "
                  "WHERE status IN ('avatar','timing','compose')")
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_loop, name="video-worker", daemon=True)
        _thread.start()


def _set(vid, **kw):
    if not kw:
        return
    cols = ", ".join(f"{k}=?" for k in kw)
    with db() as c:
        c.execute(f"UPDATE videos SET {cols} WHERE id=?", (*kw.values(), vid))


def _get(vid):
    with db() as c:
        return row(c.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone())


def _next():
    with db() as c:
        return row(c.execute("SELECT * FROM videos WHERE status='queued' ORDER BY id LIMIT 1").fetchone())


def _loop():
    while True:
        v = _next()
        if not v:
            _wake.wait(timeout=5)
            _wake.clear()
            continue
        try:
            _process(v)
        except Exception as e:  # 어떤 오류든 기록하고 다음 영상으로
            traceback.print_exc()
            _set(v["id"], status="failed", error=str(e)[:2000], message=None, finished_at=now())


def _process(v):
    vid = v["id"]
    steps = json.loads(v["script_snapshot"])["steps"]
    if not v["started_at"]:
        _set(vid, started_at=now())
        v["started_at"] = now()

    # ---------- 1/3 아바타 영상 ----------
    raw = v["raw_path"]
    if not raw or not Path(raw).exists():
        _set(vid, status="avatar", error=None, message="아바타 영상을 만들고 있습니다")
        raw = str(VIDEO_DIR / f"v{vid}_raw.mp4")
        if v["demo"]:
            dur = demo.make_demo_video(steps, v["language"], v["aspect"], raw, WORK_DIR / f"v{vid}")
            _set(vid, raw_path=raw, duration=dur, subtitle_srt=None)
        else:
            _heygen_stage(v, steps, raw)
    v = _get(vid)
    if v["status"] == "cancelled":
        return

    # ---------- 2/3 말하는 시점 맞추기 ----------
    _set(vid, status="timing", message="말하는 시점을 맞추고 있습니다")
    from .timing import compute
    w, h, dur, _ = compose.probe(v["raw_path"])
    cues = parse_srt(v["subtitle_srt"]) if v["subtitle_srt"] else None
    timings = compute(steps, cues, dur)
    _set(vid, timings=json.dumps(timings, ensure_ascii=False), duration=dur)

    # ---------- 3/3 꾸미기 입히기 ----------
    _set(vid, status="compose", message="자막과 로고를 입히고 있습니다")
    style = json.loads(v["style"])
    final = str(VIDEO_DIR / f"v{vid}_final.mp4")
    thumb = str(VIDEO_DIR / f"v{vid}_thumb.jpg")
    org = _org_name(v["language"])
    compose.compose(v["raw_path"], final, thumb, steps=steps, timings=timings, style=style,
                    org_name=org, title=v["title"],
                    logo_path=compose.logo_file_path(get_setting("logo_file")),
                    workdir=str(WORK_DIR / f"v{vid}"))
    _set(vid, status="done", final_path=final, thumb_path=thumb, message=None, error=None,
         finished_at=now())


def _org_name(language):
    name = get_setting("org_name") or ""
    i18n = get_setting("org_name_i18n") or {}
    if language and not language.startswith("ko") and i18n.get(language):
        return i18n[language]
    return name


def _heygen_stage(v, steps, raw_path):
    vid = v["id"]
    hv = v["heygen_video_id"]
    if not hv:
        key = get_setting("heygen_api_key")
        if not key:
            raise heygen.HeyGenError("HeyGen 연결이 필요합니다. 설정에서 API 키를 등록해 주세요.")
        bg = json.loads(v["background"]) if v["background"] else None
        hv = heygen.create_video(
            key, avatar_id=v["avatar_id"], script=joined_script(steps), voice_id=v["voice_id"],
            aspect=v["aspect"], resolution=get_setting("resolution") or "1080p", title=v["title"],
            background=bg, callback_id=f"dd-{vid}",
            idempotency_key=f"dd-{vid}-{int(v['started_at'] or now())}")
        _set(vid, heygen_video_id=hv)
    t_begin = time.time()
    while True:
        cur = _get(vid)
        if cur["status"] == "cancelled":
            return
        key = get_setting("heygen_api_key")
        if not key:
            _set(vid, message="일시정지: HeyGen 연결이 해제됐습니다. 설정에서 키를 다시 연결하면 이어서 진행됩니다.")
            time.sleep(30)
            continue
        try:
            d = heygen.get_video(key, hv)
        except heygen.HeyGenError as e:
            _set(vid, message=f"HeyGen 응답을 기다리는 중입니다 ({e})")
            time.sleep(POLL_SEC * 3)
            continue
        st = d.get("status")
        if st == "completed" and d.get("video_url"):
            _set(vid, message="아바타 영상을 내려받고 있습니다")
            heygen.download(d["video_url"], raw_path)
            srt = None
            if d.get("subtitle_url"):
                try:
                    srt = heygen.fetch_text(d["subtitle_url"])
                except Exception:
                    srt = None
            _set(vid, raw_path=raw_path, subtitle_srt=srt, duration=d.get("duration"))
            return
        if st == "failed":
            raise heygen.HeyGenError(
                f"HeyGen 이 아바타 영상을 만들지 못했습니다: {d.get('failure_message') or d.get('failure_code') or '이유 미상'}")
        waited = time.time() - t_begin
        if waited > AVATAR_TIMEOUT:
            raise heygen.HeyGenError("HeyGen 에서 90분이 넘도록 끝나지 않았습니다. HeyGen 사이트에서 상태를 확인해 주세요.")
        label = "HeyGen 대기열에서 기다리는 중" if st in ("pending", "waiting") else "HeyGen 이 아바타 영상을 만드는 중"
        extra = " · 평소보다 오래 걸리고 있습니다 (새로고침하지 않아도 됩니다)" if waited > 15 * 60 else ""
        _set(vid, message=f"{label}{extra}")
        time.sleep(POLL_SEC)
