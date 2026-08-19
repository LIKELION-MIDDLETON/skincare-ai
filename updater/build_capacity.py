# -*- coding: utf-8 -*-
"""올리브영 크롤링 원본(용량_증량)에서 상품별 대표 용량을 파싱한다.

한 상품이 여러 카테고리 페이지에 중복 수집돼 있을 수 있어 goods_no당
값이 있는 첫 원문 하나만 대표로 쓴다. 원문은 "본품 100ml / 증정 30ml"처럼
구성품·증정품이 함께 나열되는 경우가 많아, 관례상 맨 앞에 오는 본품 용량인
첫 번째 "숫자+단위" 토큰만 뽑는다(매/EA 같은 개수 단위도 허용).

사용:
  python build_capacity.py --raw ../oliveyoung_data --out ../상품_용량.csv
"""
import argparse, csv, glob, os, re

UNIT_MAP = {"ml": "ml", "g": "g", "kg": "kg", "매": "매", "ea": "개"}
CAP_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|g|G|kg|KG|매|EA|ea)")
# "30ml*10ea", "24ml X 10EA" 처럼 개당 용량 x 개수로 표기된 경우 총량으로 환산한다.
MULT_RE = re.compile(r"^\s*[*xX×]\s*(\d+)")


def parse_capacity(text):
    if not text:
        return None
    t = text.strip()
    m = CAP_RE.search(t)
    if not m:
        return None
    val = float(m.group(1))
    unit = UNIT_MAP[m.group(2).lower()]
    if unit in ("ml", "g", "kg"):
        mm = MULT_RE.match(t[m.end():])
        if mm:
            val *= int(mm.group(1))
    return val, unit


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(here, "..", "oliveyoung_data"))
    ap.add_argument("--out", default=os.path.join(here, "..", "상품_용량.csv"))
    a = ap.parse_args()

    raw_by_goods = {}
    for f in sorted(glob.glob(os.path.join(a.raw, "*", "*.csv"))):
        for row in csv.DictReader(open(f, encoding="utf-8-sig")):
            gn = row.get("goods_no")
            v = (row.get("용량_증량") or "").strip()
            if gn and v and gn not in raw_by_goods:
                raw_by_goods[gn] = v

    out = []
    parsed = 0
    for gn, raw in raw_by_goods.items():
        r = parse_capacity(raw)
        val, unit = r if r else ("", "")
        if r:
            parsed += 1
        out.append({"goods_no": gn, "용량_원문": raw, "용량": val, "단위": unit})

    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["goods_no", "용량_원문", "용량", "단위"])
        w.writeheader()
        w.writerows(out)
    print(f"완료: {len(out):,}행 중 {parsed:,}행 파싱 성공 -> {a.out}")


if __name__ == "__main__":
    main()
