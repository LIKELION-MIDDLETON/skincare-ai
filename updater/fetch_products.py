# -*- coding: utf-8 -*-
"""올리브영 상품 목록 + 전성분 수집 (신제품 감지용)

사용:
  python fetch_products.py --out 상품원본.csv
  python fetch_products.py --out 상품원본.csv --only-new   # 기존에 없는 상품만 상세 조회
"""
import argparse, csv, os, re, time, html
from concurrent.futures import ThreadPoolExecutor
import urllib.request, urllib.parse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
LIST = ("https://www.oliveyoung.co.kr/store/display/getMCategoryList.do"
        "?dispCatNo={cat}&prdSort=01&pageIdx={page}&rowsPerPage=48")
ARTC = "https://www.oliveyoung.co.kr/store/goods/getGoodsArtcAjax.do?goodsNo={}"

# 올리브영 카테고리
#
# 일부 카테고리는 올리브영에서 같은 dispCatNo를 공유한다.
# 이런 경우 main()에서 한 번만 조회하고, 결과 카테고리는 이름을 합쳐 기록한다.
CATEGORIES = {
 "스킨_토너":"100000100010013","에센스_세럼_엠플":"100000100010014",
 "크림":"100000100010015","로션":"100000100010016",
 "미스트_오일":"100000100010010","선크림":"100000100110006",
 "스킨케어세트":"100000100010017",
 "클렌징폼_젤":"100000100100001",
 "시트팩":"100000100090001",
 "패드":"100000100090004","페이셜백":"100000100090002",
 "코팩":"100000100090005","패치":"100000100090005",
 "선스틱":"100000100110003",
 "선스프레이_선패치":"100000100110004","선쿠션":"100000100110004",
 "립_아이리무버":"100000100100006","오일_밤":"100000100100004",
 "워터_밀크":"100000100100005","티슈_패드":"100000100100008",
 "필링_스크럼":"100000100100007",
}
FIELD_MAP = {
 "화장품법에 따라 기재해야 하는 모든 성분":"성분",
 "내용물의 용량 또는 중량":"용량_증량",
 "제품 주요 사양":"주요사양",
 "사용기한(또는 개봉 후 사용기간)":"사용기한",
 "사용방법":"사용방법",
 "화장품제조업자,화장품책임판매업자 및 맞춤형화장품판매업자":"제조업자",
 "제조국":"제조국",
}

def get(url, retries=2):
    for i in range(retries+1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception:
            if i == retries: return ""
            time.sleep(0.6*(i+1))

def strip_tags(s):
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()

def list_page(cat, page):
    t = get(LIST.format(cat=cat, page=page))
    items = []
    for m in re.finditer(r'goodsNo=([A-Z]\d{12})', t):
        items.append(m.group(1))
    return list(dict.fromkeys(items))

def detail(goods_no):
    t = get(ARTC.format(goods_no))
    if not t: return None
    out = {"goods_no": goods_no}
    for m in re.finditer(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", t, re.S):
        k, v = strip_tags(m.group(1)), strip_tags(m.group(2))
        if k in FIELD_MAP: out[FIELD_MAP[k]] = v
    return out if out.get("성분") else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="상품원본.csv")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--only-new", action="store_true")
    a = ap.parse_args()

    prev = {}
    if os.path.exists(a.out):
        prev = {r["goods_no"]: r for r in csv.DictReader(open(a.out, encoding="utf-8-sig"))}

    found = {}
    # 같은 dispCatNo를 공유하는 카테고리는 한 번만 조회한다.
    # 예: 코팩/패치, 선스프레이_선패치/선쿠션
    grouped = {}
    for name, cat in CATEGORIES.items():
        grouped.setdefault(cat, []).append(name)

    for cat, names in grouped.items():
        name = "_".join(names)
        seen_before = 0
        for p in range(1, a.max_pages+1):
            ids = list_page(cat, p)
            if not ids: break
            new = [g for g in ids if g not in found]
            for g in new: found[g] = name
            if not new: seen_before += 1
            if seen_before >= 2: break     # 같은 결과 반복 = 마지막 페이지
            time.sleep(0.3)
        print(f"  {name:<18} 누적 {len(found):,}", flush=True)

    targets = [g for g in found if not (a.only_new and g in prev)]
    print(f"목록 {len(found):,}개 / 상세 조회 {len(targets):,}개", flush=True)

    rows, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, d in enumerate(ex.map(detail, targets), 1):
            if d:
                d["카테고리"] = found[d["goods_no"]]
                rows.append(d)
            if i % 200 == 0:
                print(f"  {i:,}/{len(targets):,} ({time.time()-t0:.0f}s)", flush=True)

    merged = dict(prev)
    for r in rows: merged[r["goods_no"]] = r
    cols = ["goods_no","카테고리","주요사양","용량_증량","사용기한","사용방법","제조업자","제조국","성분"]
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for g in sorted(merged): w.writerow(merged[g])
    print(f"완료: 신규/갱신 {len(rows):,} / 총 {len(merged):,}행 -> {a.out}")

if __name__ == "__main__":
    main()
