"""'꾸미기 입히기' — 아바타 영상 위에 병원명·단계 배지·하단 자막·로고를 얹습니다.

방법
1) Pillow 로 글자·배지·로고를 투명 PNG 그림으로 그립니다.
2) ffmpeg 로 그 그림들을 정해진 시간에만 영상 위에 겹쳐 새 mp4 를 만듭니다.

초보자 메모: ffmpeg 는 따로 설치해야 합니다 (README 참고).
"""
import json
import math
import os
import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import BASE_DIR, FONT_DIR, LOGO_DIR, STEP_COLORS
from .timing import caption_chunks


class ComposeError(Exception):
    pass


# ---------------- ffmpeg 찾기 ----------------
def _tool(name):
    exe = name + (".exe" if platform.system() == "Windows" else "")
    local = BASE_DIR / "ffmpeg" / "bin" / exe          # 프로그램 폴더 안에 둔 경우
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if found:
        return found
    raise ComposeError(f"{name} 을(를) 찾지 못했습니다. README 의 'ffmpeg 설치'를 따라 설치해 주세요.")


def ffmpeg_ok():
    try:
        _tool("ffmpeg")
        _tool("ffprobe")
        return True
    except ComposeError:
        return False


def run(cmd, cwd=None, timeout=3600):
    flags = 0x08000000 if platform.system() == "Windows" else 0  # 윈도우에서 검은 창 안 뜨게
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=flags, stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ComposeError(f"ffmpeg 가 {timeout // 60}분 안에 끝나지 않았습니다.")
    if p.returncode != 0:
        tail = (p.stderr or "")[-1200:]
        raise ComposeError(f"ffmpeg 실행 실패:\n{tail}")
    return p.stdout


def probe(path):
    out = run([_tool("ffprobe"), "-v", "error", "-show_entries",
               "stream=codec_type,width,height:format=duration", "-of", "json", str(path)])
    d = json.loads(out)
    w = h = None
    has_audio = False
    for s in d.get("streams", []):
        if s.get("codec_type") == "video" and w is None:
            w, h = s.get("width"), s.get("height")
        if s.get("codec_type") == "audio":
            has_audio = True
    dur = float(d.get("format", {}).get("duration") or 0)
    if not w:
        raise ComposeError("영상 정보를 읽지 못했습니다.")
    return w, h, dur, has_audio


# ---------------- 글꼴 ----------------
_CANDIDATES = {
    "regular": [
        ("C:/Windows/Fonts/malgun.ttf", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
    ],
    "bold": [
        ("C:/Windows/Fonts/malgunbd.ttf", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 6),
    ],
    "black": [
        ("C:/Windows/Fonts/malgunbd.ttf", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
    ],
}


def _weight_key(weight):
    w = int(weight or 700)
    return "regular" if w < 600 else ("bold" if w < 800 else "black")


def font_file(name, weight):
    """(파일경로, ttc번호)"""
    if name and name != "default":
        p = FONT_DIR / Path(name).name
        if p.exists():
            return str(p), 0
    # 프로그램 폴더 fonts/ 에 Pretendard 를 넣어 두면 그것을 먼저 씀
    local = {"regular": "Pretendard-Medium.otf", "bold": "Pretendard-Bold.otf", "black": "Pretendard-ExtraBold.otf"}
    lp = BASE_DIR / "fonts" / local[_weight_key(weight)]
    if lp.exists():
        return str(lp), 0
    for path, idx in _CANDIDATES[_weight_key(weight)] + _CANDIDATES["bold"] + _CANDIDATES["regular"]:
        if os.path.exists(path):
            return path, idx
    raise ComposeError("한글 글꼴을 찾지 못했습니다. 프로그램 폴더의 fonts/ 에 Pretendard 글꼴을 넣어 주세요.")


@lru_cache(maxsize=64)
def _font(path, idx, size):
    return ImageFont.truetype(path, size=max(8, int(size)), index=idx)


def get_font(name, weight, size):
    p, i = font_file(name, weight)
    return _font(p, i, int(size))


# ---------------- 그리기 도우미 ----------------
def rgba(hex_color, opacity=100):
    h = (hex_color or "#000000").lstrip("#")
    if len(h) != 6:
        h = "000000"
    a = max(0, min(255, round(255 * float(opacity) / 100)))
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


def _text_w(font, text, stroke=0):
    l, t, r, b = font.getbbox(text, stroke_width=stroke)
    return r - l


def wrap_lines(text, font, max_w, stroke=0):
    """픽셀 폭을 넘으면 띄어쓰기 기준으로 줄을 나눕니다 (최대 2줄 권장)."""
    if _text_w(font, text, stroke) <= max_w:
        return [text]
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if _text_w(font, cand, stroke) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    # 두 줄이면 길이를 비슷하게
    if len(lines) == 2:
        best = lines
        best_diff = abs(_text_w(font, lines[0]) - _text_w(font, lines[1]))
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            if _text_w(font, a, stroke) <= max_w and _text_w(font, b, stroke) <= max_w:
                d = abs(_text_w(font, a) - _text_w(font, b))
                if d < best_diff:
                    best, best_diff = [a, b], d
        lines = best
    return lines


def caption_image(lines, style, scale, align="center"):
    """하단 자막 그림 (투명 배경 PNG)"""
    size = float(style.get("font_size", 54)) * scale
    font = get_font(style.get("font"), style.get("font_weight", 700), size)
    stroke = max(0, round(float(style.get("stroke_width", 0)) * scale))
    lh = float(style.get("line_height", 1.25))
    asc, desc = font.getmetrics()
    line_h = int((asc + desc) * lh)
    widths = [_text_w(font, ln, stroke) for ln in lines]
    tw, th = max(widths), line_h * (len(lines) - 1) + asc + desc
    pad_x = int(28 * scale) if style.get("box") else int(12 * scale)
    pad_y = int(14 * scale) if style.get("box") else int(8 * scale)
    sh = int(float(style.get("shadow_distance", 0)) * scale + float(style.get("shadow_blur", 0)) * scale * 2) if style.get("shadow") else 0
    m = sh + stroke + 4
    W, H = tw + 2 * (pad_x + m), th + 2 * (pad_y + m)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def xpos(i):
        if align == "left":
            return m + pad_x
        if align == "right":
            return W - m - pad_x - widths[i]
        return (W - widths[i]) // 2

    if style.get("box"):
        box = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle([m, m, W - m, H - m], radius=int(14 * scale),
                                              fill=rgba(style.get("box_color"), style.get("box_opacity", 55)))
        img.alpha_composite(box)

    if style.get("shadow"):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        ang = math.radians(float(style.get("shadow_angle", 45)))
        dist = float(style.get("shadow_distance", 4)) * scale
        dx, dy = round(math.cos(ang) * dist), round(math.sin(ang) * dist)
        col = rgba(style.get("shadow_color"), style.get("shadow_opacity", 60))
        for i, ln in enumerate(lines):
            d.text((xpos(i) + dx, m + pad_y + i * line_h + dy), ln, font=font, fill=col,
                   stroke_width=stroke, stroke_fill=col)
        blur = float(style.get("shadow_blur", 0)) * scale
        if blur > 0:
            layer = layer.filter(ImageFilter.GaussianBlur(blur / 2))
        img.alpha_composite(layer)

    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((xpos(i), m + pad_y + i * line_h), ln, font=font, fill=rgba(style.get("color", "#FFFFFF")),
               stroke_width=stroke, stroke_fill=rgba(style.get("stroke_color", "#000000")))
    return _apply_opacity(img, style.get("opacity", 100))


def _apply_opacity(img, opacity):
    op = float(opacity if opacity is not None else 100)
    if op >= 100:
        return img
    a = img.getchannel("A").point(lambda v: int(v * op / 100))
    img.putalpha(a)
    return img


def pill(parts, scale, bg, radius=None, pad=(22, 12), dot=None):
    """[(글, 글꼴, 색)] 을 둥근 알약 모양 안에 그립니다."""
    gap = int(12 * scale)
    widths = [_text_w(f, t) for t, f, _ in parts]
    asc = max(f.getmetrics()[0] for _, f, _ in parts)
    desc = max(f.getmetrics()[1] for _, f, _ in parts)
    dot_w = int(14 * scale) + gap if dot else 0
    px, py = int(pad[0] * scale), int(pad[1] * scale)
    W = px * 2 + dot_w + sum(widths) + gap * (len(parts) - 1)
    H = py * 2 + asc + desc
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=radius if radius is not None else H // 2, fill=bg)
    x = px
    if dot:
        r = int(7 * scale)
        cy = H // 2
        d.ellipse([x, cy - r, x + 2 * r, cy + r], fill=dot)
        x += dot_w
    for (t, f, col), w in zip(parts, widths):
        fa = f.getmetrics()[0]
        d.text((x, py + (asc - fa)), t, font=f, fill=col)
        x += w + gap
    return img


def step_caption_image(text, color, style, scale, max_w):
    """말 자막을 끈 경우 쓰는 '단계 자막' 박스"""
    size = float(style.get("font_size", 54)) * scale * 0.9
    font = get_font(style.get("font"), 700, size)
    lines = wrap_lines(text, font, max_w - int(80 * scale))[:2]
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.2)
    tw = max(_text_w(font, ln) for ln in lines)
    px, py, bar = int(30 * scale), int(18 * scale), int(10 * scale)
    W, H = tw + px * 2 + bar, lh * (len(lines) - 1) + asc + desc + py * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=int(16 * scale), fill=(255, 255, 255, 235))
    d.rounded_rectangle([0, 0, bar + int(16 * scale), H - 1], radius=int(16 * scale), fill=rgba(color))
    d.rectangle([bar, 0, bar + int(16 * scale), H - 1], fill=(255, 255, 255, 235))
    for i, ln in enumerate(lines):
        d.text((bar + px, py + i * lh), ln, font=font, fill=(17, 24, 39, 255))
    return img


# ---------------- 전체 배치 ----------------
def build_overlays(W, H, duration, *, steps, timings, style, org_name, title, logo_path, workdir):
    """겹칠 그림 목록 [(파일, x, y, 시작, 끝)]"""
    scale = min(W, H) / 1080
    portrait = H > W
    margin = int(40 * scale)
    out = []
    n = 0

    def save(img, x, y, t0, t1):
        nonlocal n
        name = f"o{n}.png"
        img.save(Path(workdir) / name)
        out.append((name, int(x), int(y), round(t0, 3), round(t1, 3)))
        n += 1

    def x_for(pos, w):
        if pos == "left":
            return margin
        if pos == "right":
            return W - margin - w
        return (W - w) // 2

    top = margin + int(float(style.get("badge_offset", 0)) / 100 * H)
    fs = 30 * scale
    f_bold = get_font(style.get("font"), 700, fs)
    f_reg = get_font(style.get("font"), 400, fs)

    title_img = None
    if style.get("show_title"):
        parts = []
        if org_name:
            parts.append((org_name, f_bold, (186, 214, 255, 255)))
        if title:
            parts.append((title, f_reg, (255, 255, 255, 255)))
        if parts:
            title_img = pill(parts, scale, (15, 23, 42, 190), dot=(96, 165, 250, 255))
            # 너무 길면 줄임
            limit = int(W * (0.9 if portrait else 0.6))
            if title_img.width > limit:
                t = title
                while t and title_img.width > limit:
                    t = t[:-1]
                    parts2 = [p for p in parts[:-1]] + [(t + "…", f_reg, (255, 255, 255, 255))]
                    title_img = pill(parts2, scale, (15, 23, 42, 190), dot=(96, 165, 250, 255))

    title_pos = style.get("title_pos", "left")
    step_pos = style.get("step_pos", "right")
    stacked = title_img is not None and style.get("show_step_title") and title_pos == step_pos
    # 세로 영상은 폭이 좁아서 제목과 배지를 위아래로
    if portrait and title_img is not None and style.get("show_step_title"):
        stacked = True

    if title_img is not None:
        save(title_img, x_for(title_pos, title_img.width), top, 0, duration)

    if style.get("show_step_title"):
        y = top + (title_img.height + int(14 * scale) if stacked else 0)
        pos = title_pos if stacked else step_pos   # 겹치면 제목 바로 아래 같은 쪽에
        for i, st in enumerate(steps):
            color = rgba(STEP_COLORS[i % len(STEP_COLORS)])
            label = f"{i + 1}단계" + (f" · {st['title']}" if st.get("title") else "")
            parts = [(label, f_bold, (255, 255, 255, 255))]
            img = pill(parts, scale, color)
            t0, t1 = timings["steps"][i]["start"], timings["steps"][i]["end"]
            if t1 - t0 > 0.05:
                save(img, x_for(pos, img.width), y, t0, t1)

    # 로고
    logo_h_used = 0
    if style.get("show_logo") and logo_path and Path(logo_path).exists():
        logo = Image.open(logo_path).convert("RGBA")
        lh = int(56 * scale)
        lw = int(logo.width * lh / logo.height)
        if lw > W * 0.3:
            lw = int(W * 0.3)
            lh = int(logo.height * lw / logo.width)
        logo = logo.resize((lw, lh), Image.LANCZOS)
        lx = margin if style.get("logo_pos") == "left" else W - margin - lw
        save(logo, lx, H - margin - lh, 0, duration)
        logo_h_used = lh

    # 하단 자막
    bottom = int((110 if logo_h_used else 70) * scale) + int(float(style.get("caption_offset", 0)) / 100 * H)
    max_w = int(W * 0.86)
    align = style.get("caption_align", "center")
    if style.get("speech_caption", True):
        stroke = round(float(style.get("stroke_width", 0)) * scale)
        font = get_font(style.get("font"), style.get("font_weight", 700), float(style.get("font_size", 54)) * scale)
        for ch in caption_chunks(timings, style, portrait):
            lines = wrap_lines(ch["text"], font, max_w, stroke)
            img = caption_image(lines, style, scale, align)
            x = {"left": margin - int(12 * scale), "right": W - margin - img.width + int(12 * scale)}.get(
                align, (W - img.width) // 2)
            save(img, x, H - bottom - img.height, ch["start"], ch["end"])
    elif style.get("step_caption"):
        for i, st in enumerate(steps):
            first = [s for s in timings["sentences"] if s["step"] == i]
            text = first[0]["text"] if first else st["body"][:40]
            img = step_caption_image(text, STEP_COLORS[i % 4], style, scale, max_w)
            t0, t1 = timings["steps"][i]["start"], timings["steps"][i]["end"]
            save(img, x_for(align, img.width), H - bottom - img.height, t0, t1)
    return out


def compose(raw_path, out_path, thumb_path, *, steps, timings, style, org_name, title, logo_path, workdir):
    W, H, dur, has_audio = probe(raw_path)
    Path(workdir).mkdir(parents=True, exist_ok=True)
    for f in Path(workdir).glob("o*.png"):
        f.unlink()
    overlays = build_overlays(W, H, dur, steps=steps, timings=timings, style=style,
                              org_name=org_name, title=title, logo_path=logo_path, workdir=workdir)
    raw_abs = str(Path(raw_path).resolve())
    out_abs = str(Path(out_path).resolve())
    cmd = [_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", raw_abs]
    for name, *_ in overlays:
        cmd += ["-i", name]
    if overlays:
        chain, prev = [], "[0:v]"
        for k, (name, x, y, t0, t1) in enumerate(overlays, start=1):
            lab = f"[v{k}]"
            chain.append(f"{prev}[{k}:v]overlay={x}:{y}:enable='between(t,{t0},{t1})'{lab}")
            prev = lab
        graph = ";".join(chain)
        cmd += ["-filter_complex", graph, "-map", prev]
    else:
        cmd += ["-map", "0:v"]
    if has_audio:
        cmd += ["-map", "0:a", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", out_abs]
    run(cmd, cwd=workdir)
    make_thumb(out_path, thumb_path, dur)
    return dur


def make_thumb(video_path, thumb_path, dur=None):
    if dur is None:
        dur = probe(video_path)[2]
    t = max(0.0, min(dur - 0.1, dur * 0.3))
    run([_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
         "-i", str(video_path), "-frames:v", "1", "-vf", "scale=480:-2", str(thumb_path)])


def logo_file_path(name):
    if not name:
        return None
    p = LOGO_DIR / Path(name).name
    return str(p) if p.exists() else None
