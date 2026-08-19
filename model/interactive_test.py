"""파이프라인을 한 번만 로드해두고 이미지+설문 응답을 반복 입력하며 테스트하는 스크립트.

매번 pipeline.py를 새로 실행하면 CNN 체크포인트 로딩이 반복돼 느리므로,
모델을 한 번만 메모리에 올려둔 채 여러 번 테스트할 때 사용한다.

기존에는 "피부 상태 설명"을 자유 텍스트로 입력받았지만, 이제는 survey.py에 정의된
정해진 설문 문항(SURVEY_QUESTIONS)에 번호로 답하는 방식으로 입력받는다.

실행:
    python interactive_test.py
    (이미지 경로에 빈 입력 또는 Ctrl+C로 종료)
"""

import json

from pipeline import SkinAnalysisPipeline
from survey import SURVEY_QUESTIONS


def ask_survey() -> dict:
    """SURVEY_QUESTIONS를 순서대로 물어보고 답변 dict를 만든다."""
    answers: dict = {}

    for q in SURVEY_QUESTIONS:
        print(f"\n{q.question}")
        for i, opt in enumerate(q.options, start=1):
            print(f"  {i}. {opt}")
        hint = "번호를 쉼표로 구분해 복수 선택 (예: 1,3)" if q.multi else "번호 하나 선택 (예: 1)"
        print(f"  ({hint}, 빈 입력 시 건너뛰기)")

        while True:
            raw = input("> ").strip()
            if not raw:
                break
            try:
                idxs = [int(x.strip()) for x in raw.split(",") if x.strip()]
                if not q.multi and len(idxs) > 1:
                    print("이 문항은 하나만 선택해주세요.")
                    continue
                selected = [q.options[i - 1] for i in idxs]
            except (ValueError, IndexError):
                print(f"1~{len(q.options)} 사이의 번호로 입력해주세요.")
                continue

            answers[q.id] = selected if q.multi else selected[0]

            if q.allow_etc and any(s.startswith("기타") for s in selected):
                etc = input("기타 내용을 직접 입력해주세요: ").strip()
                if etc:
                    answers["etc_note"] = etc
            break

    return answers


if __name__ == "__main__":
    print("모델 로딩 중...")
    pipeline = SkinAnalysisPipeline()
    print("준비 완료. 이미지 경로에 빈 입력 또는 Ctrl+C로 종료.\n")

    while True:
        image_path = input("이미지 경로: ").strip()
        if not image_path:
            break

        answers = ask_survey()

        try:
            result = pipeline.run(image_path, answers)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(f"[오류] {exc}")
        print()
