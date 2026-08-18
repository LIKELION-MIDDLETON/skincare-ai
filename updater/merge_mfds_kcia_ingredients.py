# -*- coding: utf-8 -*-
"""식약처 화장품 원료성분정보와 KCIA 성분사전 병합.

인증키는 파일에 저장하지 않고 --service-key 또는 MFDS_SERVICE_KEY로 받는다.
식약처 원본 스냅샷과 KCIA 기준의 통합 CSV를 각각 생성한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen


BASE_URL = (
    "https://apis.data.go.kr/1471000/"
    "CsmtcsIngdCpntInfoService01/getCsmtcsIngdCpntInfoService01"
)
MFDS_FIELDS = [
    "INGR_KOR_NAME",
    "INGR_ENG_NAME",
    "CAS_NO",
    "ORIGIN_MAJOR_KOR_NAME",
    "INGR_SYNONYM",
]
OUT_FIELDS = [
    "성분코드",
    "성분명",
    "영문명",
    "CAS",
    "구명칭",
    "배합목적",
    "MFDS_국문명",
    "MFDS_영문명",
    "MFDS_CAS",
    "MFDS_기원및정의",
    "MFDS_이명",
    "MFDS_매칭기준",
    "MFDS_존재여부",
]


def clean(value: object) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\ufeff", "")
    return re.sub(r"\s+", "", value).strip().casefold()


def display(value: object) -> str:
    return "" if value is None else str(value).strip()


def api_get(service_key: str, page: int, rows: int) -> dict:
    # The supplied key may already be URL encoded. Decode once, then encode
    # through urlencode so '+' and '=' are handled correctly.
    params = {
        "serviceKey": unquote(service_key),
        "pageNo": page,
        "numOfRows": rows,
        "type": "json",
    }
    request = Request(f"{BASE_URL}?{urlencode(params)}", headers={"User-Agent": "liontone-mfds-loader/1.0"})
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    header = payload.get("header") or {}
    if str(header.get("resultCode")) != "00":
        raise RuntimeError(f"MFDS API error {header.get('resultCode')}: {header.get('resultMsg')}")
    return payload


def fetch_all(service_key: str, page_size: int, delay: float) -> list[dict]:
    first = api_get(service_key, 1, page_size)
    body = first.get("body") or {}
    total = int(body.get("totalCount") or 0)
    items = list(body.get("items") or [])
    total_pages = (total + page_size - 1) // page_size
    print(f"MFDS 전체 {total:,}건, {total_pages}페이지 수집 시작", file=sys.stderr)

    for page in range(2, total_pages + 1):
        payload = api_get(service_key, page, page_size)
        items.extend((payload.get("body") or {}).get("items") or [])
        if page == total_pages or page % 5 == 0:
            print(f"  {min(len(items), total):,}/{total:,}", file=sys.stderr)
        if delay:
            time.sleep(delay)

    # Keep the API's first-seen order, while removing exact duplicate records.
    unique = []
    seen = set()
    for item in items:
        key = tuple(display(item.get(field)) for field in MFDS_FIELDS)
        if key not in seen:
            seen.add(key)
            unique.append({field: display(item.get(field)) for field in MFDS_FIELDS})
    return unique


def read_kcia(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_indices(kcia_rows: list[dict]):
    indices = {field: defaultdict(list) for field in ("kor", "old", "eng", "cas")}
    for index, row in enumerate(kcia_rows):
        values = {
            "kor": row.get("성분명"),
            "old": row.get("구명칭"),
            "eng": row.get("영문명"),
            "cas": row.get("CAS"),
        }
        for field, value in values.items():
            key = clean(value)
            if key:
                indices[field][key].append(index)
    return indices


def match_mfds(item: dict, indices) -> tuple[int | None, str]:
    # Strongest match first. Only accept alias/English/CAS matches when unique.
    candidates = [
        ("국문명", "kor", item.get("INGR_KOR_NAME")),
        ("구명칭", "old", item.get("INGR_KOR_NAME")),
        ("이명", "old", item.get("INGR_SYNONYM")),
        ("영문명", "eng", item.get("INGR_ENG_NAME")),
        ("CAS", "cas", item.get("CAS_NO")),
    ]
    for label, index_name, value in candidates:
        key = clean(value)
        if not key:
            continue
        matches = indices[index_name].get(key, [])
        if len(matches) == 1:
            return matches[0], label
    return None, "신규_MFDS"


def merge(kcia_rows: list[dict], mfds_rows: list[dict]) -> tuple[list[dict], dict]:
    indices = build_indices(kcia_rows)
    merged = []
    matched_kcia = set()
    counts = defaultdict(int)

    for item in mfds_rows:
        index, reason = match_mfds(item, indices)
        if index is None:
            row = {field: "" for field in OUT_FIELDS}
            row.update(
                {
                    "성분명": item["INGR_KOR_NAME"],
                    "영문명": item["INGR_ENG_NAME"],
                    "CAS": item["CAS_NO"],
                    "MFDS_국문명": item["INGR_KOR_NAME"],
                    "MFDS_영문명": item["INGR_ENG_NAME"],
                    "MFDS_CAS": item["CAS_NO"],
                    "MFDS_기원및정의": item["ORIGIN_MAJOR_KOR_NAME"],
                    "MFDS_이명": item["INGR_SYNONYM"],
                    "MFDS_매칭기준": reason,
                    "MFDS_존재여부": "Y",
                }
            )
        else:
            kcia = kcia_rows[index]
            matched_kcia.add(index)
            row = {field: display(kcia.get(field)) for field in OUT_FIELDS[:6]}
            row.update(
                {
                    "MFDS_국문명": item["INGR_KOR_NAME"],
                    "MFDS_영문명": item["INGR_ENG_NAME"],
                    "MFDS_CAS": item["CAS_NO"],
                    "MFDS_기원및정의": item["ORIGIN_MAJOR_KOR_NAME"],
                    "MFDS_이명": item["INGR_SYNONYM"],
                    "MFDS_매칭기준": reason,
                    "MFDS_존재여부": "Y",
                }
            )
        counts[reason] += 1
        merged.append(row)

    # Preserve KCIA-only rows so the output is a union, not an MFDS-only table.
    for index, kcia in enumerate(kcia_rows):
        if index in matched_kcia:
            continue
        row = {field: "" for field in OUT_FIELDS}
        row.update({field: display(kcia.get(field)) for field in OUT_FIELDS[:6]})
        row["MFDS_매칭기준"] = "KCIA_only"
        row["MFDS_존재여부"] = "N"
        merged.append(row)

    stats = {
        "kcia_rows": len(kcia_rows),
        "mfds_rows": len(mfds_rows),
        "matched_kcia_rows": len(matched_kcia),
        "mfds_only_rows": counts["신규_MFDS"],
        "kcia_only_rows": len(kcia_rows) - len(matched_kcia),
        "match_rules": dict(counts),
        "merged_rows": len(merged),
    }
    return merged, stats


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-key", default=os.getenv("MFDS_SERVICE_KEY"))
    parser.add_argument(
        "--kcia",
        default="oliveyoung_data/성분/kcia_성분사전.csv",
    )
    parser.add_argument(
        "--mfds-out",
        default="oliveyoung_data/성분/mfds_화장품_원료성분정보.csv",
    )
    parser.add_argument(
        "--merged-out",
        default="oliveyoung_data/성분/kcia_mfds_성분사전_병합.csv",
    )
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args()
    if not args.service_key:
        parser.error("--service-key 또는 MFDS_SERVICE_KEY가 필요합니다.")
    if not 1 <= args.page_size <= 500:
        parser.error("--page-size는 식약처 API 제한에 따라 1~500이어야 합니다.")

    kcia_path = Path(args.kcia)
    kcia_rows = read_kcia(kcia_path)
    mfds_rows = fetch_all(args.service_key, args.page_size, args.delay)
    merged_rows, stats = merge(kcia_rows, mfds_rows)

    write_csv(Path(args.mfds_out), mfds_rows, MFDS_FIELDS)
    write_csv(Path(args.merged_out), merged_rows, OUT_FIELDS)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"식약처 원본: {args.mfds_out}")
    print(f"병합 결과: {args.merged_out}")


if __name__ == "__main__":
    main()
