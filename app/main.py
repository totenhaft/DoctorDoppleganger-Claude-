"""웹 서버 (FastAPI). 화면(static/)과 데이터 API(/api/...)를 함께 제공합니다."""
import html
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import ai, compose, demo, engines, media, worker
from .auth import (COOKIE, USERNAME_RE, account_count, create_account, current_user,
                   end_sessions, hash_password, new_session, normalize_username,
                   password_problem, require_operator, require_user, try_login)
from .config import (AVATAR_DIR, DEFAULT_CLAUDE_MODEL, FONT_DIR, LANGUAGE_PRESETS, LOGO_DIR,
                     MAX_STEPS, MAX_VIDEO_SECONDS, REC_DIR, SESSION_HOURS, STATIC_DIR, STEP_COLORS,
                     VIDEO_DIR, VOICE_DIR, WORK_DIR, tts_language)
from .db import (DEFAULT_SHARE, DEFAULT_STYLE, db, get_setting, init_db, merged_style, now,
                 row, rows, set_setting)
from .textutil import clean_steps, clean_title, estimate_seconds, parse_srt

@asynccontextmanager
async def lifespan(_app):
    # 프로그램이 켜질 때 한 번: 데이터베이스 준비, 연습 아바타 그림, 대기열 시작
    init_db()
    demo.make_demo_previews(STATIC_DIR)
    worker.start()
    yield


app = FastAPI(title="Doctor Doppelganger", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)


# 다른 사이트가 몰래 요청을 보내지 못하도록, 화면에서 보낸 요청에는 이 머리말을 붙입니다.
@app.middleware("http")
async def _csrf(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("x-requested-with") != "dd":
            return JSONResponse({"detail": "잘못된 요청입니다."}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


def bad(msg, code=400):
    raise HTTPException(code, msg)


async def body(request: Request):
    try:
        return await request.json()
    except Exception:
        bad("요청 내용을 읽지 못했습니다.")


# =====================================================================
# 로그인 / 계정
# =====================================================================
def _login_response(username):
    token = new_session(username)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_HOURS * 3600)
    return resp


@app.get("/api/session")
def session(request: Request):
    acc = current_user(request)
    return {"user": acc, "setup_needed": account_count() == 0,
            "org_name": get_setting("org_name")}


@app.post("/api/setup")
async def setup(request: Request):
    if account_count() > 0:
        bad("이미 운영자 계정이 있습니다.", 409)
    d = await body(request)
    u = normalize_username(d.get("username"))
    if not USERNAME_RE.match(u):
        bad("아이디는 영문 소문자·숫자와 . _ @ + - 만 쓸 수 있고 3~64자입니다.")
    p = password_problem(d.get("password", ""))
    if p:
        bad(p)
    create_account(u, d["password"], role="operator", must_change=False)
    if d.get("org_name"):
        set_setting("org_name", str(d["org_name"]).strip()[:40])
    return _login_response(u)


@app.post("/api/login")
async def login(request: Request):
    d = await body(request)
    acc, err = try_login(d.get("username", ""), d.get("password", ""))
    if err:
        bad(err, 401)
    return _login_response(acc["username"])


@app.post("/api/logout")
def logout(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        with db() as c:
            c.execute("DELETE FROM sessions WHERE token=?", (token,))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE)
    return resp


@app.post("/api/password")
async def change_password(request: Request):
    acc = current_user(request)
    if not acc:
        bad("로그인이 필요합니다.", 401)
    d = await body(request)
    new = d.get("new_password", "")
    if d.get("confirm") is not None and d.get("confirm") != new:
        bad("새 비밀번호 두 칸이 같지 않습니다.")
    p = password_problem(new)
    if p:
        bad(p)
    with db() as c:
        full = row(c.execute("SELECT * FROM accounts WHERE username=?", (acc["username"],)).fetchone())
        if not acc["must_change"]:
            from .auth import verify_password
            if not verify_password(d.get("current_password", ""), full["pw_hash"]):
                bad("지금 비밀번호가 맞지 않습니다.")
        c.execute("UPDATE accounts SET pw_hash=?, must_change=0, status='active' WHERE username=?",
                  (hash_password(new), acc["username"]))
    end_sessions(acc["username"])
    return _login_response(acc["username"])


@app.get("/api/accounts")
def list_accounts(op=Depends(require_operator)):
    with db() as c:
        accs = rows(c.execute("SELECT username, role, status, locked, failed_count, created_at "
                              "FROM accounts ORDER BY created_at").fetchall())
    return {"accounts": accs, "me": op["username"]}


@app.post("/api/accounts")
async def invite(request: Request, op=Depends(require_operator)):
    d = await body(request)
    u = normalize_username(d.get("username"))
    if not USERNAME_RE.match(u):
        bad("아이디는 영문 소문자·숫자와 . _ @ + - 만 쓸 수 있고 3~64자입니다. 첫 글자는 영문이나 숫자여야 합니다.")
    p = password_problem(d.get("password", ""))
    if p:
        bad(p)
    role = d.get("role") if d.get("role") in ("operator", "staff") else "staff"
    with db() as c:
        if c.execute("SELECT 1 FROM accounts WHERE username=?", (u,)).fetchone():
            bad("이미 있는 아이디입니다.", 409)
    create_account(u, d["password"], role=role, must_change=True)
    return {"ok": True}


def _operators_left(c, excluding):
    return c.execute("SELECT COUNT(*) FROM accounts WHERE role='operator' AND status!='disabled' "
                     "AND username!=?", (excluding,)).fetchone()[0]


@app.patch("/api/accounts/{username}")
async def update_account(username: str, request: Request, op=Depends(require_operator)):
    d = await body(request)
    with db() as c:
        acc = row(c.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone())
        if not acc:
            bad("계정을 찾지 못했습니다.", 404)
        action = d.get("action")
        if action == "role":
            role = d.get("role")
            if role not in ("operator", "staff"):
                bad("역할 값이 맞지 않습니다.")
            if acc["role"] == "operator" and role == "staff" and _operators_left(c, username) == 0:
                bad("운영자가 한 명은 있어야 합니다.")
            c.execute("UPDATE accounts SET role=? WHERE username=?", (role, username))
        elif action == "unlock":
            c.execute("UPDATE accounts SET locked=0, failed_count=0 WHERE username=?", (username,))
        elif action == "disable":
            if username == op["username"]:
                bad("자기 계정은 비활성할 수 없습니다.")
            if acc["role"] == "operator" and _operators_left(c, username) == 0:
                bad("운영자가 한 명은 있어야 합니다.")
            c.execute("UPDATE accounts SET status='disabled' WHERE username=?", (username,))
        elif action == "enable":
            c.execute("UPDATE accounts SET status=? WHERE username=?",
                      ("pending" if acc["must_change"] else "active", username))
        else:
            bad("알 수 없는 작업입니다.")
    if action in ("role", "disable"):
        end_sessions(username)
    return {"ok": True}


@app.post("/api/accounts/{username}/reset")
async def reset_password(username: str, request: Request, op=Depends(require_operator)):
    d = await body(request)
    p = password_problem(d.get("password", ""))
    if p:
        bad(p)
    with db() as c:
        if not c.execute("SELECT 1 FROM accounts WHERE username=?", (username,)).fetchone():
            bad("계정을 찾지 못했습니다.", 404)
        c.execute("UPDATE accounts SET pw_hash=?, must_change=1, locked=0, failed_count=0, "
                  "status=CASE WHEN status='disabled' THEN 'disabled' ELSE 'pending' END WHERE username=?",
                  (hash_password(d["password"]), username))
    end_sessions(username)
    return {"ok": True}


# =====================================================================
# 설정
# =====================================================================
def _fonts():
    out = []
    for f in sorted(FONT_DIR.glob("*")):
        if f.suffix.lower() in (".ttf", ".otf"):
            out.append({"file": f.name, "name": f.stem})
    return out


def _logo_info():
    name = get_setting("logo_file")
    p = LOGO_DIR / name if name else None
    if not p or not p.exists():
        return None
    with Image.open(p) as im:
        return {"url": f"/api/logo?t={int(p.stat().st_mtime)}", "width": im.width, "height": im.height,
                "kb": round(p.stat().st_size / 1024)}


PUBLIC_KEYS = ["org_name", "org_name_i18n", "org_desc", "default_language", "languages",
               "caption_style", "tts_model", "tts_precision", "lipsync_batch", "claude_model", "public_base_url"]


@app.get("/api/settings")
def get_settings(user=Depends(require_user)):
    s = {k: get_setting(k) for k in PUBLIC_KEYS}
    s["caption_style"] = merged_style()
    s["claude_model"] = s["claude_model"] or DEFAULT_CLAUDE_MODEL
    s["public_base_url"] = s["public_base_url"] or ""
    return {
        "settings": s,
        "default_style": DEFAULT_STYLE,
        "engine": engines.status(),
        "claude": {"configured": bool(get_setting("anthropic_api_key"))},
        "ffmpeg": compose.ffmpeg_ok(),
        "fonts": _fonts(),
        "logo": _logo_info(),
        "language_presets": LANGUAGE_PRESETS,
        "step_colors": STEP_COLORS,
        "max_seconds": MAX_VIDEO_SECONDS,
        "role": user["role"],
    }


@app.put("/api/settings")
async def put_settings(request: Request, op=Depends(require_operator)):
    d = await body(request)
    if "org_name" in d:
        name = str(d["org_name"] or "").strip()
        if not name or len(name) > 40:
            bad("병원명은 1~40자로 입력해 주세요.")
        set_setting("org_name", name)
    if "org_name_i18n" in d and isinstance(d["org_name_i18n"], dict):
        set_setting("org_name_i18n", {k: str(v)[:40] for k, v in d["org_name_i18n"].items() if v})
    if "org_desc" in d:
        set_setting("org_desc", str(d["org_desc"] or "")[:300])
    if "languages" in d:
        langs = [l for l in d["languages"] if isinstance(l, dict) and re.match(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$", str(l.get("code", "")))]
        if not langs:
            bad("언어가 하나는 있어야 합니다.")
        set_setting("languages", [{"code": l["code"], "label": str(l.get("label") or l["code"])[:30]} for l in langs])
    if "default_language" in d:
        codes = [l["code"] for l in get_setting("languages")]
        if d["default_language"] not in codes:
            bad("기본언어는 사용 중인 언어 중에서 골라 주세요.")
        set_setting("default_language", d["default_language"])
    if "caption_style" in d:
        set_setting("caption_style", validate_style(d["caption_style"]))
    if "tts_model" in d and d["tts_model"] in ("auto", "0.6B", "1.7B"):
        set_setting("tts_model", d["tts_model"])
    if "tts_precision" in d and d["tts_precision"] in ("auto", "float32", "float16", "bfloat16"):
        set_setting("tts_precision", d["tts_precision"])
    if "lipsync_batch" in d:
        try:
            b = int(d["lipsync_batch"])
        except (TypeError, ValueError):
            bad("입모양 처리 장수에 숫자를 넣어 주세요.")
        if not 0 <= b <= 32:
            bad("입모양 처리 장수는 0(자동)~32 사이여야 합니다.")
        set_setting("lipsync_batch", b)
    if "claude_model" in d:
        set_setting("claude_model", str(d["claude_model"] or "").strip()[:80])
    if "public_base_url" in d:
        u = str(d["public_base_url"] or "").strip().rstrip("/")
        if u and not re.match(r"^https?://[^\s<>\"']+$", u):
            bad("공유 링크 주소는 http:// 또는 https:// 로 시작해야 합니다.")
        set_setting("public_base_url", u)
    return {"ok": True}


def validate_style(s):
    if not isinstance(s, dict):
        bad("자막 설정 형식이 맞지 않습니다.")
    out = {}
    for k, default in DEFAULT_STYLE.items():
        if k not in s:
            continue
        v = s[k]
        if isinstance(default, bool):
            out[k] = bool(v)
        elif isinstance(default, (int, float)):
            try:
                v = float(v)
            except (TypeError, ValueError):
                bad(f"{k} 에 숫자를 넣어 주세요.")
            out[k] = v if isinstance(default, float) else int(round(v))
        else:
            out[k] = str(v)[:80]
    hexes = [k for k in out if k.endswith("color")]
    for k in hexes:
        if not re.match(r"^#[0-9A-Fa-f]{6}$", out[k]):
            bad("색은 #rrggbb 형식이어야 합니다.")
    rng = {"min_chars": (5, 30), "max_chars": (5, 30), "font_size": (20, 120), "stroke_width": (0, 12),
           "opacity": (10, 100), "box_opacity": (0, 100), "shadow_opacity": (0, 100),
           "shadow_distance": (0, 30), "shadow_blur": (0, 30), "shadow_angle": (0, 360),
           "caption_offset": (-20, 60), "badge_offset": (-5, 60), "font_weight": (400, 900),
           "line_height": (1.0, 2.0)}
    for k, (lo, hi) in rng.items():
        if k in out and not (lo <= out[k] <= hi):
            bad(f"{k} 값은 {lo}~{hi} 사이여야 합니다.")
    if out.get("min_chars", 0) > out.get("max_chars", 99):
        bad("최소 글자는 최대 글자보다 클 수 없습니다.")
    return out


@app.post("/api/connection/claude")
async def connect_claude(request: Request, op=Depends(require_operator)):
    d = await body(request)
    key = str(d.get("api_key") or "").strip()
    if not key:
        set_setting("anthropic_api_key", "")
        return {"ok": True}
    if not key.startswith("sk-"):
        bad("Anthropic API 키는 보통 sk- 로 시작합니다. 다시 확인해 주세요.")
    set_setting("anthropic_api_key", key)
    return {"ok": True}


@app.get("/api/features")
def features(user=Depends(require_user)):
    return {"ai": bool(get_setting("anthropic_api_key")), "engine": engines.status(),
            "ffmpeg": compose.ffmpeg_ok()}


@app.get("/api/engine")
def engine_status(refresh: int = 0, user=Depends(require_user)):
    return engines.status(force=bool(refresh))


# ---- 로고 ----
@app.post("/api/logo")
async def upload_logo(file: UploadFile = File(...), op=Depends(require_operator)):
    data = await file.read()
    if len(data) > 512 * 1024:
        bad("로고 파일은 512KB 이하여야 합니다. 이미지 크기를 줄여 다시 올려 주세요.")
    if not data.startswith(b"\x89PNG"):
        bad("PNG 파일만 올릴 수 있습니다. 투명 배경 PNG 를 권합니다.")
    tmp = LOGO_DIR / "upload.tmp"
    tmp.write_bytes(data)
    try:
        with Image.open(tmp) as im:
            im.verify()
        with Image.open(tmp) as im:
            if im.width > 2048 or im.height > 2048:
                bad("로고는 가로·세로 2048px 이하여야 합니다.")
    except HTTPException:
        tmp.unlink(missing_ok=True)
        raise
    except Exception:
        tmp.unlink(missing_ok=True)
        bad("그림 파일을 읽지 못했습니다.")
    name = f"logo_{int(time.time())}.png"
    old = get_setting("logo_file")
    tmp.rename(LOGO_DIR / name)
    set_setting("logo_file", name)
    if old and old != name:
        (LOGO_DIR / old).unlink(missing_ok=True)
    return {"ok": True, "logo": _logo_info()}


@app.delete("/api/logo")
def delete_logo(op=Depends(require_operator)):
    old = get_setting("logo_file")
    set_setting("logo_file", "")
    if old:
        (LOGO_DIR / old).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/logo")
def get_logo():
    # 로고는 공개 정보라 공유 페이지에서도 씁니다.
    name = get_setting("logo_file")
    p = LOGO_DIR / name if name else None
    if not p or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


# ---- 글꼴 ----
@app.post("/api/fonts")
async def upload_font(file: UploadFile = File(...), consent: str = Form(""), op=Depends(require_operator)):
    if consent != "yes":
        bad("글꼴 사용 권리를 확인했다는 칸에 체크해 주세요.")
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in (".ttf", ".otf"):
        bad("TTF·OTF 글꼴 파일만 올릴 수 있습니다.")
    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        bad("글꼴 파일이 너무 큽니다 (최대 30MB).")
    safe = re.sub(r"[^\w.\-가-힣]", "_", name)
    p = FONT_DIR / safe
    p.write_bytes(data)
    try:
        from PIL import ImageFont
        ImageFont.truetype(str(p), 20)
    except Exception:
        p.unlink(missing_ok=True)
        bad("글꼴 파일을 읽지 못했습니다.")
    return {"ok": True, "fonts": _fonts()}


@app.delete("/api/fonts/{name}")
def delete_font(name: str, op=Depends(require_operator)):
    (FONT_DIR / Path(name).name).unlink(missing_ok=True)
    return {"ok": True, "fonts": _fonts()}


@app.get("/api/fonts/{name}")
def get_font_file(name: str, user=Depends(require_user)):
    p = FONT_DIR / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


# ---- 공유 페이지 문구 ----
def share_page_settings():
    s = dict(DEFAULT_SHARE)
    s.update(get_setting("share_page") or {})
    if not s.get("heading"):
        s["heading"] = get_setting("org_name") or ""
    return s


@app.get("/api/share-page")
def get_share_page(user=Depends(require_user)):
    return {"page": share_page_settings(), "defaults": {**DEFAULT_SHARE, "heading": get_setting("org_name")}}


def _check_share(d):
    heading = str(d.get("heading") or "").strip()
    message = str(d.get("message") or "").strip()
    notice = str(d.get("ai_notice") or "").strip() or DEFAULT_SHARE["ai_notice"]
    if len(heading) > 60 or len(message) > 500 or len(notice) > 320:
        bad("글자 수가 너무 깁니다. (상단 60자, 본문 500자, AI 고지 320자)")
    for t in (heading, message, notice):
        if "<" in t or ">" in t:
            bad("꺾쇠 괄호(< >)는 쓸 수 없습니다.")
    if "AI" not in notice.upper() and "인공지능" not in notice:
        bad("AI 고지 문구에 「AI」나 「인공지능」이 들어가야 합니다.")
    return {"heading": heading, "message": message, "ai_notice": notice}


@app.put("/api/share-page")
async def put_share_page(request: Request, op=Depends(require_operator)):
    set_setting("share_page", _check_share(await body(request)))
    return {"ok": True}


@app.post("/api/share-page/preview")
async def preview_share_page(request: Request, user=Depends(require_user)):
    d = await body(request)
    page = {**share_page_settings(), **{k: str(d.get(k) or "") for k in ("heading", "message", "ai_notice")}}
    return HTMLResponse(render_share(page, "안내 영상 제목", None, preview=True))


# =====================================================================
# 스크립트
# =====================================================================
def _script_out(r):
    r = dict(r)
    r["steps"] = json.loads(r["steps"])
    r["chars"] = sum(len(s["body"]) for s in r["steps"])
    r["lines"] = sum(len([l for l in s["body"].split("\n") if l.strip()]) for s in r["steps"])
    r["est_seconds"] = estimate_seconds(r["steps"], r["language"])
    r["reviewed"] = bool(r["reviewed"])
    return r


@app.get("/api/scripts")
def list_scripts(user=Depends(require_user)):
    with db() as c:
        rs = c.execute("SELECT * FROM scripts ORDER BY created_at DESC").fetchall()
    return {"scripts": [_script_out(r) for r in rs]}


def _lang_ok(code):
    return any(l["code"] == code for l in get_setting("languages"))


@app.post("/api/scripts")
async def create_script(request: Request, user=Depends(require_user)):
    d = await body(request)
    try:
        title = clean_title(d.get("title"))
        steps = clean_steps(d.get("steps"))
    except ValueError as e:
        bad(str(e))
    lang = d.get("language") or get_setting("default_language")
    if not _lang_ok(lang):
        bad("설정에서 켜 둔 언어만 고를 수 있습니다.")
    source = d.get("source") if d.get("source") in ("manual", "ai", "srt", "backup") else "manual"
    t = now()
    with db() as c:
        cur = c.execute("INSERT INTO scripts(title, language, steps, reviewed, source, created_by, created_at, updated_at) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (title, lang, json.dumps(steps, ensure_ascii=False), 1, source, user["username"], t, t))
        sid = cur.lastrowid
    return {"ok": True, "id": sid}


def _get_script(sid):
    with db() as c:
        r = c.execute("SELECT * FROM scripts WHERE id=?", (sid,)).fetchone()
    if not r:
        bad("스크립트를 찾지 못했습니다.", 404)
    return _script_out(r)


@app.get("/api/scripts/{sid}")
def get_script(sid: int, user=Depends(require_user)):
    return _get_script(sid)


@app.put("/api/scripts/{sid}")
async def update_script(sid: int, request: Request, user=Depends(require_user)):
    _get_script(sid)
    d = await body(request)
    try:
        title = clean_title(d.get("title"))
        steps = clean_steps(d.get("steps"))
    except ValueError as e:
        bad(str(e))
    lang = d.get("language")
    if not _lang_ok(lang):
        bad("설정에서 켜 둔 언어만 고를 수 있습니다.")
    with db() as c:
        c.execute("UPDATE scripts SET title=?, language=?, steps=?, updated_at=? WHERE id=?",
                  (title, lang, json.dumps(steps, ensure_ascii=False), now(), sid))
    return {"ok": True}


@app.post("/api/scripts/{sid}/review")
def review_script(sid: int, user=Depends(require_user)):
    _get_script(sid)
    with db() as c:
        c.execute("UPDATE scripts SET reviewed=1 WHERE id=?", (sid,))
    return {"ok": True}


@app.delete("/api/scripts/{sid}")
def delete_script(sid: int, user=Depends(require_user)):
    _get_script(sid)
    with db() as c:
        c.execute("DELETE FROM scripts WHERE id=?", (sid,))
    return {"ok": True}


@app.post("/api/scripts/{sid}/duplicate")
def duplicate_script(sid: int, user=Depends(require_user)):
    s = _get_script(sid)
    title = (s["title"] + " (사본)")[:60]
    t = now()
    with db() as c:
        cur = c.execute("INSERT INTO scripts(title, language, steps, reviewed, source, created_by, created_at, updated_at) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (title, s["language"], json.dumps(s["steps"], ensure_ascii=False), int(s["reviewed"]),
                         s["source"], user["username"], t, t))
    return {"ok": True, "id": cur.lastrowid}


@app.post("/api/scripts/{sid}/translate")
async def translate_script(sid: int, request: Request, user=Depends(require_user)):
    s = _get_script(sid)
    d = await body(request)
    target = d.get("language")
    langs = {l["code"]: l["label"] for l in get_setting("languages")}
    if target not in langs:
        bad("번역할 언어를 골라 주세요.")
    if target == s["language"]:
        bad("원고와 같은 언어입니다.")
    org = (get_setting("org_name_i18n") or {}).get(target) or get_setting("org_name")
    try:
        title, steps = ai.translate(s["title"], s["steps"], langs[target], org)
    except ai.AIError as e:
        bad(str(e))
    try:
        steps = clean_steps(steps)
    except ValueError as e:
        bad(f"번역 결과를 저장하지 못했습니다: {e}")
    t = now()
    with db() as c:
        cur = c.execute("INSERT INTO scripts(title, language, steps, reviewed, source, created_by, created_at, updated_at) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (title or s["title"], target, json.dumps(steps, ensure_ascii=False), 0, "translate",
                         user["username"], t, t))
    return {"ok": True, "id": cur.lastrowid}


@app.post("/api/srt/parse")
async def srt_parse(file: UploadFile = File(...), user=Depends(require_user)):
    data = await file.read()
    if len(data) > 256 * 1024:
        bad("파일이 너무 큽니다 (최대 256KB).")
    for enc in ("utf-8-sig", "cp949", "utf-16"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        bad("파일 인코딩을 읽지 못했습니다. UTF-8 로 저장한 SRT 파일을 올려 주세요.")
    cues = parse_srt(text)
    if not cues:
        bad("자막 시간(00:00:01,000 --> 00:00:02,000 형식)을 찾지 못했습니다. SRT 파일이 맞는지 확인해 주세요.")
    if len(cues) > 2000:
        bad("자막 블록이 너무 많습니다 (최대 2000개).")
    out, punct = [], 0
    for _, _, t in cues:
        t = t.strip()
        if t and t[-1] not in ".!?。！？…":
            t += "."
            punct += 1
        out.append(t)
    return {"text": " ".join(out), "recognized": len(cues), "punctuated": punct}


@app.post("/api/ai-draft")
async def ai_draft(request: Request, user=Depends(require_user)):
    d = await body(request)
    topic = str(d.get("topic") or "").strip()
    if not topic:
        bad("안내 주제를 적어 주세요.")
    if len(topic) > 80 or len(str(d.get("memo") or "")) > 400:
        bad("주제는 80자, 메모는 400자까지 쓸 수 있습니다.")
    langs = {l["code"]: l["label"] for l in get_setting("languages")}
    lang = d.get("language") or get_setting("default_language")
    try:
        steps = ai.draft(topic, d.get("memo"), d.get("steps", 3), get_setting("org_name"), langs.get(lang, "한국어"))
    except ai.AIError as e:
        bad(str(e))
    return {"steps": steps}


# =====================================================================
# 아바타 · 목소리 (이 PC 안에 저장)
# =====================================================================
MAX_UPLOAD = 500 * 1024 * 1024


async def _save_upload(file: UploadFile, dest: Path, limit=MAX_UPLOAD):
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                f.close()
                dest.unlink(missing_ok=True)
                bad(f"파일이 너무 큽니다 (최대 {limit // 1024 // 1024}MB).")
            f.write(chunk)
    if size == 0:
        dest.unlink(missing_ok=True)
        bad("빈 파일입니다.")
    return dest


def _avatar_out(r):
    return {
        "id": str(r["id"]), "name": r["name"], "kind": r["kind"], "orientation": r["orientation"] or "landscape",
        "width": r["width"], "height": r["height"], "status": r["status"], "progress": r["progress"],
        "message": r["message"], "error": r["error"], "created_at": r["created_at"], "demo": False,
        "preview_image": f"/api/avatars/{r['id']}/preview?t={int(r['prepared_at'] or r['created_at'])}" if r["preview_path"] else None,
    }


def _get_avatar(aid):
    with db() as c:
        r = row(c.execute("SELECT * FROM avatars WHERE id=?", (aid,)).fetchone())
    if not r:
        bad("아바타를 찾지 못했습니다.", 404)
    return r


@app.get("/api/avatars")
def list_avatars(user=Depends(require_user)):
    with db() as c:
        rs = c.execute("SELECT * FROM avatars ORDER BY created_at DESC").fetchall()
    return {"items": [_avatar_out(r) for r in rs] + demo.DEMO_AVATARS, "engine": engines.status()}


@app.post("/api/avatars")
async def add_avatar(name: str = Form(...), consent: str = Form(""), file: UploadFile = File(...),
                     user=Depends(require_user)):
    if consent != "yes":
        bad("본인이거나 본인 동의를 받은 얼굴인지 확인하는 칸에 체크해 주세요.")
    name = name.strip()[:40]
    if not name:
        bad("아바타 이름을 입력해 주세요.")
    ext = Path(file.filename or "").suffix.lower()
    if ext in (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"):
        kind = "video"
    elif ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        kind = "photo"
    else:
        bad("영상(mp4·mov) 또는 사진(jpg·png) 파일을 올려 주세요.")
    if not compose.ffmpeg_ok():
        bad("ffmpeg 가 설치되어 있지 않습니다. README 를 따라 설치해 주세요.")
    with db() as c:
        cur = c.execute("INSERT INTO avatars(name, kind, src_path, status, progress, message, created_by, created_at) "
                        "VALUES(?,?,?,?,?,?,?,?)", (name, kind, "", "uploading", 0, "올리는 중", user["username"], now()))
        aid = cur.lastrowid
    folder = AVATAR_DIR / str(aid)
    src = await _save_upload(file, folder / f"upload{ext}")
    import anyio
    try:
        info = await anyio.to_thread.run_sync(lambda: media.normalize_avatar(kind, src, folder))
    except Exception as e:
        with db() as c:
            c.execute("DELETE FROM avatars WHERE id=?", (aid,))
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        bad(f"파일을 읽지 못했습니다: {str(e)[:300]}")
    with db() as c:
        c.execute("UPDATE avatars SET src_path=?, norm_path=?, preview_path=?, width=?, height=?, orientation=?, "
                  "status='pending', message='대기 중' WHERE id=?",
                  (str(src), info["norm"], info["preview"], info["width"], info["height"], info["orientation"], aid))
    worker.wake()
    return {"ok": True, "id": str(aid)}


@app.post("/api/avatars/{aid}/prepare")
def reprepare_avatar(aid: int, user=Depends(require_user)):
    a = _get_avatar(aid)
    if a["status"] in ("pending", "preparing"):
        bad("이미 준비 중입니다.")
    import shutil
    if a["prep_dir"]:
        shutil.rmtree(a["prep_dir"], ignore_errors=True)
    engines.status(force=True)
    with db() as c:
        c.execute("UPDATE avatars SET status='pending', prep_dir=NULL, progress=0, error=NULL, message='대기 중' WHERE id=?", (aid,))
    worker.wake()
    return {"ok": True}


@app.patch("/api/avatars/{aid}")
async def rename_avatar(aid: int, request: Request, user=Depends(require_user)):
    _get_avatar(aid)
    name = str((await body(request)).get("name") or "").strip()[:40]
    if not name:
        bad("이름을 입력해 주세요.")
    with db() as c:
        c.execute("UPDATE avatars SET name=? WHERE id=?", (name, aid))
    return {"ok": True}


@app.delete("/api/avatars/{aid}")
def delete_avatar(aid: int, user=Depends(require_user)):
    a = _get_avatar(aid)
    if a["status"] == "preparing":
        bad("준비 중인 아바타는 지울 수 없습니다. 끝난 뒤 지워 주세요.")
    with db() as c:
        busy = c.execute("SELECT COUNT(*) FROM videos WHERE avatar_id=? AND status IN ('queued','voice','lipsync')",
                         (str(aid),)).fetchone()[0]
        if busy:
            bad("이 아바타로 만들고 있는 영상이 있습니다. 끝난 뒤 지워 주세요.")
        c.execute("DELETE FROM avatars WHERE id=?", (aid,))
    import shutil
    shutil.rmtree(AVATAR_DIR / str(aid), ignore_errors=True)
    return {"ok": True}


@app.get("/api/avatars/{aid}/preview")
def avatar_preview(aid: int, user=Depends(require_user)):
    a = _get_avatar(aid)
    if not a["preview_path"] or not Path(a["preview_path"]).exists():
        raise HTTPException(404)
    return FileResponse(a["preview_path"], media_type="image/jpeg")


@app.get("/api/avatars/{aid}/source")
def avatar_source(aid: int, user=Depends(require_user)):
    a = _get_avatar(aid)
    if not a["norm_path"] or not Path(a["norm_path"]).exists():
        raise HTTPException(404)
    return FileResponse(a["norm_path"])


# ---- 목소리 ----
def _voice_out(r):
    return {"id": r["id"], "name": r["name"], "language": r["language"], "ref_text": r["ref_text"],
            "seconds": r["seconds"], "created_at": r["created_at"], "audio": f"/api/voices/{r['id']}/audio"}


def _get_voice(vid):
    with db() as c:
        r = row(c.execute("SELECT * FROM voices WHERE id=?", (vid,)).fetchone())
    if not r:
        bad("목소리를 찾지 못했습니다.", 404)
    return r


@app.get("/api/voices")
def list_voices(user=Depends(require_user)):
    with db() as c:
        rs = c.execute("SELECT * FROM voices ORDER BY created_at DESC").fetchall()
    return {"items": [_voice_out(r) for r in rs], "engine": engines.status()}


@app.post("/api/voices")
async def add_voice(name: str = Form(...), language: str = Form("ko-KR"), ref_text: str = Form(""),
                    consent: str = Form(""), file: UploadFile = File(...), user=Depends(require_user)):
    if consent != "yes":
        bad("본인 목소리이거나 본인 동의를 받은 목소리인지 확인하는 칸에 체크해 주세요.")
    name = name.strip()[:40]
    ref_text = re.sub(r"\s+", " ", ref_text).strip()[:1000]
    if not name:
        bad("목소리 이름을 입력해 주세요.")
    if len(ref_text) < 10:
        bad("녹음할 때 읽은 문장을 그대로 적어 주세요. 정확할수록 목소리가 닮습니다.")
    if not tts_language(language):
        bad("이 언어는 목소리 엔진이 지원하지 않습니다.")
    if not compose.ffmpeg_ok():
        bad("ffmpeg 가 설치되어 있지 않습니다.")
    ext = Path(file.filename or "rec.webm").suffix.lower() or ".webm"
    tmp = await _save_upload(file, WORK_DIR / f"voice_upload_{secrets.token_hex(6)}{ext}", limit=50 * 1024 * 1024)
    folder_tmp = VOICE_DIR / f"new_{secrets.token_hex(6)}"
    folder_tmp.mkdir(parents=True, exist_ok=True)
    import anyio
    try:
        secs = await anyio.to_thread.run_sync(lambda: media.to_wav(tmp, folder_tmp / "ref.wav", trim=True, loudnorm=True))
    except Exception as e:
        bad(f"녹음 파일을 읽지 못했습니다: {str(e)[:200]}")
    finally:
        tmp.unlink(missing_ok=True)
    if secs < 5:
        bad(f"녹음이 {secs:.1f}초로 너무 짧습니다. 10~30초 정도로 녹음해 주세요.")
    if secs > 60:
        bad(f"녹음이 {secs:.0f}초로 너무 깁니다. 30초 안팎이 가장 좋습니다 (최대 60초).")
    with db() as c:
        cur = c.execute("INSERT INTO voices(name, language, ref_path, ref_text, seconds, created_by, created_at) "
                        "VALUES(?,?,?,?,?,?,?)", (name, language, "", ref_text, round(secs, 1), user["username"], now()))
        vid = cur.lastrowid
        folder = VOICE_DIR / str(vid)
        folder_tmp.rename(folder)
        c.execute("UPDATE voices SET ref_path=? WHERE id=?", (str(folder / "ref.wav"), vid))
    return {"ok": True, "id": vid, "seconds": round(secs, 1)}


@app.delete("/api/voices/{vid}")
def delete_voice(vid: int, user=Depends(require_user)):
    _get_voice(vid)
    with db() as c:
        busy = c.execute("SELECT COUNT(*) FROM videos WHERE voice_db_id=? AND status IN ('queued','voice')", (vid,)).fetchone()[0]
        if busy:
            bad("이 목소리로 만들고 있는 영상이 있습니다. 끝난 뒤 지워 주세요.")
        c.execute("DELETE FROM voices WHERE id=?", (vid,))
    import shutil
    shutil.rmtree(VOICE_DIR / str(vid), ignore_errors=True)
    return {"ok": True}


@app.get("/api/voices/{vid}/audio")
def voice_audio(vid: int, sample: int = 0, user=Depends(require_user)):
    v = _get_voice(vid)
    p = Path(v["ref_path"]).parent / "sample.wav" if sample else Path(v["ref_path"])
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.post("/api/voices/{vid}/test")
async def test_voice(vid: int, request: Request, user=Depends(require_user)):
    """등록한 목소리로 짧은 문장을 읽어 봅니다 (모델을 불러오느라 30초~1분 걸림)"""
    v = _get_voice(vid)
    text = str((await body(request)).get("text") or "").strip()[:200]
    if not text:
        bad("읽어 볼 문장을 입력해 주세요.")
    st = engines.status()
    if not st.get("tts_ready"):
        bad("목소리 엔진이 설치되지 않았습니다. 설정 → 영상 엔진을 확인해 주세요.")
    if engines.GPU_LOCK.locked():
        bad("지금 다른 영상을 만들고 있어 그래픽카드가 바쁩니다. 끝난 뒤 다시 들어 보세요.", 409)
    folder = Path(v["ref_path"]).parent
    raw = folder / "sample_raw.wav"
    job = {"model": str(engines.tts_model_dir()), "language": tts_language(v["language"]), "ref_audio": v["ref_path"],
           "ref_text": v["ref_text"], "dtype": engines.tts_precision(),
           "items": [{"text": text, "out": str(raw)}]}
    jp = folder / "sample_job.json"
    jp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    import anyio
    try:
        await anyio.to_thread.run_sync(lambda: engines.run("tts_qwen.py", ["--job", jp], None, log_name=f"voice{vid}-test"))
        await anyio.to_thread.run_sync(lambda: media.to_wav(raw, folder / "sample.wav", trim=True, loudnorm=True))
    except engines.EngineError as e:
        bad(str(e))
    return {"ok": True, "audio": f"/api/voices/{vid}/audio?sample=1&t={int(time.time())}"}


# ---- 영상마다 직접 녹음한 음성 ----
@app.post("/api/recordings")
async def upload_recording(file: UploadFile = File(...), user=Depends(require_user)):
    ext = Path(file.filename or "rec.webm").suffix.lower() or ".webm"
    token = secrets.token_hex(10)
    tmp = await _save_upload(file, REC_DIR / f"{token}_upload{ext}", limit=100 * 1024 * 1024)
    import anyio
    try:
        secs = await anyio.to_thread.run_sync(lambda: media.to_wav(tmp, REC_DIR / f"{token}.wav", trim=True, loudnorm=True))
    except Exception as e:
        bad(f"녹음 파일을 읽지 못했습니다: {str(e)[:200]}")
    finally:
        tmp.unlink(missing_ok=True)
    if secs < 0.5:
        bad("녹음에 소리가 거의 없습니다. 다시 녹음해 주세요.")
    return {"id": token, "seconds": round(secs, 1)}


def _recording_path(token):
    if not re.match(r"^[0-9a-f]{20}$", str(token or "")):
        return None
    p = REC_DIR / f"{token}.wav"
    return str(p) if p.exists() else None


# =====================================================================
# 영상
# =====================================================================
STAGES = {"queued": 0, "voice": 1, "lipsync": 2, "compose": 3, "done": 3, "failed": 0, "cancelled": 0}
ACTIVE = ("voice", "lipsync", "compose")


def share_base(request: Request):
    return (get_setting("public_base_url") or str(request.base_url)).rstrip("/")


def _video_out(r, queue_pos, base):
    v = dict(r)
    snap = json.loads(v.pop("script_snapshot"))
    for k in ("subtitle_srt", "timings", "raw_path", "final_path", "thumb_path", "heygen_video_id", "background",
              "audio_path", "recordings"):
        v.pop(k, None)
    v["has_raw"] = bool(r["raw_path"] and Path(r["raw_path"]).exists())
    v["has_final"] = bool(r["final_path"] and Path(r["final_path"]).exists())
    v["thumb"] = f"/api/videos/{r['id']}/thumb?t={int(r['finished_at'] or 0)}" if r["thumb_path"] else None
    v["style"] = json.loads(r["style"])
    v["steps"] = snap["steps"]
    v["stage"] = STAGES.get(r["status"], 0)
    v["queue_pos"] = queue_pos.get(r["id"])
    v["share_url"] = f"{base}/v/{r['share_slug']}" if r["share_slug"] and r["share_enabled"] else None
    v["demo"] = bool(r["demo"])
    v["reviewed"] = bool(r["reviewed"])
    v["share_enabled"] = bool(r["share_enabled"])
    v["lipsync"] = bool(r["lipsync"])
    return v


@app.get("/api/videos")
def list_videos(request: Request, user=Depends(require_user)):
    with db() as c:
        rs = c.execute("SELECT * FROM videos WHERE status!='cancelled' ORDER BY created_at DESC").fetchall()
        avatars_waiting = c.execute("SELECT COUNT(*) FROM avatars WHERE status IN ('pending','preparing')").fetchone()[0]
    queued = sorted([r["id"] for r in rs if r["status"] == "queued"])
    running = any(r["status"] in ACTIVE for r in rs) or avatars_waiting > 0
    pos = {vid: i + (1 if running else 0) for i, vid in enumerate(queued)}
    base = share_base(request)
    return {"videos": [_video_out(r, pos, base) for r in rs], "now": now()}


def _get_video(vid):
    with db() as c:
        r = row(c.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone())
    if not r:
        bad("영상을 찾지 못했습니다.", 404)
    return r


@app.get("/api/videos/{vid}")
def get_video(vid: int, request: Request, user=Depends(require_user)):
    r = _get_video(vid)
    return _video_out(r, {}, share_base(request))


def _insert_video(**kw):
    kw.setdefault("created_at", now())
    cols = ", ".join(kw)
    q = ", ".join("?" for _ in kw)
    with db() as c:
        cur = c.execute(f"INSERT INTO videos({cols}) VALUES({q})", tuple(kw.values()))
        vid = cur.lastrowid
    worker.wake()
    return vid


def _check_voice_choice(d, steps, language):
    """→ (voice_mode, voice_db_id, recordings_json)"""
    mode = d.get("voice_mode")
    st = engines.status()
    if mode == "clone":
        voice = _get_voice(int(d.get("voice_id") or 0))
        if not st.get("tts_ready"):
            bad("목소리 엔진이 아직 설치되지 않았습니다. 설정 → 영상 엔진을 확인하거나 '직접 녹음'을 써 주세요.")
        if not tts_language(language):
            bad("이 언어는 목소리 엔진이 지원하지 않습니다. '직접 녹음'으로 만들어 주세요.")
        return "clone", voice["id"], None
    if mode == "recording":
        recs = d.get("recordings") or []
        if len(recs) != len(steps):
            bad(f"단계가 {len(steps)}개입니다. 단계마다 녹음을 하나씩 올려 주세요.")
        paths = [_recording_path(t) for t in recs]
        if not all(paths):
            bad("올린 녹음 파일을 찾지 못했습니다. 다시 올려 주세요.")
        total = sum(media.wav_seconds(p) for p in paths)
        if total > MAX_VIDEO_SECONDS:
            bad(f"녹음 길이가 모두 {int(total)}초입니다. 최대 {MAX_VIDEO_SECONDS}초까지 만들 수 있습니다.")
        return "recording", None, json.dumps(paths, ensure_ascii=False)
    return "silent", None, None


@app.post("/api/videos")
async def create_video(request: Request, user=Depends(require_user)):
    d = await body(request)
    try:
        title = clean_title(d.get("title"))
    except ValueError as e:
        bad(str(e))
    s = _get_script(int(d.get("script_id") or 0))
    if not compose.ffmpeg_ok():
        bad("ffmpeg 가 설치되어 있지 않아 영상을 만들 수 없습니다. README 를 따라 설치해 주세요.")
    avatar_id = str(d.get("avatar_id") or "")
    if demo.is_demo(avatar_id):
        av = next((a for a in demo.DEMO_AVATARS if a["id"] == avatar_id), None)
        if not av:
            bad("연습용 아바타 이름이 맞지 않습니다.")
        orientation, is_demo, av_name, preview = av["orientation"], True, av["name"], av["preview_image"]
        av_status = "demo"
    else:
        a = _get_avatar(int(avatar_id or 0))
        if a["status"] == "failed":
            bad("이 아바타는 준비에 실패했습니다. [아바타·목소리]에서 다시 준비하거나 새로 등록해 주세요.")
        orientation, is_demo, av_name = a["orientation"] or "landscape", False, a["name"]
        preview, av_status = _avatar_out(a)["preview_image"], a["status"]
    est = estimate_seconds(s["steps"], s["language"])
    mode, voice_db_id, recordings = _check_voice_choice(d, s["steps"], s["language"])
    if mode != "recording" and est > MAX_VIDEO_SECONDS:
        bad(f"원고 예상 길이가 약 {int(est)}초입니다. 최대 {MAX_VIDEO_SECONDS}초까지 만들 수 있으니 원고를 줄여 주세요.")
    lipsync = bool(d.get("lipsync")) and not is_demo and mode != "silent"
    if lipsync:
        if not engines.status().get("lipsync_ready"):
            bad("입모양 엔진이 아직 설치되지 않았습니다. 입모양 맞추기를 끄고 만들거나 엔진을 설치해 주세요.")
        if av_status == "unprepared":
            bad("이 아바타는 입모양 준비가 안 됐습니다. [아바타·목소리]에서 「입모양 준비」를 먼저 눌러 주세요.")
    if not s["reviewed"] and not d.get("confirm_unreviewed"):
        bad("이 스크립트는 검수 전 기계번역입니다. 의료진 검수 후 만들어 주세요.", 409)
    style = validate_style(merged_style(d.get("style") or {}))
    vid = _insert_video(
        title=title, script_id=s["id"],
        script_snapshot=json.dumps({"title": s["title"], "steps": s["steps"]}, ensure_ascii=False),
        language=s["language"], avatar_id=avatar_id, avatar_name=av_name[:100], avatar_preview=preview,
        aspect="9:16" if orientation == "portrait" else "16:9",
        style=json.dumps({**merged_style(), **style}, ensure_ascii=False), demo=1 if is_demo else 0,
        voice_mode=mode, voice_db_id=voice_db_id, recordings=recordings, lipsync=1 if lipsync else 0,
        status="queued", reviewed=1 if s["reviewed"] else 0, created_by=user["username"])
    return {"ok": True, "id": vid}


@app.post("/api/videos/{vid}/recompose")
async def recompose(vid: int, request: Request, user=Depends(require_user)):
    """꾸미기 바꾸기 — 음성·입모양 영상은 그대로 두고 자막·로고만 다시 입힘 (몇 분이면 끝)"""
    src = _get_video(vid)
    if not (src["raw_path"] and Path(src["raw_path"]).exists() and src["timings"]):
        bad("입모양까지 맞춘 영상이 없어 꾸미기를 바꿀 수 없습니다.")
    d = await body(request)
    style = validate_style(merged_style(d.get("style") or json.loads(src["style"])))
    try:
        title = clean_title(d.get("title") or src["title"])
    except ValueError as e:
        bad(str(e))
    keep = ("script_id", "script_snapshot", "language", "avatar_id", "avatar_name", "avatar_preview", "aspect",
            "demo", "raw_path", "timings", "audio_path", "voice_mode", "voice_db_id", "recordings", "lipsync",
            "reviewed", "duration")
    new = _insert_video(title=title, style=json.dumps({**merged_style(), **style}, ensure_ascii=False),
                        status="queued", parent_id=src["id"], created_by=user["username"],
                        **{k: src[k] for k in keep})
    return {"ok": True, "id": new}


@app.post("/api/videos/{vid}/remake")
async def remake(vid: int, request: Request, user=Depends(require_user)):
    """대사 고쳐 다시 만들기 — 같은 아바타·목소리·자막 설정으로 음성부터 새로"""
    src = _get_video(vid)
    if src["voice_mode"] == "recording":
        bad("직접 녹음한 영상은 대사를 고치려면 새로 녹음해야 합니다. 스크립트를 고친 뒤 [영상 만들기]에서 다시 만들어 주세요.")
    d = await body(request)
    try:
        steps = clean_steps(d.get("steps"))
    except ValueError as e:
        bad(str(e))
    if len(steps) > MAX_STEPS:
        bad("단계가 너무 많습니다.")
    est = estimate_seconds(steps, src["language"])
    if est > MAX_VIDEO_SECONDS:
        bad(f"원고 예상 길이가 약 {int(est)}초라 만들 수 없습니다. 대사를 줄여 주세요.")
    snap = json.loads(src["script_snapshot"])
    keep = ("title", "script_id", "language", "avatar_id", "avatar_name", "avatar_preview", "aspect", "style",
            "demo", "voice_mode", "voice_db_id", "lipsync", "reviewed")
    new = _insert_video(script_snapshot=json.dumps({"title": snap.get("title"), "steps": steps}, ensure_ascii=False),
                        status="queued", created_by=user["username"], **{k: src[k] for k in keep})
    return {"ok": True, "id": new}


@app.post("/api/videos/{vid}/retry")
def retry(vid: int, user=Depends(require_user)):
    v = _get_video(vid)
    if v["status"] != "failed":
        bad("실패한 영상만 다시 시도할 수 있습니다.")
    with db() as c:
        c.execute("UPDATE videos SET status='queued', error=NULL, message='다시 시도합니다', progress=NULL WHERE id=?", (vid,))
    worker.wake()
    return {"ok": True}


@app.post("/api/videos/{vid}/cancel")
def cancel(vid: int, user=Depends(require_user)):
    v = _get_video(vid)
    if v["status"] != "queued":
        bad("아직 시작하지 않은 영상만 대기 취소할 수 있습니다.")
    with db() as c:
        c.execute("UPDATE videos SET status='cancelled' WHERE id=?", (vid,))
    return {"ok": True}


@app.delete("/api/videos/{vid}")
def delete_video(vid: int, user=Depends(require_user)):
    v = _get_video(vid)
    if v["status"] in ACTIVE:
        bad("만드는 중인 영상은 지울 수 없습니다.")
    with db() as c:
        c.execute("DELETE FROM videos WHERE id=?", (vid,))
        shared = {}
        for col in ("raw_path", "audio_path"):
            shared[col] = c.execute(f"SELECT COUNT(*) FROM videos WHERE {col}=?", (v[col],)).fetchone()[0] if v[col] else 1
    for p in (v["final_path"], v["thumb_path"]):
        if p:
            Path(p).unlink(missing_ok=True)
    for col in ("raw_path", "audio_path"):
        if v[col] and shared[col] == 0:
            Path(v[col]).unlink(missing_ok=True)
    import shutil
    shutil.rmtree(WORK_DIR / f"v{vid}", ignore_errors=True)
    return {"ok": True}


@app.post("/api/videos/{vid}/share")
async def share(vid: int, request: Request, user=Depends(require_user)):
    v = _get_video(vid)
    d = await body(request)
    enabled = bool(d.get("enabled"))
    if enabled and v["status"] != "done":
        bad("완성된 영상만 공유할 수 있습니다.")
    slug = v["share_slug"]
    if enabled and (not slug or d.get("new_slug")):
        slug = secrets.token_urlsafe(9)
    with db() as c:
        c.execute("UPDATE videos SET share_slug=?, share_enabled=? WHERE id=?", (slug, 1 if enabled else 0, vid))
    url = f"{share_base(request)}/v/{slug}" if enabled else None
    return {"ok": True, "url": url}


@app.get("/api/videos/{vid}/file")
def video_file(vid: int, kind: str = "final", download: int = 0, user=Depends(require_user)):
    v = _get_video(vid)
    p = v["raw_path"] if kind == "raw" else v["final_path"]
    if not p or not Path(p).exists():
        raise HTTPException(404, "영상 파일이 없습니다.")
    fname = re.sub(r"[\\/:*?\"<>|]", "_", v["title"]) + ("_원본" if kind == "raw" else "") + ".mp4"
    return FileResponse(p, media_type="video/mp4",
                        filename=fname if download else None,
                        content_disposition_type="attachment" if download else "inline")


@app.get("/api/videos/{vid}/thumb")
def video_thumb(vid: int, user=Depends(require_user)):
    v = _get_video(vid)
    if not v["thumb_path"] or not Path(v["thumb_path"]).exists():
        raise HTTPException(404)
    return FileResponse(v["thumb_path"], media_type="image/jpeg")


# =====================================================================
# 환자용 공유 페이지 (로그인 없이 열림)
# =====================================================================
SHARE_TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{title} · {heading}</title>
<style>
:root{{--bg:#F4F7FB;--card:#fff;--ink:#0F172A;--muted:#475569;--brand:#1D4ED8;--line:#E2E8F0}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;line-height:1.6}}
main{{max-width:720px;margin:0 auto;padding:20px 16px 40px}}
.org{{display:flex;align-items:center;gap:10px;color:var(--brand);font-weight:700;font-size:15px}}
.org img{{height:28px;width:auto}}
h1{{font-size:22px;margin:6px 0 16px;letter-spacing:-.01em}}
.video{{background:#0B1220;border-radius:16px;overflow:hidden;display:flex;justify-content:center}}
video{{width:100%;max-height:78vh;display:block;background:#0B1220}}
.placeholder{{aspect-ratio:16/9;width:100%;display:grid;place-items:center;color:#94A3B8;font-size:14px}}
.notice{{margin-top:12px;background:#EEF2FF;border:1px solid #C7D2FE;border-radius:12px;padding:12px 14px;
font-size:14px;color:#312E81;white-space:pre-line}}
.msg{{margin-top:14px;white-space:pre-line;font-size:16px;color:var(--muted)}}
footer{{margin-top:28px;font-size:12px;color:#94A3B8}}
</style></head><body><main>
<div class="org">{logo}<span>{heading}</span></div>
<h1>{title}</h1>
<div class="video">{video}</div>
<div class="notice">ⓘ {ai_notice}</div>
<div class="msg">{message}</div>
<footer>{heading}</footer>
</main></body></html>"""


def render_share(page, title, video_src, preview=False):
    e = html.escape
    logo = '<img src="/api/logo" alt="" onerror="this.remove()">' if get_setting("logo_file") else ""
    if video_src:
        video = f'<video controls playsinline preload="metadata" src="{e(video_src)}"></video>'
    else:
        video = '<div class="placeholder">영상이 여기에 나옵니다</div>'
    return SHARE_TEMPLATE.format(title=e(title), heading=e(page["heading"]), logo=logo, video=video,
                                 ai_notice=e(page["ai_notice"]), message=e(page["message"]))


def _shared(slug):
    with db() as c:
        r = row(c.execute("SELECT * FROM videos WHERE share_slug=? AND share_enabled=1", (slug,)).fetchone())
    if not r or r["status"] != "done" or not r["final_path"] or not Path(r["final_path"]).exists():
        return None
    return r


@app.get("/v/{slug}", response_class=HTMLResponse)
def shared_page(slug: str):
    r = _shared(slug)
    if not r:
        return HTMLResponse("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                            "<p style='font-family:sans-serif;padding:24px'>링크가 꺼졌거나 없는 영상입니다. 병원에 문의해 주세요.</p>",
                            status_code=404)
    return HTMLResponse(render_share(share_page_settings(), r["title"], f"/v/{slug}/video"))


@app.get("/v/{slug}/video")
def shared_video(slug: str):
    r = _shared(slug)
    if not r:
        raise HTTPException(404)
    return FileResponse(r["final_path"], media_type="video/mp4")


# =====================================================================
# 화면 파일
# =====================================================================
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
