"""AI 원고 초안·번역 (Claude API, 선택 기능).

설정 화면에서 Anthropic API 키를 넣었을 때만 동작합니다.
환자 이름·연락처 같은 개인정보는 넣지 않도록 화면에서 안내합니다.
"""
import json
import re

from .config import DEFAULT_CLAUDE_MODEL, MAX_STEP_TITLE, MAX_STEPS
from .db import get_setting


class AIError(Exception):
    pass


def _client():
    key = get_setting("anthropic_api_key")
    if not key:
        raise AIError("설정에서 Claude(Anthropic) API 키를 먼저 등록해 주세요.")
    try:
        import anthropic
    except ImportError:
        raise AIError("anthropic 패키지가 없습니다. 명령창에서 pip install anthropic 을 실행해 주세요.")
    return anthropic.Anthropic(api_key=key), (get_setting("claude_model") or DEFAULT_CLAUDE_MODEL)


def _ask(system, prompt, max_tokens=4000):
    client, model = _client()
    try:
        msg = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                     messages=[{"role": "user", "content": prompt}])
    except Exception as e:  # 네트워크·키·모델 이름 오류 등
        raise AIError(f"Claude 요청에 실패했습니다: {e}")
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _json_from(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AIError("AI 응답을 읽지 못했습니다. 다시 시도해 주세요.")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        raise AIError("AI 응답 형식이 맞지 않습니다. 다시 시도해 주세요.")


def _steps_from(data, n=None):
    steps = []
    for s in (data.get("steps") or [])[:MAX_STEPS]:
        body = str(s.get("body") or "").strip().replace("<", "").replace(">", "")
        title = str(s.get("title") or "").strip().replace("<", "").replace(">", "")[:MAX_STEP_TITLE]
        if body:
            steps.append({"title": title, "body": body})
    if not steps:
        raise AIError("AI 가 원고를 만들지 못했습니다. 주제를 조금 더 구체적으로 적어 주세요.")
    return steps


SYSTEM_DRAFT = (
    "당신은 안과 병원의 환자 안내 원고 작성 도우미입니다. 원장님 아바타가 직접 읽는 짧은 안내 영상 원고를 씁니다. "
    "규칙: 1) 환자가 듣기 쉬운 말투(존댓말), 한 문장은 짧게, 문장마다 마침표로 끝냅니다. "
    "2) 메모에 없는 구체적 수치·약 이름·기간은 지어내지 말고, 필요하면 '안내받은 대로'처럼 일반적으로 씁니다. "
    "3) 진단·처방을 대신하는 표현은 쓰지 않습니다. "
    "4) 반드시 JSON 하나만 출력합니다: {\"steps\":[{\"title\":\"짧은 단계 제목(15자 이내)\",\"body\":\"아바타가 읽을 문장들\"}]}"
)


def draft(topic, memo, n_steps, org_name, language_label):
    n_steps = max(1, min(MAX_STEPS, int(n_steps or 3)))
    prompt = (
        f"병원명: {org_name}\n원고 언어: {language_label}\n안내 주제: {topic}\n"
        f"참고 메모: {memo or '(없음)'}\n단계 수: {n_steps}\n\n"
        f"첫 단계는 병원 인사로 시작하고, 마지막 단계는 궁금한 점은 병원에 문의하라는 문장으로 끝내 주세요. "
        f"전체 길이는 읽는 데 1~2분 정도가 되게 해 주세요."
    )
    return _steps_from(_json_from(_ask(SYSTEM_DRAFT, prompt)))


SYSTEM_TRANSLATE = (
    "You translate patient-education scripts for an eye clinic. Keep medical meaning exact, keep the tone polite and simple, "
    "keep one sentence per sentence and end every sentence with the target language's sentence-final punctuation. "
    "Do not add or remove information. Output ONLY JSON: {\"title\":\"...\",\"steps\":[{\"title\":\"...\",\"body\":\"...\"}]}"
)


def translate(title, steps, target_label, org_name_target):
    payload = json.dumps({"title": title, "steps": steps}, ensure_ascii=False)
    prompt = (f"Target language: {target_label}\nClinic name to use in the target language: {org_name_target}\n\n"
              f"Translate this JSON:\n{payload}")
    data = _json_from(_ask(SYSTEM_TRANSLATE, prompt, max_tokens=6000))
    return str(data.get("title") or title).strip()[:60], _steps_from(data)
