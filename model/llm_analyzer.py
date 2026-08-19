"""텍스트 설명 + CNN 결과를 받아 Gemini 무료 API로 2차 종합 분석을 수행하는 모듈."""

from __future__ import annotations

import os
from typing import List

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

import config

SYSTEM_PROMPT = """당신은 피부 상태 분석을 보조하는 AI 어시스턴트입니다.
입력으로는 (1) 사용자가 작성한 피부 상태에 대한 텍스트 설명과
(2) CNN 이미지 분류 모델이 예측한 결과(예측 라벨, 확률, 상위 후보)가 주어집니다.

다음 규칙을 반드시 지키세요:
- 두 정보를 종합해 가능성 있는 피부 상태를 설명하되, 이것은 참고용 정보이며 의학적 진단이 아님을 분명히 밝힙니다.
- CNN 결과의 확신도(top-1 confidence)가 낮거나 텍스트 설명과 상충하면 그 불확실성을 그대로 알려줍니다.
- CNN 예측이 "Normal"(정상)이고 텍스트 설명에도 특별한 이상이 없다면, 정상 소견임을 안심시켜 주는 톤으로 답합니다.
"""


class SkinAnalysisResult(BaseModel):
    """LLM 2차 분석 결과 스키마."""

    summary: str = Field(description="상황 요약 (한두 문장)")
    likely_conditions: List[str] = Field(description="가능성 있는 상태 후보들 (정상이면 ['정상'])")
    reasoning: str = Field(description="CNN 결과와 텍스트를 어떻게 종합했는지에 대한 설명")
    care_recommendations: List[str] = Field(description="생활 관리 팁 등 일반적인 권장 사항")
    need_professional_care: bool = Field(description="전문의 상담이 필요한 상태인지 여부")
    disclaimer: str = Field(description="의학적 진단이 아니라는 면책 문구")


class SkinLLMAnalyzer:
    """텍스트 + CNN 결과를 받아 Gemini 무료 API로 2차 종합 분석을 수행한다."""

    def __init__(self, model: str = config.LLM_MODEL, api_key: str | None = None):
        api_key = api_key or os.getenv(config.LLM_API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"{config.LLM_API_KEY_ENV} 환경변수가 설정되어 있지 않습니다. "
                "https://aistudio.google.com/apikey 에서 무료로 발급받아 .env 파일에 넣어주세요."
            )
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def analyze(self, user_text: str, cnn_result: dict) -> dict:
        """user_text(피부 상태 설명)와 cnn_result(1차 CNN 판단)를 종합해 최종 결과를 생성한다."""
        top_k_desc = ", ".join(
            f"{c['label']}({c['confidence']:.2f})" for c in cnn_result.get("top_k", [])
        )
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"[사용자 텍스트 설명]\n{user_text}\n\n"
            f"[CNN 이미지 분류 결과]\n"
            f"예측 라벨: {cnn_result.get('predicted_label')}\n"
            f"확신도: {cnn_result.get('confidence')}\n"
            f"상위 후보: {top_k_desc}"
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SkinAnalysisResult,
            ),
        )

        result = SkinAnalysisResult.model_validate_json(response.text)
        return result.model_dump()
