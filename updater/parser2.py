# -*- coding: utf-8 -*-
"""올리브영 전성분 파서 v2 — 콤마형/공백형 자동 판별 + 구성품 분리 + 공백 포함 성분명 재결합"""
import re, csv, sys
sys.path.insert(0,'.')
from alias import canon
from rules import classify
SEP="␟"
SUFFIX=re.compile(r"(추출물|오일|수$|즙|검$|왁스|버터|알코올|애씨드|산$|추출물$|잎수|꽃수|발효물|발효여과물|껍질추출물|뿌리추출물|씨오일|열매오일|가루|분말)$")

_D=None
def _dict():
    global _D
    if _D is None:
        _D=set()
        with open('/sessions/trusting-amazing-ride/mnt/outputs/성분_효능_사전_v1.csv',encoding='utf-8-sig') as f:
            for r in csv.DictReader(f): _D.add(canon(r["성분명"]))
    return _D

def resolves(tok):
    c=canon(tok)
    return c in _dict() or classify(c) is not None

def split_components(t):
    """[구성품명] 단위로 분리. 반환: [(구성품명, 성분문자열)]"""
    t=re.sub(r"^[\s■*]+","",t or "")
    parts=re.split(r"[\[【]([^\]】]{1,40})[\]】]", t)
    if len(parts)==1: return [("", t)]
    out=[]; 
    if parts[0].strip(): out.append(("", parts[0]))
    for i in range(1,len(parts),2):
        name=parts[i].strip(); body=parts[i+1] if i+1<len(parts) else ""
        if body.strip(): out.append((name, body))
    return out or [("", t)]

def _clean(x):
    x=x.replace(SEP,",").strip(" ,.·;:\u200b")
    x=MARK.sub("",x)
    x=x.lstrip("*+※'\"[]() ")
    x=x.strip(" ,.·;:")
    x=re.sub(r"^\d+(ml|g|mg|ea)\b","",x,flags=re.I)
    if BAD.match(x): return ""
    return x

# 안내문구 컷오프 트리거
CUT=re.compile(r"(최신\s*정보|포장의?\s*성분|참고하시|변경될\s*수|고객\s*관리|고객\s*센터|상세\s*페이지\s*참조|문의\s*바랍|확인\s*바랍|표시\s*:|제공된\s*성분|본사|제품에\s*따라|무첨가|불검출|테스트\s*완료)")
# 성분명이 될 수 없는 토큰
BAD=re.compile(r"^(성분은?|동일|제품이?라?도?|경우에|따라|변경될|수|있습니다|최신정보는?|포장의?|참고하시거나|본사|고객관리지원팀으로|연락|부탁|드립니다|참조|상세페이지|및|또는|등|위|아래|주의|함유|전성분|기타|없음|해당사항|\d+|[-–—·※*+'\"\[\]()]*)$")
MARK=re.compile(r"[*+※★☆＊'\"]+$")

def split_ing(t, merge=True):
    """단일 구성품 성분문자열 -> 성분 리스트"""
    if not t: return []
    m=CUT.search(t)
    if m: t=t[:m.start()]                              # 안내문구 이후 절단
    t=re.sub(r"\([^)]*\)"," ",t)                       # (10%) (1,000ppm)
    t=re.sub(r"^[^:,]{0,25}:\s*","",t)                 # "앰플:" 헤더
    t=re.sub(r"^.{0,30}?\d+\s*(ml|g|mg|ea)\s+","",t,flags=re.I)
    t=re.sub(r"(\d),(\d)",lambda m:m.group(1)+SEP+m.group(2),t)   # 1,2- 보호
    t=t.replace("@",",").replace("｜",",")
    ncomma=t.count(",")+t.count("、")
    if ncomma>=3:                                       # 콤마형
        toks=[_clean(x).replace(" ","") for x in re.split(r"[,、]",t)]
        return [x for x in toks if x]
    # 공백형
    toks=[_clean(x) for x in re.split(r"\s+",t)]
    toks=[x for x in toks if x]
    if not merge: return toks
    # 공백 포함 성분명 재결합 (예: "에난티아 클로란타껍질추출물")
    out=[]; i=0
    while i<len(toks):
        cur=toks[i]
        # 속명+종명 분리 케이스만 결합: 짧고(<=7자) 접미사 없고 미분류인 토큰
        if (i+1<len(toks) and not resolves(cur) and len(cur)<=7
                and not SUFFIX.search(cur)):
            j2=cur+toks[i+1]
            if resolves(j2):
                out.append(j2); i+=2; continue
        out.append(cur); i+=1
    return out

def parse_all(t):
    """전체 문자열 -> [(구성품, [성분...])]"""
    return [(n, split_ing(b)) for n,b in split_components(t)]

def parse_pct(t):
    res={}
    for m in re.finditer(r"([가-힣A-Za-z0-9,\-/]+)\s*\(([^)]*?)\)", t or ""):
        name=m.group(1).split(",")[-1].strip(); body=m.group(2).replace(",","")
        p=re.search(r"([\d.]+)\s*%",body); q=re.search(r"([\d.]+)\s*ppm",body,re.I)
        if p: res[name]=float(p.group(1))
        elif q: res[name]=float(q.group(1))/10000.0
    return res
