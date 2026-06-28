"""
A1 — K-EXAONE 래퍼 (Friendli Dedicated Endpoints, OpenAI 호환).

.env:
  EXAONE_API_KEY=flp_...
  EXAONE_BASE_URL=https://api.friendli.ai/dedicated/v1
  EXAONE_MODEL=<endpoint-id>

기본 사용:
  from ai.exaone import chat, generate_docent
  print(chat("한국어로 짧은 자기소개 해줘"))
"""
from __future__ import annotations
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_BASE = os.getenv("EXAONE_BASE_URL", "https://api.friendli.ai/dedicated/v1")
_KEY = os.getenv("EXAONE_API_KEY", "")
_MODEL = os.getenv("EXAONE_MODEL", "")

_client = OpenAI(base_url=_BASE, api_key=_KEY)


def chat(
    user: str,
    system: str = "You are a helpful assistant.",
    *,
    thinking: bool = False,   # Controllable Reasoning — 끄면 응답 빠름
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """단발 채팅. reasoning은 기본 off(속도)."""
    if not _KEY or not _MODEL:
        raise RuntimeError("EXAONE_API_KEY / EXAONE_MODEL 미설정 (.env 확인)")
    resp = _client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": thinking}},
    )
    return resp.choices[0].message.content.strip()


# ── 도슨트 생성 ──────────────────────────────────────────────────────────
DOCENT_SYSTEM = (
    "너는 박물관 도슨트다. 시각장애인 관람객을 위해, 작품을 '손으로 만지며' 감상하도록 안내한다. "
    "형태·윤곽·돌출부·재질을 촉각 언어로 묘사하되, 색·시각 비유는 피한다. "
    "한국어로 6~8문장, 따뜻하고 차분한 어조. "
    "반드시 [검증된 작품 정보]에 있는 사실에만 근거하라. 거기 없는 치수·일화·세부는 지어내지 말 것. "
    "정보가 부족하면 일반적 형태 묘사에 그치고 단정하지 않는다."
)


def generate_docent(meta: dict, context: str = "") -> str:
    """작품 메타(+ RAG 컨텍스트) → 도슨트 텍스트.

    meta 예: {"title": "...", "era": "...", "type": "3d", "material": "..."}
    context: RAG로 검색된 작품 사실 (없으면 빈 문자열 — A2에서 연결).
    """
    parts = [f"작품명: {meta.get('title','')}",
             f"시대: {meta.get('era','')}",
             f"종류: {'평면 회화' if meta.get('type')=='2d' else '입체 유물'}"]
    if meta.get("material"):
        parts.append(f"재질: {meta['material']}")
    if context:
        parts.append(f"\n[검증된 작품 정보]\n{context}")
    user = "\n".join(parts) + "\n\n위 작품의 촉각 감상 도슨트를 작성해줘."
    return chat(user, system=DOCENT_SYSTEM, thinking=False, temperature=0.6, max_tokens=700)


def answer_question(meta: dict, question: str, context: str = "") -> str:
    """실시간 후속 질문 → 답변 (A1 Q&A)."""
    sys = DOCENT_SYSTEM + " 관람객의 후속 질문에 3~5문장으로 답한다."
    base = f"작품: {meta.get('title','')} ({meta.get('era','')})"
    if context:
        base += f"\n[검증된 정보]\n{context}"
    return chat(f"{base}\n\n질문: {question}", system=sys, thinking=False, max_tokens=500)


if __name__ == "__main__":
    # 연결 스모크 테스트
    print("[1] 기본 호출:", chat("한 문장으로 인사해줘.")[:120])
    print("\n[2] 도슨트:\n",
          generate_docent({"title": "금동 반가사유상", "era": "삼국시대 7세기",
                           "type": "3d", "material": "금동"}))
