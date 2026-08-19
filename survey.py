"""사용자의 피부 상태를 자유 서술형 텍스트가 아닌, 정해진 객관식 설문으로 입력받기 위한 모듈.

기존에는 `--text "볼에 붉은 좁쌀 여드름이..."` 처럼 자유 텍스트를 그대로 LLM에 넘겼지만,
이 모듈은 공통 설문 문항(SURVEY_QUESTIONS)을 정의하고, 사용자가 고른 선택지들을
LLM 프롬프트용 텍스트로 변환하는 `answers_to_text()`를 제공한다.

프론트/서버 파트에서는 SURVEY_QUESTIONS를 그대로 문항 정의로 사용해 UI(라디오/체크박스)를
구성하고, 사용자가 고른 답을 아래와 같은 dict로 모아 pipeline.run()에 넘기면 된다.

    answers = {
        "skin_type": "지성",
        "main_concern": ["여드름/뾰루지", "블랙헤드/모공"],
        "duration": "1~4주",
        "location": ["볼", "코(T존)"],
        "sensitivity": "가끔 그렇다",
        "history": "없음",
        "etc_note": "선크림만 바꿔도 트러블이 나요",  # 자유 입력(선택)
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Union

AnswerValue = Union[str, List[str]]


@dataclass
class SurveyQuestion:
    id: str
    question: str
    options: List[str]
    multi: bool = False          # True면 복수 선택 가능
    allow_etc: bool = False      # True면 "기타(직접 입력)" 선택 시 자유 텍스트 추가 입력


# ---- 공통 피부 상태 설문 문항 ----
SURVEY_QUESTIONS: List[SurveyQuestion] = [
    SurveyQuestion(
        id="skin_type",
        question="피부 타입은 어떻게 되나요?",
        options=["건성", "지성", "복합성(T존 지성/볼 건성)", "수부지(속건조 지성)", "민감성", "잘 모르겠음"],
    ),
    SurveyQuestion(
        id="main_concern",
        question="가장 신경 쓰이는 고민은 무엇인가요?",
        options=[
            "여드름/뾰루지",
            "블랙헤드/모공",
            "홍조/붉은기",
            "건조함/각질",
            "색소침착/기미",
            "주름/탄력저하",
            "가려움/따가움",
            "특별한 고민 없음",
        ],
        multi=True,
    ),
    SurveyQuestion(
        id="duration",
        question="위 고민은 얼마나 지속되었나요?",
        options=["해당 없음", "1주 이내", "1~4주", "1~3개월", "3개월 이상"],
    ),
    SurveyQuestion(
        id="location",
        question="주로 어느 부위에 나타나나요?",
        options=["이마", "코(T존)", "볼", "턱", "눈가", "얼굴 전체", "해당 없음"],
        multi=True,
    ),
    SurveyQuestion(
        id="sensitivity",
        question="새로운 화장품을 사용하면 트러블(자극/뾰루지 등)이 잘 생기나요?",
        options=["전혀 그렇지 않다", "가끔 그렇다", "자주 그렇다"],
    ),
    SurveyQuestion(
        id="history",
        question="피부 질환으로 진단받은 적이 있나요?",
        options=["없음", "아토피피부염", "여드름(중증)", "지루성피부염", "건선", "기타(직접 입력)"],
        allow_etc=True,
    ),
]

_QUESTIONS_BY_ID: Dict[str, SurveyQuestion] = {q.id: q for q in SURVEY_QUESTIONS}


def validate_answers(answers: Dict[str, AnswerValue]) -> None:
    """answers의 각 값이 해당 문항의 options 안에 있는지 검증한다. (프론트 검증 누락 대비 서버측 방어)"""
    for qid, value in answers.items():
        if qid == "etc_note":
            continue
        q = _QUESTIONS_BY_ID.get(qid)
        if q is None:
            raise ValueError(f"알 수 없는 설문 문항 id: {qid}")
        values = value if isinstance(value, list) else [value]
        if not q.multi and len(values) > 1:
            raise ValueError(f"'{q.question}' 문항은 단일 선택만 가능합니다.")
        invalid = [v for v in values if v not in q.options]
        if invalid:
            raise ValueError(f"'{q.question}' 문항에 허용되지 않은 답변: {invalid}")


# ---- 추천 API(유정님 파트, skincare-ai) 연동용 변환 ----
# 유정님 쪽 Survey 스키마(main.py)는 문항을 1부터 시작하는 정수 코드로 받고,
# 필드명도 우리와 다르다. 두 SURVEY_QUESTIONS의 옵션 "순서"가 코드표와 일치하도록
# 맞춰뒀으므로, 옵션의 리스트 인덱스(+1)를 그대로 코드로 쓰면 된다.
_BACKEND_FIELD_MAP: Dict[str, str] = {
    "skin_type": "skin_type",
    "main_concern": "concerns",
    "duration": "duration",
    "location": "areas",
    "sensitivity": "irritation",
    "history": "diagnosed",
}


def answers_to_recommend_survey(answers: Dict[str, AnswerValue]) -> Dict[str, Union[int, List[int]]]:
    """설문 답변(한글 라벨) dict를 skincare-ai `/recommend`의 survey 스키마(정수 코드)로 변환한다."""
    result: Dict[str, Union[int, List[int]]] = {}
    for q in SURVEY_QUESTIONS:
        value = answers.get(q.id)
        if not value:
            continue
        backend_key = _BACKEND_FIELD_MAP[q.id]
        values = value if isinstance(value, list) else [value]
        codes = [q.options.index(v) + 1 for v in values]
        result[backend_key] = codes if q.multi else codes[0]
    return result


def answers_to_text(answers: Dict[str, AnswerValue]) -> str:
    """설문 답변 dict를 LLM 프롬프트에 넣을 자연어 텍스트로 변환한다."""
    lines = []
    for q in SURVEY_QUESTIONS:
        value = answers.get(q.id)
        if not value:
            continue
        value_text = ", ".join(value) if isinstance(value, list) else str(value)
        lines.append(f"- {q.question} -> {value_text}")

    etc_note = answers.get("etc_note")
    if etc_note:
        lines.append(f"- 추가 메모 -> {etc_note}")

    return "\n".join(lines) if lines else "(설문 응답 없음)"
