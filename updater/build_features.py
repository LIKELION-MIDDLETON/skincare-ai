# -*- coding: utf-8 -*-
"""전성분 원본 -> 효능 15축 피처 CSV"""
import argparse, csv, os, sys, re, math, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser2 import parse_all, parse_pct
from resolve import resolve, key
from alias import canon

EFF=["보습","유연","밀폐보습","장벽강화","진정","항산화","미백","주름개선",
     "피지조절","피지흡착","여드름","각질제거","자외선차단","재생","탄력"]
SKIP={"제형","용제","점증","방부","유화","가용화","세정","피막","착색","향료","피부컨디셔닝"}
COM={canon(x) for x in ["미네랄오일","아이소프로필미리스테이트","아이소프로필팔미테이트","코코넛오일",
  "라우릭애씨드","미리스틱애씨드","코코아버터","페트롤라툼","올레익애씨드","시어버터","라놀린",
  "에틸헥실팔미테이트","옥틸스테아레이트","부틸스테아레이트","코코넛야자오일"]}
FRAG={canon(x) for x in ["향료","착향제","합성향료","조합향료","천연향료"]}
ALLERG={canon(x) for x in ["리모넨","리날룰","시트랄","제라니올","시트로넬올","유제놀","쿠마린",
  "벤질벤조에이트","벤질신나메이트","헥실신남알","부틸페닐메틸프로피오날","알파-아이소메틸아이오논",
  "아밀신남알","파네솔","벤질살리실레이트","아니스알코올","시트로넬알","벤질알코올"]}
ESSOIL=re.compile(r"(라벤더|로즈마리|베르가모트|유칼립투스|페퍼민트|오렌지껍질|레몬껍질|라임전초|"
                  r"제라늄|주니퍼|광곽향|일랑일랑|파출리|티트리잎오일|캐모마일꽃오일)")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",default="상품원본.csv")
    ap.add_argument("--out",default="피처.csv")
    a=ap.parse_args()
    rows=list(csv.DictReader(open(a.raw,encoding="utf-8-sig")))
    cache={}
    def R(n):
        if n not in cache: cache[n]=resolve(n)
        return cache[n]
    out=[]
    for row in rows:
        s=row.get("성분") or ""
        ings=[i for _,l in parse_all(s) for i in l]
        if not ings: continue
        sc=collections.Counter(); tags=[]; gosi=[]; cov=0; auth=0
        com=0; nall=0; neo=0; frag=False
        for idx,i in enumerate(ings):
            c=canon(i)
            if c in COM: com += 3 if idx<5 else 2 if idx<12 else 1
            if c in FRAG: frag=True
            if c in ALLERG: nall+=1
            if ESSOIL.search(i): neo+=1
            r=R(i)
            if not r: continue
            cov+=1
            if "협회" in r["근거"] or "고시" in r["근거"]: auth+=1
            if r["고시기능성"]: gosi.append(f'{r["고시기능성"]}:{r["표준명"]}')
            for t in r["효능태그"]:
                if t in SKIP: continue
                if t not in tags: tags.append(t)
                sc[t]+= 3 if idx<5 else 2 if idx<12 else 1
        rec={"goods_no":row["goods_no"],"카테고리":row.get("카테고리",""),
             "brand":row.get("brand",""),"name":row.get("name",""),
             "sale_price":row.get("sale_price",""),"주요사양":row.get("주요사양",""),
             "성분수":len(ings),"커버리지%":round(cov/len(ings)*100),
             "효능태그":"|".join(tags),"고시기능성성분":", ".join(sorted(set(gosi))),
             "표기함량":"","향료":"Y" if frag else "N","알레르기유발착향":nall,
             "에센셜오일":neo,"무향판정":"Y" if (not frag and nall==0 and neo==0) else "N",
             "코메도점수":com,"코메도성분":"","공인근거비율%":round(auth/len(ings)*100)}
        for e in EFF: rec[e]=sc.get(e,0)
        out.append(rec)
    cols=list(out[0].keys())
    with open(a.out,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(out)
    print(f"완료: {len(out):,}행 -> {a.out}")

if __name__=="__main__":
    main()
