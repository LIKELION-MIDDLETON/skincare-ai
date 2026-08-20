# -*- coding: utf-8 -*-
"""올리브영 크롤링 원본(용량_증량)에서 상품별 대표 용량을 파싱한다.

한 상품이 여러 카테고리 페이지에 중복 수집돼 있을 수 있어 goods_no당
값이 있는 첫 원문 하나만 대표로 쓴다. 원문은 "본품 100ml / 증정 30ml"처럼
구성품·증정품이 함께 나열되는 경우가 많아, 관례상 맨 앞에 오는 본품 용량인
첫 번째 "숫자+단위" 토큰만 뽑는다(매/EA 같은 개수 단위도 허용).

시트팩·코팩·패치·패드·티슈_패드처럼 낱개로 밀봉 포장된 상품은 실제 사용
단위가 "매(장)"인데, 크롤링 원문이 "30ml*10"(장당 내용물 30ml × 10장)처럼
장당 용량을 먼저 적는 경우가 많다. 위 일반 규칙을 그대로 적용하면 "300ml"로
잘못 읽혀서(장 단위 대신 내용물 총량으로 계산됨) 1일 사용량이 실제와 전혀
다른 값이 나온다. 그래서 이 카테고리들은 "매/장" 표기를 최우선으로 찾고,
없으면 "<용량><단위> x <개수>" 꼴에서 뒤의 개수를 매수로 해석한다.

동시에 `사용방법` 원문도 goods_no당 하나씩 함께 뽑아 둔다.

사용:
  python build_capacity.py --raw ../oliveyoung_data --out ../상품_용량.csv
"""
import argparse, csv, glob, os, re

UNIT_MAP = {"ml": "ml", "g": "g", "kg": "kg", "매": "매", "ea": "개"}
CAP_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|g|G|kg|KG|매|EA|ea)")
# "30ml*10ea", "24ml X 10EA" 처럼 개당 용량 x 개수로 표기된 경우 총량으로 환산한다.
MULT_RE = re.compile(r"^\s*[*xX×]\s*(\d+)")

# "데이 75ml / 나이트 75ml", "본품 15ml/ 리필 15ml 2입"처럼 "/"로 나뉜 서로
# 다른 이름의 구성품 2개가 실제로 같이 담겨 오는 경우, 첫 토큰(관례상 본품
# 용량)만 뽑으면 실제 총 용량의 절반 이하로 잡혀서 1일가격이 그만큼(최대
# 수 배) 부풀려진다. "증정/기획/사은품" 등은 이미 상위 필터(ml_engine.is_bundle)
# 에서 후보 자체를 통째로 빼므로, 여기서는 "/" 딱 2조각으로만 나뉘고 각
# 조각이 "<라벨> <숫자><단위>[<N>입|개]" 꼴로 깔끔하게 끝나는(다른 잡음이
# 없는) 경우로만 한정해 합산한다 — "60mL / 60mL*2 / 150ml / ..." 처럼 실제로는
# 구성품이 아니라 구매 옵션이 여러 개 나열된 경우는 조각이 3개 이상이라
# 여기 안 걸리고 기존 로직(첫 토큰)으로 폴백한다.
PAIR_SKIP_LABELS = re.compile(r"(증정|사은품|기획|미니|트래블|여행|키트|단품|대용량|옵션)")
_PAREN_RE = re.compile(r"\([^)]*\)")
_PART_RE = re.compile(
    r"^\s*([가-힣A-Za-z][가-힣A-Za-z\s]{0,15}?)\s*[:：]?\s*"
    r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|g|G)\s*(.*)$"
)
_PART_MULT_RE = re.compile(r"^(\d+)\s*(입|개)$")


def _parse_pair_part(part):
    raw = part.strip()
    if PAIR_SKIP_LABELS.search(raw):
        return None  # "(증정)", "(본품)" 처럼 괄호 안에 붙은 표시도 괄호를 지우기 전에 먼저 걸러낸다
    part = _PAREN_RE.sub("", raw).strip()
    m = _PART_RE.match(part)
    if not m:
        return None
    label, num, unit, rest = m.groups()
    label = label.strip()
    if PAIR_SKIP_LABELS.search(label):
        return None
    val = float(num)
    rest = rest.strip()
    if rest:
        mm = _PART_MULT_RE.match(rest)
        if not mm:
            return None  # 못 알아듣는 꼬리표가 남으면 안전하게 포기
        val *= int(mm.group(1))
    return label, val, UNIT_MAP[unit.lower()]


def parse_capacity_pair(text):
    """"라벨 숫자단위 / 라벨 숫자단위" 2조각을 합산한다. 조건이 안 맞으면 None."""
    if not text or "/" not in text:
        return None
    parts = text.split("/")
    if len(parts) != 2:
        return None
    parsed = [_parse_pair_part(p) for p in parts]
    if any(p is None for p in parsed):
        return None
    (l1, v1, u1), (l2, v2, u2) = parsed
    if u1 != u2 or l1 == l2:
        return None
    return v1 + v2, u1

# 카테고리 폴더/파일명(=상품별_효능_v4.csv의 "카테고리" 값)이 이 목록에
# 속하면 매(장) 수 우선 파싱을 적용한다. 페이셜백(워시오프 클레이/버블팩 등)은
# 낱개 포장이 아니라 실제로 ml/g 내용물이 맞아서 제외한다.
SHEET_CATEGORIES = {"시트팩", "코팩", "패치", "패드", "티슈_패드"}
SHEET_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(매|장)")
EA_ONLY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(EA|ea)")


def parse_capacity_sheet(text):
    """매(장) 수를 우선으로 뽑는다. 못 찾으면 None (호출부에서 일반 로직으로 폴백)."""
    if not text:
        return None
    t = text.strip()
    m = SHEET_UNIT_RE.search(t)
    if m:
        return float(m.group(1)), "매"
    # "30ml*10"처럼 <용량><단위> 뒤에 곱셈 기호+개수만 오는 경우, 그 개수를 매수로 본다.
    m2 = CAP_RE.search(t)
    if m2 and UNIT_MAP[m2.group(2).lower()] in ("ml", "g", "kg"):
        mm = MULT_RE.match(t[m2.end():])
        if mm:
            return float(mm.group(1)), "매"
    m3 = EA_ONLY_RE.search(t)
    if m3:
        return float(m3.group(1)), "매"
    return None


def parse_capacity(text, category=None):
    if not text:
        return None
    if category in SHEET_CATEGORIES:
        r = parse_capacity_sheet(text)
        if r:
            return r
    r = parse_capacity_pair(text)
    if r:
        return r
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
        cat = os.path.splitext(os.path.basename(f))[0].removesuffix("_result")
        for row in csv.DictReader(open(f, encoding="utf-8-sig")):
            gn = row.get("goods_no")
            if not gn:
                continue
            rec = raw_by_goods.setdefault(gn, {})
            v = (row.get("용량_증량") or "").strip()
            if v and "용량_증량" not in rec:
                rec["용량_증량"] = v
                rec["카테고리"] = cat
            u = (row.get("사용방법") or "").strip()
            if u and "사용방법" not in rec:
                rec["사용방법"] = u

    out = []
    parsed = 0
    for gn, rec in raw_by_goods.items():
        raw = rec.get("용량_증량", "")
        r = parse_capacity(raw, rec.get("카테고리")) if raw else None
        val, unit = r if r else ("", "")
        if r:
            parsed += 1
        out.append({"goods_no": gn, "용량_원문": raw, "용량": val, "단위": unit,
                     "사용방법": rec.get("사용방법", "")})

    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["goods_no", "용량_원문", "용량", "단위", "사용방법"])
        w.writeheader()
        w.writerows(out)
    print(f"완료: {len(out):,}행 중 {parsed:,}행 파싱 성공 -> {a.out}")


if __name__ == "__main__":
    main()
