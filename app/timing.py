"""'말하는 시점 맞추기' — 원고의 각 글자가 영상 몇 초에 나오는지 계산합니다.

방법
1) HeyGen 이 같이 주는 SRT 자막(말한 시점이 들어 있음)과 원고를 글자 단위로 맞춰 봅니다.
2) SRT 가 없으면(연습 모드 등) 글자 수 비율로 시간을 나눕니다(추정).
결과는 문장별 시작·끝 시각과 글자별 시각이며, 자막을 나누고 단계 배지를 바꾸는 데 씁니다.
"""
import difflib
import unicodedata

from .textutil import split_sentences

PAUSE = 0.35  # 추정 모드에서 문장 사이 쉬는 시간(초)


def _keep(ch):
    cat = unicodedata.category(ch)
    return cat[0] in ("L", "N")  # 글자·숫자만 비교


def build_sentences(steps):
    sents = []
    for si, st in enumerate(steps):
        for s in split_sentences(st["body"]):
            sents.append({"step": si, "text": s})
    if not sents:  # 마침표가 전혀 없어도 단계 하나를 한 문장으로
        for si, st in enumerate(steps):
            sents.append({"step": si, "text": st["body"].strip()})
    return sents


def _char_times_estimate(full, duration):
    """글자 수 비율로 시간 배정"""
    n = sum(1 for ch in full if _keep(ch)) or 1
    n_sent = max(1, full.count("␞") + 1)
    lead, tail = 0.3, 0.4
    talk = max(0.5, duration - lead - tail - PAUSE * (n_sent - 1))
    per = talk / n
    t, out = lead, []
    for ch in full:
        if ch == "␞":
            t += PAUSE
            out.append(t)
            continue
        out.append(t)
        if _keep(ch):
            t += per
    return out


def _char_times_from_srt(full, cues, duration):
    # 자막 글자마다 시각 배정
    s_chars, s_times = [], []
    for start, end, text in cues:
        text = text.strip()
        L = max(1, len(text))
        for k, ch in enumerate(text):
            s_chars.append(ch)
            s_times.append(start + (end - start) * (k + 0.5) / L)
        s_chars.append(" ")
        s_times.append(end)
    norm_s = [(i, ch.lower()) for i, ch in enumerate(s_chars) if _keep(ch)]
    norm_t = [(i, ch.lower()) for i, ch in enumerate(full) if _keep(ch)]
    if not norm_s or not norm_t:
        return None
    sm = difflib.SequenceMatcher(None, "".join(c for _, c in norm_t), "".join(c for _, c in norm_s), autojunk=False)
    known = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            known[a + k] = s_times[norm_s[b + k][0]]
    matched_ratio = len(known) / len(norm_t)
    if matched_ratio < 0.3:  # 원고와 자막이 너무 다르면 추정으로
        return None
    # 맞춰지지 않은 글자는 앞뒤 사이를 직선으로 채움
    idx = sorted(known)
    times_norm = [None] * len(norm_t)
    for j in idx:
        times_norm[j] = known[j]
    first, last = idx[0], idx[-1]
    for j in range(first):
        times_norm[j] = max(0.0, known[first] - (first - j) * 0.15)
    for j in range(last + 1, len(norm_t)):
        times_norm[j] = min(duration, known[last] + (j - last) * 0.15)
    prev = first
    for j in idx[1:]:
        if j - prev > 1:
            t0, t1 = times_norm[prev], times_norm[j]
            for k in range(prev + 1, j):
                times_norm[k] = t0 + (t1 - t0) * (k - prev) / (j - prev)
        prev = j
    # 시간이 거꾸로 가지 않게
    for j in range(1, len(times_norm)):
        if times_norm[j] < times_norm[j - 1]:
            times_norm[j] = times_norm[j - 1]
    # 원래 문자열 위치(공백·문장부호 포함)로 펼치기
    out = [0.0] * len(full)
    pos = {orig: times_norm[j] for j, (orig, _) in enumerate(norm_t)}
    cur = times_norm[0]
    for i in range(len(full)):
        if i in pos:
            cur = pos[i]
        out[i] = cur
    return out


def compute(steps, cues, duration):
    sents = build_sentences(steps)
    sep = "␞"  # 문장 구분용 표시 (읽지 않음)
    full = sep.join(s["text"] for s in sents)
    times = None
    method = "estimate"
    if cues:
        times = _char_times_from_srt(full, cues, duration)
        if times:
            method = "srt"
    if times is None:
        times = _char_times_estimate(full, duration)

    pos = 0
    for s in sents:
        L = len(s["text"])
        ct = times[pos:pos + L]
        s["chars"] = [round(t, 2) for t in ct]
        s["start"] = round(max(0.0, ct[0] - 0.08), 2) if ct else 0.0
        s["end"] = round(min(duration, (ct[-1] if ct else 0) + 0.35), 2)
        pos += L + 1
    # 다음 문장 시작 전에 끝나도록
    for a, b in zip(sents, sents[1:]):
        if a["end"] > b["start"]:
            a["end"] = b["start"]
        if a["end"] <= a["start"]:
            a["end"] = round(a["start"] + 0.3, 2)

    step_times = []
    n_steps = len(steps)
    for si in range(n_steps):
        ss = [s for s in sents if s["step"] == si]
        step_times.append({"start": ss[0]["start"] if ss else None})
    # 비어 있는 단계는 앞 단계에 붙임
    for si in range(n_steps):
        if step_times[si]["start"] is None:
            step_times[si]["start"] = step_times[si - 1]["start"] if si else 0.0
    step_times[0]["start"] = 0.0
    for si in range(n_steps):
        step_times[si]["end"] = step_times[si + 1]["start"] if si + 1 < n_steps else duration
    return {"method": method, "duration": duration, "sentences": sents, "steps": step_times}


# ---------------- 하단 자막 나누기 ----------------
def caption_chunks(timings, style, portrait=False):
    """문장을 한 화면에 나올 자막 조각으로 나눕니다. [{text, start, end, step}]"""
    if style.get("caption_mode") == "manual":
        mx = int(style.get("max_chars", 25))
        mn = int(style.get("min_chars", 10))
        if portrait:
            mx = min(mx, 26)
    else:
        mx = 16 if portrait else 28
        mn = 6 if portrait else 10
    mn = min(mn, mx)
    chunks = []
    for n, s in enumerate(timings["sentences"]):
        text, ct = s["text"], s["chars"]
        pos = 0
        for p in _split_text(text, mn, mx):
            i = text.find(p, pos)
            if i < 0:
                i = pos
            start = ct[i] if i < len(ct) else s["start"]
            chunks.append({"text": p, "start": max(s["start"], start - 0.05), "step": s["step"],
                           "_sent": n, "_end": s["end"]})
            pos = i + len(p)
    for a, b in zip(chunks, chunks[1:]):
        # 같은 문장 안에서는 다음 조각이 나올 때까지, 문장이 끝나면 문장 끝까지
        a["end"] = b["start"] if a["_sent"] == b["_sent"] else min(a["_end"], b["start"])
    if chunks:
        chunks[-1]["end"] = chunks[-1]["_end"]
    for c in chunks:
        c.pop("_end", None)
        c.pop("_sent", None)
        c["start"] = round(c["start"], 2)
        c["end"] = round(max(c["end"], c["start"] + 0.4), 2)
    return chunks


def _split_text(text, mn, mx):
    if len(text) <= mx:
        return [text]
    words = text.split(" ")
    out, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= mx:
            cur = cand
            # 쉼표에서 끊을 수 있으면 끊기 (최소 글자 이상일 때)
            if cur.endswith((",", "，", "、")) and len(cur) >= mn:
                out.append(cur)
                cur = ""
            continue
        if cur:
            out.append(cur)
        while len(w) > mx:  # 띄어쓰기 없는 아주 긴 단어
            out.append(w[:mx])
            w = w[mx:]
        cur = w
    if cur:
        if out and len(cur) < mn and len(out[-1]) + 1 + len(cur) <= mx + mn // 2:
            out[-1] = out[-1] + " " + cur
        else:
            out.append(cur)
    return out
