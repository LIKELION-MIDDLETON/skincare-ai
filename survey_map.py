# -*- coding: utf-8 -*-
"""설문 응답 -> 효능 가중치 / 제약 매핑"""

SKIN_TYPE = {1:"건성", 2:"지성", 3:"복합성", 4:"수부지", 5:"민감성", 6:None}

# 피부타입별 규칙 가중치 보정
SKIN_ADJ = {
 "건성":  {"보습":1.5,"장벽강화":1.0,"밀폐보습":1.0,"피지조절":-1.0,"피지흡착":-1.5},
 "지성":  {"피지조절":1.5,"피지흡착":1.0,"밀폐보습":-1.5,"유연":-1.0},
 "복합성":{"보습":0.5,"피지조절":0.5},
 # 수부지 = 속건조 지성 : 보습과 피지조절을 동시에, 단 유분은 억제
 "수부지":{"보습":1.8,"장벽강화":1.2,"피지조절":1.2,"피지흡착":0.5,"밀폐보습":-1.2,"유연":-1.0},
 "민감성":{"진정":1.5,"장벽강화":1.0,"각질제거":-1.5,"미백":-0.8},
}
# 피부타입별 ML 축 보정
SKIN_ML = {
 "건성":{"건성적합":0.6},"지성":{"지성적합":0.6},"복합성":{},
 "수부지":{"지성적합":0.4,"보습효과":0.5},"민감성":{"저자극":0.8},
}

CONCERN = {
 1:("여드름/뾰루지",  {"여드름":2.0,"피지조절":1.5,"진정":1.0,"밀폐보습":-1.0}, {"지성적합":0.4}),
 2:("블랙헤드/모공",  {"피지조절":1.8,"피지흡착":1.2,"각질제거":0.8,"밀폐보습":-1.0}, {"지성적합":0.5}),
 3:("홍조/붉은기",    {"진정":2.5,"장벽강화":1.5,"각질제거":-1.5}, {"저자극":0.7,"진정효과":0.6}),
 4:("건조함/각질",    {"보습":2.0,"장벽강화":1.5,"밀폐보습":0.8}, {"보습효과":0.7,"건성적합":0.4}),
 5:("색소침착/기미",  {"미백":2.5,"항산화":1.5}, {"미백효과":0.8}),
 6:("주름/탄력저하",  {"주름개선":2.0,"탄력":1.0,"항산화":1.0}, {"미백효과":0.3}),
 7:("가려움/따가움",  {"진정":3.0,"장벽강화":2.0,"각질제거":-2.5,"미백":-1.0}, {"저자극":1.0,"진정효과":0.7}),
 8:("특별한 고민 없음", {}, {}),
}
DURATION = {1:"해당 없음",2:"1주 이내",3:"1~4주",4:"1~3개월",5:"3개월 이상"}
AREA = {1:"이마",2:"코(T존)",3:"볼",4:"턱",5:"눈가",6:"얼굴 전체",7:"해당 없음"}
# 자극 민감도 -> 무향 강제 여부 + 저자극 ML 가중
IRRITATION = {1:(0,0.0),2:(1,0.5),3:(2,1.2)}   # 0없음 1감점 2하드필터
# 진단 이력 -> 의료 플래그
DIAGNOSED = {1:(None,False),2:("아토피피부염",True),3:("여드름(중증)",True),
             4:("지루성피부염",True),5:("건선",True),6:("기타",False)}

def apply(survey):
    """반환: (rule_adj, ml_adj, flags)"""
    rule={}; ml={}; flags={"무향강제":False,"무향선호":False,"의료이력":None,
                           "피부타입":None,"고민":[],"만성":False}
    if not survey: return rule,ml,flags
    st=SKIN_TYPE.get(survey.get("skin_type") or 0)
    flags["피부타입"]=st
    if st:
        for k,v in SKIN_ADJ.get(st,{}).items(): rule[k]=rule.get(k,0)+v
        for k,v in SKIN_ML.get(st,{}).items():  ml[k]=ml.get(k,0)+v
        if st=="민감성": flags["무향강제"]=True
    if 7 in (survey.get("concerns") or []) or 3 in (survey.get("concerns") or []):
        flags["무향선호"]=True
    for c in (survey.get("concerns") or []):
        if c not in CONCERN: continue
        nm,rw,mw=CONCERN[c]; flags["고민"].append(nm)
        for k,v in rw.items(): rule[k]=rule.get(k,0)+v
        for k,v in mw.items(): ml[k]=ml.get(k,0)+v
    ir=survey.get("irritation")
    if ir in IRRITATION:
        lvl,w=IRRITATION[ir]
        if lvl>=2: flags["무향강제"]=True
        elif lvl==1: flags["무향선호"]=True
        if w: ml["저자극"]=ml.get("저자극",0)+w
    dg=survey.get("diagnosed")
    if dg in DIAGNOSED:
        nm,med=DIAGNOSED[dg]; flags["의료이력"]=nm
        if med: flags["무향강제"]=True
    if (survey.get("duration") or 0)>=5: flags["만성"]=True
    return rule,ml,flags
