"""전체 파이프라인: 이미지 -> CNN 1차 판단 -> (설문 응답 + CNN 결과) -> LLM 2차 종합 분석.

사용자 입력은 자유 서술형 텍스트가 아니라 survey.py에 정의된 정해진 설문(SURVEY_QUESTIONS)에
대한 답변으로 받는다.

실행 예:
    python pipeline.py --image sample.jpg --answers '{"skin_type": "지성", "main_concern": ["여드름/뾰루지"]}'
"""

from __future__ import annotations

import argparse
import json

from cnn_infer import SkinCNNPredictor
from llm_analyzer import SkinLLMAnalyzer
from survey import answers_to_recommend_survey, answers_to_text, validate_answers


class SkinAnalysisPipeline:
    """이미지 + 설문 응답을 입력받아 CNN 1차 판단 -> LLM 2차 종합 분석까지 수행한다."""

    def __init__(self):
        self.cnn = SkinCNNPredictor()
        self.llm = SkinLLMAnalyzer()

    def run(self, image_path: str, survey_answers: dict | str, top_k: int = 3) -> dict:
        """survey_answers: survey.SURVEY_QUESTIONS 문항 id -> 선택값(str 또는 list[str]) dict.

        하위 호환을 위해 str(자유 텍스트)을 넘겨도 그대로 동작한다.
        """
        cnn_result = self.cnn.predict(image_path, top_k=top_k)

        survey_payload = None
        if isinstance(survey_answers, dict):
            validate_answers(survey_answers)
            user_text = answers_to_text(survey_answers)
            survey_payload = answers_to_recommend_survey(survey_answers)
        else:
            user_text = survey_answers  # 레거시: 자유 텍스트 그대로 사용

        llm_result = self.llm.analyze(user_text, cnn_result)

        return {
            "cnn_result": cnn_result,
            "llm_result": llm_result,
            "survey": survey_payload,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="피부 상태 분석 파이프라인 실행")
    parser.add_argument("--image", type=str, required=True, help="분석할 피부 이미지 경로")
    parser.add_argument(
        "--answers",
        type=str,
        required=True,
        help='설문 응답 JSON 문자열. 예: \'{"skin_type": "지성", "main_concern": ["여드름/뾰루지"]}\'',
    )
    args = parser.parse_args()

    pipeline = SkinAnalysisPipeline()
    result = pipeline.run(args.image, json.loads(args.answers))

    print(json.dumps(result, ensure_ascii=False, indent=2))
