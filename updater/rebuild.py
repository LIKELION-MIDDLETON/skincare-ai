# -*- coding: utf-8 -*-
"""리뷰/상품 갱신 후 적합도_전상품.csv 재생성

  python rebuild.py --features 피처.csv --labels 리뷰라벨.csv --out 적합도_전상품.csv
  python rebuild.py ... --retrain      # 모델도 다시 학습
"""
import argparse, os, pickle, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")

EFF=["보습","유연","밀폐보습","장벽강화","진정","항산화","미백","주름개선",
     "피지조절","피지흡착","여드름","각질제거","자외선차단","재생","탄력"]
TARGETS={"건성적합":"건성에 좋아요","지성적합":"지성에 좋아요","저자극":"자극없이 순해요",
         "진정효과":"진정에 좋아요","보습효과":"보습에 좋아요","미백효과":"주름/미백에 좋아요"}
LEAVE_ON={"스킨_토너","로션","크림","패드","워터_밀크","에센스_세럼_엠플","선크림","미스트_오일"}
SCOPE={"건성적합":"all","지성적합":"all","저자극":"all","진정효과":"all",
       "보습효과":"leave_on","미백효과":"leave_on"}
MIN_REVIEW=30
PARAMS=dict(n_estimators=600,learning_rate=0.04,num_leaves=15,min_child_samples=25,
            subsample=0.8,colsample_bytree=0.7,reg_lambda=1.0,random_state=42,verbose=-1)

def featurize(f, cat_cols):
    X=pd.DataFrame(index=f.index)
    n=np.sqrt((f[EFF].astype(float)**2).sum(axis=1)).replace(0,1)
    for e in EFF: X["n_"+e]=f[e].astype(float)/n
    X["성분수"]=pd.to_numeric(f["성분수"],errors="coerce").fillna(0)
    X["커버리지"]=pd.to_numeric(f["커버리지%"],errors="coerce").fillna(0)
    X["코메도"]=pd.to_numeric(f["코메도점수"],errors="coerce").fillna(0)
    X["알레르기착향"]=pd.to_numeric(f["알레르기유발착향"],errors="coerce").fillna(0)
    X["에센셜오일"]=pd.to_numeric(f["에센셜오일"],errors="coerce").fillna(0)
    X["향료"]=(f["향료"]=="Y").astype(int)
    X["무향"]=(f["무향판정"]=="Y").astype(int)
    X["고시보유"]=(f["고시기능성성분"].fillna("")!="").astype(int)
    for c in cat_cols: X[c]=(f["카테고리"]==c[4:]).astype(int)
    return X

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--features",default="피처.csv")
    ap.add_argument("--labels",default="리뷰라벨.csv")
    ap.add_argument("--model",default="model_v4final.pkl")
    ap.add_argument("--out",default="적합도_전상품.csv")
    ap.add_argument("--retrain",action="store_true")
    a=ap.parse_args()

    f=pd.read_csv(a.features).drop_duplicates("goods_no").reset_index(drop=True)
    lab=pd.read_csv(a.labels)
    print(f"상품 {len(f):,} / 라벨 {len(lab):,}")

    if a.retrain:
        import lightgbm as lgb
        df=f.merge(lab,on="goods_no",how="inner").reset_index(drop=True)
        cat_cols=["cat_"+c for c in sorted(df["카테고리"].unique())]
        X=featurize(df,cat_cols)
        nrev=pd.to_numeric(df["리뷰수"],errors="coerce").fillna(0)
        w=np.sqrt(np.clip(nrev,1,None))
        models={}
        print("재학습:")
        for name,col in TARGETS.items():
            y=pd.to_numeric(df[col],errors="coerce")
            m=y.notna()&(nrev>=MIN_REVIEW)
            if SCOPE[name]=="leave_on": m=m&df["카테고리"].isin(LEAVE_ON)
            models[name]=lgb.LGBMRegressor(**PARAMS).fit(X[m],y[m],sample_weight=w[m])
            print(f"  {name:<8} n={m.sum():,}")
        pickle.dump({"models":models,"cols":list(X.columns)},open(a.model,"wb"))
        print(f"  -> {a.model} 저장")

    M=pickle.load(open(a.model,"rb")); models,COLS=M["models"],M["cols"]
    cat_cols=[c for c in COLS if c.startswith("cat_")]
    X=featurize(f,cat_cols)
    for c in COLS:
        if c not in X: X[c]=0
    X=X[COLS]

    out=f[["goods_no","카테고리","brand","name","sale_price"]].copy()
    for k,g in models.items(): out[k]=np.clip(g.predict(X),0,100).round(2)
    out=out.merge(lab[["goods_no","리뷰수"]+list(TARGETS.values())],on="goods_no",how="left")
    out["출처"]="예측"
    for k,v in TARGETS.items():
        real=pd.to_numeric(out[v],errors="coerce")
        use=real.notna()&(pd.to_numeric(out["리뷰수"],errors="coerce").fillna(0)>=MIN_REVIEW)
        out.loc[use,k]=real[use]; out.loc[use,"출처"]="실측"
    out=out.drop(columns=list(TARGETS.values()))
    out.to_csv(a.out,index=False,encoding="utf-8-sig")
    print(f"완료: {len(out):,}행 (실측 {(out['출처']=='실측').sum():,} / 예측 {(out['출처']=='예측').sum():,}) -> {a.out}")

if __name__=="__main__":
    main()
