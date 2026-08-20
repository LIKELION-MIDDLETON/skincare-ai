# -*- coding: utf-8 -*-
"""graph_reasons.py가 뽑은 성분·근거를 받아 "왜 이 상품을 추천했는지"를
OpenAI GPT로 문장화한다. model/llm_analyzer.py와 같은 구조화 출력
(response_format) 패턴을 따른다.

openai 패키지는 ReasonGenerator를 실제로 쓸 때만 임포트한다 — API 키가 없는
환경(테스트, 로컬 데모)에서 ml_engine.py를 그냥 import만 해도 깨지지 않게 하려고.
"""
from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()  # main.py를 거치지 않고 ml_engine.py를 직접 실행해도 .env를 읽게

LLM_MODEL = "gpt-4o-mini"
LLM_API_KEY_ENV = "OPENAI_API_KEY"

SYSTEM_PROMPT = """당신은 화장품 추천 이유를 설명하는 어시스턴트입니다.
각 추천 상품마다 "성분 근거" 목록(성분명, 관련 효능, 근거 강도)과, 있는 경우
식약처 직접 주장 효능이 함께 주어집니다.

다음 규칙을 반드시 지키세요:
- 주어진 성분 근거·직접 주장 목록에 없는 효능이나 성분은 절대 언급하거나 지어내지 마세요.
- 근거 강도가 "regulatory"(식약처 고시/보고)나 "official_reference"(배합목적 공식 근거)인
  성분은 단정적으로 설명해도 됩니다. "heuristic"(이름 기반 추론)인 성분은
  "~로 알려져 있다"처럼 완곡한 톤으로 쓰고, 확정적 효능 주장처럼 쓰지 마세요.
- 한 상품당 1~2문장, 존댓말로 간결하게 씁니다. 광고 문구처럼 과장하지 마세요.
"""


class ItemReason(BaseModel):
    goods_no: str
    이유: str = Field(description="근거 목록에 있는 사실만 바탕으로 한 1~2문장 추천 이유")


class PackageReasons(BaseModel):
    reasons: List[ItemReason]


class ReasonGenerator:
    def __init__(self, model: str = LLM_MODEL, api_key: str | None = None):
        api_key = api_key or os.getenv(LLM_API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"{LLM_API_KEY_ENV} 환경변수가 설정되어 있지 않습니다. "
                "https://platform.openai.com/api-keys 에서 발급받아 .env 파일에 넣어주세요."
            )
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def explain(self, diagnosis_label: str, diagnosis_summary: str, items: list[dict]) -> dict:
        """items: [{"goods_no","name","슬롯","성분근거":[{"성분","기능","근거"}],"직접주장":[...]}]
        반환: {goods_no: 이유 문장}
        """
        lines = [f"[진단] {diagnosis_label} — {diagnosis_summary}", ""]
        for it in items:
            lines.append(f"- goods_no={it['goods_no']} | {it['슬롯']} | {it['name']}")
            if it["성분근거"]:
                ev = "; ".join(f"{e['성분']}({e['기능']}, {e['근거']})" for e in it["성분근거"])
                lines.append(f"  성분 근거: {ev}")
            if it["직접주장"]:
                lines.append(f"  식약처 직접 주장: {', '.join(it['직접주장'])}")
        user_prompt = "\n".join(lines)

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=PackageReasons,
        )
        result = completion.choices[0].message.parsed
        return {r.goods_no: r.이유 for r in result.reasons}
