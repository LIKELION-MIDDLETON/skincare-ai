# -*- coding: utf-8 -*-
"""화장품 추천 API v5 — 피부분석(CNN+LLM) + 설문을 그대로 입력받음"""
from dotenv import load_dotenv
load_dotenv()  # .env의 OPENAI_API_KEY(추천이유 생성용) 등을 읽어옴

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import ml_engine as E
from survey_map import apply as apply_survey, SKIN_TYPE, CONCERN

app = FastAPI(title="스킨케어 패키지 추천 API", version="5.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
CLASSES=["acne_rosacea","atopic_dermatitis","eczema","fungal_infection",
         "normal","pigmentation_disorder","psoriasis_lichen_planus","urticaria"]

# ---------- 입력 스키마 (피부분석 결과 그대로) ----------
class TopK(BaseModel):
    label: str
    confidence: float

class CnnResult(BaseModel):
    predicted_label: str
    confidence: float
    top_k: List[TopK] = []

class LlmResult(BaseModel):
    summary: Optional[str] = None
    likely_conditions: List[str] = []
    reasoning: Optional[str] = None
    care_recommendations: List[str] = []
    need_professional_care: Optional[bool] = None
    disclaimer: Optional[str] = None

class Survey(BaseModel):
    skin_type: Optional[int] = Field(None, ge=1, le=6, description="1건성 2지성 3복합성 4수부지 5민감성 6모름")
    concerns: List[int] = Field(default_factory=list, description="1여드름 2모공 3홍조 4건조 5색소 6주름 7가려움 8없음")
    duration: Optional[int] = Field(None, ge=1, le=5)
    areas: List[int] = Field(default_factory=list)
    irritation: Optional[int] = Field(None, ge=1, le=3, description="1전혀 2가끔 3자주")
    diagnosed: Optional[int] = Field(None, ge=1, le=6)

class Req(BaseModel):
    cnn_result: CnnResult
    llm_result: Optional[LlmResult] = None
    survey: Optional[Survey] = None
    budget_total: Optional[int] = None
    alpha: float = Field(0.6, ge=0, le=1)

def to_probs(cnn: CnnResult) -> Dict[str,float]:
    """top_k가 일부만 와도 나머지를 균등 분배해 확률 벡터 복원"""
    p={c:0.0 for c in CLASSES}
    for t in cnn.top_k:
        if t.label in p: p[t.label]=float(t.confidence)
    if not any(p.values()):
        if cnn.predicted_label not in p:
            raise HTTPException(400,f"알 수 없는 클래스: {cnn.predicted_label}")
        p[cnn.predicted_label]=float(cnn.confidence)
    s=sum(p.values())
    if s>1.01: raise HTTPException(400,f"확률 합이 1을 초과: {s:.3f}")
    rest=[c for c in CLASSES if p[c]==0.0]
    if rest and s<0.999:
        each=(1.0-s)/len(rest)
        for c in rest: p[c]=each
    return p

@app.get("/health")
def health(): return {"status":"ok","products":len(E.products()),"version":"5.0"}

@app.get("/meta")
def meta():
    return {"classes":CLASSES,"medical":sorted(E.MEDICAL),
            "skin_type_codes":{k:v for k,v in SKIN_TYPE.items()},
            "concern_codes":{k:v[0] for k,v in CONCERN.items()},
            "slots":[s[1] for s in E.SLOTS]}

@app.post("/recommend")
def recommend(req: Req):
    probs = to_probs(req.cnn_result)
    sv = req.survey.model_dump() if req.survey else None
    rule_adj, ml_adj, flags = apply_survey(sv)

    r = E.recommend(probs, alpha=req.alpha, budget_total=req.budget_total,
                    extra_rule=rule_adj, extra_ml=ml_adj,
                    force_unscented=flags["무향강제"],
                    prefer_unscented=flags.get("무향선호",False))
    E.attach_reasons(r)  # 실패해도 조용히 넘어감(구성[].추천이유=None) — 아래는 그대로 진행

    # LLM / 설문 기반 의료 권고 보강
    need = bool(req.llm_result and req.llm_result.need_professional_care)
    if need or flags["의료이력"] or (flags["만성"] and r["트리아지"]!="normal"):
        r["의료상담권고"]=True
    reasons=[]
    if r["트리아지"]=="의료필요": reasons.append(f"진단 결과({r['진단']})")
    if need: reasons.append("AI 분석 소견")
    if flags["의료이력"]: reasons.append(f"진단 이력({flags['의료이력']})")
    if flags["만성"]: reasons.append("증상 3개월 이상 지속")
    r["의료권고사유"]=reasons

    r["반영된설문"]={"피부타입":flags["피부타입"],"고민":flags["고민"],
                    "무향필터":"강제" if flags["무향강제"] else ("선호" if flags.get("무향선호") else "없음")}
    if req.llm_result:
        r["분석요약"]=req.llm_result.summary
        r["생활수칙"]=req.llm_result.care_recommendations
        r["고지사항"]=req.llm_result.disclaimer
    for it in r["구성"]:
        for k in ("점수","규칙점수","ML점수"): it.pop(k,None)
    r.pop("ML비중",None)
    return r
