# -*- coding: utf-8 -*-
"""피부 분석 API — 백엔드가 호출하는 HTTP 서버

기존 pipeline.py를 감싸기만 함. 모델 코드는 건드리지 않음.

실행:
    uvicorn server:app --host 0.0.0.0 --port 8001
"""
import os, tempfile, json, logging
from typing import Dict, List, Union, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pipeline import SkinAnalysisPipeline
from survey import SURVEY_QUESTIONS, validate_answers

log = logging.getLogger("skin-analysis")
app = FastAPI(title="피부 분석 API", version="1.0",
              description="이미지 + 설문 → CNN 1차 판단 → LLM 2차 종합 분석")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_BYTES = 10 * 1024 * 1024        # 10MB

_pipeline: Optional[SkinAnalysisPipeline] = None
def get_pipeline() -> SkinAnalysisPipeline:
    """모델은 최초 요청 시 1회만 로드 (기동 시간 단축)"""
    global _pipeline
    if _pipeline is None:
        log.info("모델 로딩 시작")
        _pipeline = SkinAnalysisPipeline()
        log.info("모델 로딩 완료")
    return _pipeline


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _pipeline is not None}


@app.get("/survey")
def survey_schema():
    """설문 문항 스키마. 프론트가 화면 그릴 때 사용."""
    return {"questions": [
        {"id": q.id, "question": q.question, "options": list(q.options),
         "multi": q.multi, "allow_etc": getattr(q, "allow_etc", False)}
        for q in SURVEY_QUESTIONS
    ]}


@app.post("/analyze")
async def analyze(
    image: UploadFile = File(..., description="얼굴 피부 사진"),
    answers: str = Form("{}", description='설문 응답 JSON. 예: {"skin_type":"지성","main_concern":["여드름/뾰루지"]}'),
    top_k: int = Form(3),
):
    """반환값을 그대로 추천 API(/recommend)에 POST하면 됨."""
    if image.content_type not in ALLOWED:
        raise HTTPException(400, f"지원하지 않는 이미지 형식: {image.content_type}")

    try:
        parsed = json.loads(answers) if answers else {}
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"answers JSON 파싱 실패: {e}")
    if not isinstance(parsed, dict):
        raise HTTPException(400, "answers는 JSON 객체여야 합니다")
    if parsed:
        try:
            validate_answers(parsed)
        except ValueError as e:
            raise HTTPException(400, str(e))

    data = await image.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"이미지가 too large ({len(data)//1024//1024}MB). 최대 10MB")
    if not data:
        raise HTTPException(400, "빈 이미지 파일")

    suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data); tmp.close()
        result = get_pipeline().run(tmp.name, parsed, top_k=top_k)
    except Exception as e:
        log.exception("분석 실패")
        raise HTTPException(500, f"분석 중 오류: {type(e).__name__}: {e}")
    finally:
        try: os.unlink(tmp.name)
        except OSError: pass

    return result
