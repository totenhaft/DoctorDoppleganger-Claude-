"""원고 다루기: 문장 나누기, 단계 검사, SRT 읽기, 길이 추정."""
import re

from .config import (CHARS_PER_SEC, MAX_SCRIPT_CHARS, MAX_STEP_TITLE, MAX_STEPS,
                     MAX_TITLE)

_SENT_END = re.compile(r"(?<=[.!?。！？…])[\"'”’)\]」』]*\s+|\n+")


def split_sentences(text: str):
    """문장 끝(마침표·물음표·느낌표) 또는 줄바꿈에서 나눕니다."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENT_END.split(text)]
    return [p for p in parts if p]


def lang_key(code: str) -> str:
    return (code or "ko").split("-")[0].lower()


def nospace_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s or ""))


def estimate_seconds(steps, language="ko-KR") -> float:
    rate = CHARS_PER_SEC.get(lang_key(language), CHARS_PER_SEC["default"])
    chars = sum(nospace_len(s.get("body", "")) for s in steps)
    pauses = sum(len(split_sentences(s.get("body", ""))) for s in steps) * 0.35
    return round(chars / rate + pauses + 1.0, 1)


def joined_script(steps) -> str:
    """아바타가 실제로 읽을 전체 원고 (단계 제목은 읽지 않음)"""
    return "\n\n".join(s["body"].strip() for s in steps if s.get("body", "").strip())


def clean_steps(steps):
    """단계 목록을 정리하고 문제가 있으면 ValueError"""
    if not isinstance(steps, list) or not steps:
        raise ValueError("단계가 하나 이상 있어야 합니다.")
    if len(steps) > MAX_STEPS:
        raise ValueError(f"단계는 {MAX_STEPS}개까지 만들 수 있습니다.")
    out = []
    for i, s in enumerate(steps, 1):
        title = str(s.get("title") or "").strip()
        body = str(s.get("body") or "").strip()
        if not body:
            raise ValueError(f"{i}단계 말할 내용을 입력해 주세요.")
        if len(title) > MAX_STEP_TITLE:
            raise ValueError(f"{i}단계 제목은 {MAX_STEP_TITLE}자까지 쓸 수 있습니다.")
        if "<" in title + body or ">" in title + body:
            raise ValueError(f"{i}단계 문구에 < > 기호는 쓸 수 없습니다.")
        out.append({"title": title, "body": body})
    total = sum(len(s["body"]) for s in out)
    if total > MAX_SCRIPT_CHARS:
        raise ValueError(f"단계를 합친 원고가 {total}자입니다. {MAX_SCRIPT_CHARS}자 이하로 줄여 주세요.")
    return out


def clean_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise ValueError("제목을 입력해 주세요.")
    if len(title) > MAX_TITLE:
        raise ValueError(f"제목은 {MAX_TITLE}자까지 쓸 수 있습니다.")
    if "<" in title or ">" in title:
        raise ValueError("제목에 < > 기호는 쓸 수 없습니다.")
    return title


# ---------------- SRT ----------------
_TC = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")


def _secs(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_srt(text: str):
    """[(시작초, 끝초, 글), ...]"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.strip().split("\n") if l.strip()]
        for i, line in enumerate(lines):
            m = _TC.search(line)
            if m:
                g = m.groups()
                body = " ".join(re.sub(r"<[^>]+>|\{[^}]+\}", "", l).strip() for l in lines[i + 1:])
                if body.strip():
                    cues.append((_secs(*g[:4]), _secs(*g[4:]), body.strip()))
                break
    return cues
