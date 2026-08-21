"""텍스트 설명 + CNN 결과를 받아 OpenAI GPT API로 2차 종합 분석을 수행하는 모듈."""

from __future__ import annotations

import os
from typing import List

from openai import OpenAI
from pydantic import BaseModel, Field

import config

SYSTEM_PROMPT = """당신은 피부 상태 분석을 보조하는 AI 어시스턴트입니다.
입력으로는 (1) 사용자가 작성한 피부 상태에 대한 텍스트 설명과
(2) CNN 이미지 분류 모델이 예측한 결과(예측 라벨, 확률, 상위 후보)가 주어집니다.

다음 규칙을 반드시 지키세요:
- 두 정보를 종합해 가능성 있는 피부 상태를 설명하되, 이것은 참고용 정보이며 의학적 진단이 아님을 분명히 밝힙니다.
- CNN 결과의 확신도(top-1 confidence)가 낮거나 텍스트 설명과 상충하면 그 불확실성을 그대로 알려줍니다.
- CNN 예측이 "Normal"(정상)이고 텍스트 설명에도 특별한 이상이 없다면, 정상 소견임을 안심시켜 주는 톤으로 답합니다.
- sos_needed는 "피부가 갑자기 안 좋아진 것 같은" 급성/일시적 트러블(예: 갑작스러운 뾰루지, 홍조,
  모공 막힘 등)로 판단될 때만 true로 하세요. 아토피/건선처럼 오래 지속된 만성 질환이거나, 정상
  소견이거나, 판단 근거가 부족하면 false로 하고 sos_care는 빈 리스트로 둡니다. 애매하면 굳이
  추천하지 말고 false를 선택하세요.
- sos_needed가 true일 때만 sos_care에 지금 당장 시도해볼 수 있는 응급 케어 아이템을 1~3개
  담습니다. 마스크팩(진정/보습 시트팩), 코팩(모공/블랙헤드 팩), 필링(순한 각질제거), 트러블
  패치(패치형 스팟) 중 상황에 맞는 것만 고르세요.
- care_recommendations와 sos_care는 겹치지 않게 씁니다. care_recommendations에는 "손으로 만지지
  않기", "저자극 클렌저로 세안하기", "패치 테스트 먼저 하기"처럼 특정 제품군을 지칭하지 않는
  행동 습관/생활 수칙만 적고, 마스크팩/코팩/필링/패치 같은 제품군 언급은 절대 넣지 마세요
  (그건 sos_care의 역할입니다).
"""


class SkinAnalysisResult(BaseModel):
    """LLM 2차 분석 결과 스키마."""

    summary: str = Field(description="상황 요약 (한두 문장)")
    likely_conditions: List[str] = Field(description="가능성 있는 상태 후보들 (정상이면 ['정상'])")
    reasoning: str = Field(description="CNN 결과와 텍스트를 어떻게 종합했는지에 대한 설명")
    care_recommendations: List[str] = Field(
        description="생활 습관/관리 팁 (세안 방법, 자극 피하기 등). 특정 응급 아이템은 sos_care에만 "
        "담고 여기서 중복하지 않기"
    )
    need_professional_care: bool = Field(description="전문의 상담이 필요한 상태인지 여부")
    sos_needed: bool = Field(description="갑자기 악화된 것처럼 보여 즉각적인 응급 케어가 필요한지 여부")
    sos_care: List[str] = Field(
        description="sos_needed가 true일 때 추천하는 응급 케어 아이템(마스크팩/코팩/필링/패치 등). "
        "false면 빈 리스트"
    )
    disclaimer: str = Field(description="의학적 진단이 아니라는 면책 문구")


class SkinLLMAnalyzer:
    """텍스트 + CNN 결과를 받아 OpenAI GPT API로 2차 종합 분석을 수행한다."""

    def __init__(self, model: str = config.LLM_MODEL, api_key: str | None = None):
        api_key = api_key or os.getenv(config.LLM_API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"{config.LLM_API_KEY_ENV} 환경변수가 설정되어 있지 않습니다. "
                "https://platform.openai.com/api-keys 에서 발급받아 .env 파일에 넣어주세요."
            )
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def analyze(self, user_text: str, cnn_result: dict) -> dict:
        """user_text(피부 상태 설명)와 cnn_result(1차 CNN 판단)를 종합해 최종 결과를 생성한다."""
        top_k_desc = ", ".join(
            f"{c['label']}({c['confidence']:.2f})" for c in cnn_result.get("top_k", [])
        )
        user_prompt = (
            f"[사용자 텍스트 설명]\n{user_text}\n\n"
            f"[CNN 이미지 분류 결과]\n"
            f"예측 라벨: {cnn_result.get('predicted_label')}\n"
            f"확신도: {cnn_result.get('confidence')}\n"
            f"상위 후보: {top_k_desc}"
        )

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=SkinAnalysisResult,
        )

        result = completion.choices[0].message.parsed
        return result.model_dump()
