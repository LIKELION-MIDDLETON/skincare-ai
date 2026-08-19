# -*- coding: utf-8 -*-
"""ML 적합도 예측을 반영한 다중 카테고리 패키지 추천 (하이브리드)"""
import csv, os, math, re
from package_rules import SLOTS, DX, SKIN_ADJ, MEDICAL
import daily_usage
BASE=os.path.dirname(os.path.abspath(__file__))
EFF=["보습","유연","밀폐보습","장벽강화","진정","항산화","미백","주름개선",
     "피지조절","피지흡착","여드름","각질제거","자외선차단","재생","탄력"]
# 현재 수집한 카테고리를 슬롯별로 추천하므로 클렌징·팩·패치 등을
# 상품명 기준으로 일괄 제외하지 않는다. 얼굴 외 부위 제품만 공통 제외한다.
BAD=re.compile(r"(바디|body|헤어|샴푸|풋|핸드|제모|두피|네일)",re.I)

# 진단 -> ML 타깃 가중치 (리뷰 라벨로 학습된 축)
ML_W = {
 "acne_rosacea":          {"지성적합":1.0,"저자극":0.4,"진정효과":0.5},
 "pigmentation_disorder": {"미백효과":1.0,"저자극":0.3,"보습효과":0.3},
 "normal":                {"보습효과":0.7,"저자극":0.5},
 "atopic_dermatitis":     {"저자극":1.0,"진정효과":0.9,"보습효과":0.7,"건성적합":0.5},
 "eczema":                {"저자극":1.0,"진정효과":0.9,"보습효과":0.7},
 "fungal_infection":      {"저자극":0.9,"진정효과":0.6,"지성적합":0.4},
 "psoriasis_lichen_planus":{"저자극":1.0,"보습효과":0.9,"진정효과":0.8,"건성적합":0.5},
 "urticaria":             {"저자극":1.2,"진정효과":0.9},
}
ML_TARGETS=["건성적합","지성적합","저자극","진정효과","보습효과","미백효과"]

# 선스틱(문질러 바르는 고체)·선스프레이/선패치(분사·부착형)는 "1일 몇 g/ml"로
# 쪼개는 게 실사용과 안 맞아서, 1일 용량·1일 가격 대신 전체 용량과 정가를
# 그대로 보여준다.
NO_DAILY_SPLIT={"선스틱","선스프레이_선패치"}

def _fmt_daily(value, unit):
    """1일 사용량 표시 문자열. 매/개처럼 낱개 단위는 소수로 쪼갤 수 없으니
    반내림~반올림 범위(예: "1~2매")로 보여주고, ml/g처럼 계량 가능한
    단위는 그대로 소수 한 자리로 표시한다."""
    if value is None:
        return None
    if unit in ("매","개"):
        lo,hi = math.floor(value),math.ceil(value)
        return f"{lo}{unit}" if lo==hi else f"{lo}~{hi}{unit}"
    return f"{round(value,1)}{unit}"

_P=None
def products():
    global _P
    if _P is None:
        ml={}
        for r in csv.DictReader(open(os.path.join(BASE,"적합도_전상품.csv"),encoding="utf-8-sig")):
            ml[r["goods_no"]]={k:float(r[k] or 0) for k in ML_TARGETS}
            ml[r["goods_no"]]["출처"]=r["출처"]
        cap={}
        cap_path=os.path.join(BASE,"상품_용량.csv")
        if os.path.exists(cap_path):
            for r in csv.DictReader(open(cap_path,encoding="utf-8-sig")):
                try: v=float(r["용량"]) if r["용량"] else None
                except: v=None
                cap[r["goods_no"]]={"용량":v,"단위":r["단위"] or None,"원문":r["용량_원문"],
                                     "사용방법":r.get("사용방법") or ""}
        _P=[]
        for r in csv.DictReader(open(os.path.join(BASE,"상품별_효능_v4.csv"),encoding="utf-8-sig")):
            try: r["_price"]=int(r["sale_price"] or 0)
            except: r["_price"]=0
            v={e:float(r.get(e) or 0) for e in EFF}
            n=math.sqrt(sum(x*x for x in v.values())) or 1.0
            r["_v"]={k:x/n for k,x in v.items()}
            r["_com"]=int(r.get("코메도점수") or 0)
            r["_uns"]=r.get("무향판정")=="Y"
            r["_ml"]=ml.get(r["goods_no"])
            r["_cap"]=cap.get(r["goods_no"])
            _P.append(r)
    return _P

def decide(probs, th=0.35):
    top=max(probs,key=probs.get); med=sum(probs.get(c,0) for c in MEDICAL)
    if med>=th and top not in MEDICAL:
        return max(MEDICAL,key=lambda c:probs.get(c,0)), f"안전분기(질환합 {med:.2f})", probs[top]
    return top,"argmax",probs[top]

def score(p, dx, w, prof, alpha=0.6):
    """alpha: ML 비중 (0=규칙만, 1=ML만)"""
    rule=sum(wt*p["_v"].get(k,0) for k,wt in w.items())
    rule+= 0.3*(float(p.get("공인근거비율%") or 0)/100)
    if prof.get("무향"):
        if not p["_uns"]: rule-=0.6
        rule-= 0.15*min(int(p.get("알레르기유발착향") or 0),5)
    if prof.get("논코메도"): rule-= 0.25*p["_com"]
    mlw=dict(ML_W.get(dx,{}))
    if prof.get("_extra_ml"):
        for k,v in prof["_extra_ml"].items(): mlw[k]=mlw.get(k,0)+v
    ml=0.0
    if p["_ml"] and mlw:
        tot=sum(mlw.values())
        ml=sum(wt*p["_ml"][t] for t,wt in mlw.items())/(tot*100)   # 0~1 정규화
    return (1-alpha)*rule + alpha*ml*3.0, rule, ml

def recommend(probs, skin_type=None, alpha=0.6, budget_total=None,
              extra_rule=None, extra_ml=None, force_unscented=False, prefer_unscented=False):
    if isinstance(probs,str): probs={probs:1.0}
    dx,why,conf=decide(probs); prof=dict(DX[dx])
    w=dict(prof["w"])
    if skin_type in SKIN_ADJ:
        for k,v in SKIN_ADJ[skin_type].items(): w[k]=w.get(k,0)+v
    if extra_rule:
        for k,v in extra_rule.items(): w[k]=w.get(k,0)+v
    if force_unscented or prefer_unscented: prof["무향"]=True
    if extra_ml: prof["_extra_ml"]=extra_ml
    cap=budget_total//len(SLOTS) if budget_total else None
    items=[]; total=0
    for order,slot,cats in SLOTS:
        cand=[p for p in products() if p["카테고리"] in cats and not BAD.search(p["name"])]
        if force_unscented:
            hard=[p for p in cand if p["_uns"]]
            if len(hard)>=3: cand=hard          # 무향 제품만 (후보 부족 시 감점으로 fallback)
        if cap: cand=[p for p in cand if 0<p["_price"]<=cap]
        if not cand: continue
        best=max(cand,key=lambda p:score(p,dx,w,prof,alpha)[0])
        s,rule,ml=score(best,dx,w,prof,alpha)
        m=best["_ml"] or {}
        c=best["_cap"] or {}
        cap_val=c.get("용량"); cap_unit=c.get("단위") or ""
        if best["카테고리"] in NO_DAILY_SPLIT:
            일일가격,일일용량=None,None
            전체용량=f"{cap_val}{cap_unit}" if cap_val is not None else (c.get("원문") or None)
            정가=best["_price"]
        else:
            전체용량,정가=None,None
            table=daily_usage.daily_amount(best["카테고리"])
            if table and cap_val and cap_unit==table[1]:
                # 카테고리별 1일 권장량만큼 정가를 비례 배분한다(마진 없음).
                일일용량_수,단위=table
                일일가격=round(best["_price"]*일일용량_수/cap_val)
                일일용량=_fmt_daily(일일용량_수,단위)
            else:
                # 권장량 표가 없거나 단위가 안 맞으면 총용량/7로 대체한다.
                일일가격=round(best["_price"]/7)
                일일용량=_fmt_daily(cap_val/7 if cap_val is not None else None,cap_unit)
        items.append({"순서":order,"슬롯":prof["슬롯3"] if order==3 else slot,
            "goods_no":best["goods_no"],"brand":best["brand"],"name":best["name"],
            "일일가격":일일가격,"일일용량":일일용량,"전체용량":전체용량,"정가":정가,
            "점수":round(s,3),"규칙점수":round(rule,3),"ML점수":round(ml,3),
            "적합도":{k:m.get(k) for k in ML_W.get(dx,{})},"적합도출처":m.get("출처"),
            "고시":best.get("고시기능성성분",""),"무향":best["_uns"],"코메도":best["_com"]})
        total+=일일가격 if 일일가격 is not None else round(best["_price"]/7)
    return {"진단":dx,"헤드라인":f"당신은 {prof['라벨']}입니다","패키지명":f"{prof['라벨']} 패키지",
            "트리아지":prof["트리아지"],"의료상담권고":prof["트리아지"]=="의료필요",
            "요약":prof["요약"],"신뢰도":round(conf,3),"판정근거":why,"ML비중":alpha,
            "구성":items,"총액_일일":total}

def render(r):
    o=["진단 결과",r["헤드라인"],f"  {r['요약']}","",f"┌ {r['패키지명']}"]
    for it in r["구성"]:
        o.append(f"│ {it['순서']}. {it['슬롯']}")
        o.append(f"│    {it['brand']} {it['name'][:36]}")
        ad=" ".join(f"{k}{v:.0f}" for k,v in it["적합도"].items() if v is not None)
        o.append(f"│    {ad}")
        if it["일일가격"] is not None:
            cap=f" | 1일 사용량 {it['일일용량']}" if it["일일용량"] else ""
            o.append(f"│    1일 가격 {it['일일가격']:,}원{cap}")
        else:
            vol=f" ({it['전체용량']})" if it["전체용량"] else ""
            o.append(f"│    전체 가격 {it['정가']:,}원{vol}")
    o.append(f"└ 총 하루 {r['총액_일일']:,}원")
    if r["의료상담권고"]: o.append("\n⚠ 피부과 진료를 먼저 받으세요.")
    return "\n".join(o)

if __name__=="__main__":
    demo={"acne_rosacea":0.71,"pigmentation_disorder":0.12,"eczema":0.06,"psoriasis_lichen_planus":0.05,
          "fungal_infection":0.03,"atopic_dermatitis":0.02,"urticaria":0.01,"normal":0.00}
    print(render(recommend(demo,budget_total=90000)))
