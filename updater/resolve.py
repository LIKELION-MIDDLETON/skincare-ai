# -*- coding: utf-8 -*-
"""성분 -> 효능 해석기 (3계층: 협회 배합목적 > 식약처 고시 > 규칙추론)"""
import csv, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from alias import canon, canon_en
from purpose_map import to_tags
from rules import classify

BASE=os.path.dirname(os.path.abspath(__file__))
KCIA={}   # key -> (성분명, 영문명, 배합목적)
for r in csv.DictReader(open(BASE+'/kcia.csv',encoding='utf-8-sig')):
    rec=(r['성분명'], r['영문명'], r['배합목적'])
    for k in (r['성분명'], r['구명칭']):
        if k: KCIA.setdefault(canon(k), rec)
    if r['영문명']: KCIA.setdefault('EN:'+canon_en(r['영문명']), rec)
for r in csv.DictReader(open(BASE+'/kcia_patch.csv',encoding='utf-8')):
    KCIA[canon(r['성분명'])]=(r['성분명'],'',r['배합목적'])
GOSI={canon(r['성분명']):(r['고시기능성'],r['고시함량'])
      for r in csv.DictReader(open(BASE+'/gosi.csv',encoding='utf-8'))}

_EN=re.compile(r'^[A-Za-z0-9,\-/() ]+$')
def key(name): return 'EN:'+canon_en(name) if _EN.match(name or '') else canon(name)

def resolve(name):
    """반환: dict(효능태그, 배합목적, 고시기능성, 고시함량, 근거, INCI)"""
    k=key(name)
    out={"효능태그":[], "배합목적":"", "고시기능성":"", "고시함량":"", "근거":[], "INCI":"", "표준명":name, "비안면":False}
    rec=KCIA.get(k)
    c=canon(name)
    if rec:
        out["INCI"]=rec[1]; out["배합목적"]=rec[2]; out["표준명"]=rec[0]
        c=canon(rec[0])                      # 영문표기여도 한글 표준명 기준으로 후속 조회
        t=to_tags(rec[2])
        if "비안면" in t: out["비안면"]=True
        t=[x for x in t if x!="비안면"]       # 헤어/네일 목적은 얼굴 효능에서 제외
        if t: out["효능태그"]+=t; out["근거"].append("협회")
    if c in GOSI:
        f,amt=GOSI[c]; out["고시기능성"]=f; out["고시함량"]=amt
        if f not in out["효능태그"]: out["효능태그"].append(f)
        out["근거"].append("고시")
    # 규칙: 태그가 없거나 총칭(피부컨디셔닝)뿐일 때 보완
    if not out["효능태그"] or set(out["효능태그"])<={"피부컨디셔닝","제형"}:
        rk=classify(c)
        if rk:
            for t in rk["효능태그"].split("|"):
                if t and t not in out["효능태그"]: out["효능태그"].append(t)
            out["근거"].append("추론")
    out["효능태그"]=[t for t in out["효능태그"] if t!="피부컨디셔닝"] or (["피부컨디셔닝"] if out["배합목적"] else [])
    return out if (out["효능태그"] or out["배합목적"]) else None
