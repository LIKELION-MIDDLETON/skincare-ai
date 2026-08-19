# -*- coding: utf-8 -*-
"""올리브영 리뷰 집계 라벨 수집 (증분 갱신 지원)

사용:
  python fetch_reviews.py --products ../상품별_효능_v4.csv --out 리뷰라벨.csv
  python fetch_reviews.py ... --only-new     # 기존 파일에 없는 상품만
"""
import argparse, csv, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import urllib.request

API = "https://m.oliveyoung.co.kr/review/api/v2/reviews/{}/stats"
UA  = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
FIELDS = ["건성에 좋아요","복합성에 좋아요","지성에 좋아요",
          "자극없이 순해요","보통이에요","자극이 느껴져요",
          "진정에 좋아요","보습에 좋아요","주름/미백에 좋아요"]

def fetch(goods_no, retries=2):
    for i in range(retries+1):
        try:
            req = urllib.request.Request(API.format(goods_no), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read().decode()).get("data")
            if not d: return None
            out = {"goods_no": goods_no,
                   "리뷰수": d.get("reviewCount", 0),
                   "평점": (d.get("ratingDistribution") or {}).get("averageRating")}
            for s in d.get("satisfactionStats") or []:
                for a in s.get("answerDtos") or []:
                    out[a["answerName"]] = a["answerPercentage"]
            return out
        except Exception:
            if i == retries: return None
            time.sleep(0.5 * (i+1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", required=True, help="goods_no 컬럼이 있는 CSV")
    ap.add_argument("--out", default="리뷰라벨.csv")
    ap.add_argument("--workers", type=int, default=8, help="동시 요청 수 (과하게 올리지 말 것)")
    ap.add_argument("--only-new", action="store_true", help="out 파일에 없는 상품만 수집")
    a = ap.parse_args()

    ids = sorted({r["goods_no"] for r in csv.DictReader(open(a.products, encoding="utf-8-sig"))
                  if r.get("goods_no")})
    prev = {}
    if os.path.exists(a.out):
        prev = {r["goods_no"]: r for r in csv.DictReader(open(a.out, encoding="utf-8-sig"))}
        if a.only_new:
            ids = [g for g in ids if g not in prev]
    print(f"대상 {len(ids):,}개 (기존 {len(prev):,}개)", flush=True)
    if not ids:
        print("수집할 항목 없음"); return

    res, fail, t0 = [], 0, time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, r in enumerate(ex.map(fetch, ids), 1):
            if r: res.append(r)
            else: fail += 1
            if i % 200 == 0:
                print(f"  {i:,}/{len(ids):,}  ({time.time()-t0:.0f}s)", flush=True)

    merged = dict(prev)
    for r in res: merged[r["goods_no"]] = r
    cols = ["goods_no","리뷰수","평점"] + FIELDS
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for g in sorted(merged): w.writerow(merged[g])
    print(f"완료: 성공 {len(res):,} / 실패 {fail} / 총 {len(merged):,}행 -> {a.out}"
          f"  ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()
