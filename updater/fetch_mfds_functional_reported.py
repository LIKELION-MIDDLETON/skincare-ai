# -*- coding: utf-8 -*-
"""식약처 기능성화장품 보고품목정보 수집기.

인증키는 코드에 저장하지 않는다. 프로젝트 루트 .env의 MFDS_SERVICE_KEY,
환경변수, --service-key 또는 숨김 입력 프롬프트 순서로 읽는다.

기본 실행:
    python3 updater/fetch_mfds_functional_reported.py

선택 필터:
    python3 updater/fetch_mfds_functional_reported.py --item-name "나이아신아마이드"
"""
from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://apis.data.go.kr/1471000/FtnltCosmRptPrdlstInfoService"
OPERATION = "getRptPrdlstInq"
ENDPOINT = f"{BASE_URL}/{OPERATION}"
PAGE_SIZE_MAX = 500
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

# 식약처 API 명세의 주요 출력 필드. API에 새 필드가 추가되면 CSV에도 자동 반영한다.
KNOWN_FIELDS = [
    "COSMETIC_REPORT_SEQ",
    "ITEM_SEQ",
    "ITEM_NAME",
    "DEPT_RECEIPT_NO",
    "REPORT_FLAG_CODE",
    "REPORT_FLAG_NAME",
    "MANUF_NAME",
    "MANUF_COUNTRY_CODE",
    "MANUF_COUNTRY_NAME",
    "MANUF_PLACE",
    "ITEM_PH",
    "COSMETIC_TARGET_FLAG",
    "COSMETIC_TARGET_FLAG_NAME",
    "COSMETIC_STD_CODE",
    "COSMETIC_STD_NAME",
    "ENTP_NAME",
    "ENTP_SEQ",
    "REPORT_DATE",
    "CANCEL_REQ_DATE",
    "CANCEL_APPROVAL_DATE",
    "CANCEL_APPROVAL_YN",
    "ETHANOL_OVER_YN",
    "EE_CODE",
    "EE_NAME",
    "SPF",
    "PA",
    "USAGE_DOSAGE",
    "EFFECT_YN1",
    "EFFECT_YN2",
    "EFFECT_YN3",
    "WATER_PROOFING_FLAG",
    "WATER_PROOFING_NAME",
    "EE_DOC_DATA",
    "UD_DOC_DATA",
    "NB_DOC_DATA",
]


def load_env_file(path: Path = ENV_PATH) -> None:
    """외부 의존성 없이 프로젝트 루트 .env를 읽는다.

    이미 설정된 프로세스 환경변수는 .env 값으로 덮어쓰지 않는다.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def get_service_key(value: str | None) -> str:
    load_env_file()
    if value:
        return value.strip()
    env_key = os.getenv("MFDS_SERVICE_KEY")
    if env_key:
        return env_key.strip()
    entered = getpass.getpass("식약처 일반 인증키를 입력하세요(화면에 표시되지 않음): ")
    if not entered.strip():
        raise SystemExit("인증키가 입력되지 않았습니다.")
    return entered.strip()


def request_page(
    service_key: str,
    page_no: int,
    num_of_rows: int,
    item_name: str = "",
    item_seq: str = "",
    cosmetic_report_seq: str = "",
) -> dict:
    # 포털에서 복사한 URL Encode 키와 원문 키를 모두 처리한다.
    params = {
        "serviceKey": unquote(service_key),
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    if item_name:
        params["item_name"] = item_name
    if item_seq:
        params["item_seq"] = item_seq
    if cosmetic_report_seq:
        params["cosmetic_report_seq"] = cosmetic_report_seq

    request = Request(
        f"{ENDPOINT}?{urlencode(params)}",
        headers={"User-Agent": "liontone-mfds-functional-reported/1.0"},
    )
    with urlopen(request, timeout=90) as response:
        payload = json.load(response)

    header = payload.get("header") or {}
    if str(header.get("resultCode")) != "00":
        raise RuntimeError(
            f"식약처 API 오류 {header.get('resultCode')}: {header.get('resultMsg')}"
        )
    return payload


def as_items(value) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def fetch_all(args, service_key: str) -> tuple[list[dict], int]:
    first = request_page(
        service_key,
        1,
        args.page_size,
        args.item_name,
        args.item_seq,
        args.cosmetic_report_seq,
    )
    body = first.get("body") or {}
    total_count = int(body.get("totalCount") or 0)
    items = as_items(body.get("items"))
    total_pages = (total_count + args.page_size - 1) // args.page_size
    print(
        f"조회 대상 {total_count:,}건 / {total_pages:,}페이지",
        file=sys.stderr,
    )

    for page_no in range(2, total_pages + 1):
        payload = request_page(
            service_key,
            page_no,
            args.page_size,
            args.item_name,
            args.item_seq,
            args.cosmetic_report_seq,
        )
        page_items = as_items((payload.get("body") or {}).get("items"))
        items.extend(page_items)
        if page_no == total_pages or page_no % 10 == 0:
            print(f"  수집 진행: {len(items):,}/{total_count:,}", file=sys.stderr)
        if args.delay:
            time.sleep(args.delay)
    return items, total_count


def ordered_fields(items: list[dict]) -> list[str]:
    discovered = []
    seen = set()
    for field in KNOWN_FIELDS + [key for item in items for key in item]:
        if field not in seen:
            seen.add(field)
            discovered.append(field)
    return discovered


def write_outputs(items: list[dict], total_count: int, args) -> None:
    json_path = Path(args.json_out)
    csv_path = Path(args.csv_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ordered_fields(items)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)

    report_seq = {str(item.get("COSMETIC_REPORT_SEQ") or "") for item in items}
    report_seq.discard("")
    print(f"수집 행: {len(items):,}건 / API totalCount: {total_count:,}건")
    print(f"보고일련번호 고유값: {len(report_seq):,}건")
    print(f"필드 수: {len(fields)}개")
    print(f"JSON 저장: {json_path}")
    print(f"CSV 저장: {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="식약처 기능성화장품 보고품목정보 수집")
    parser.add_argument("--service-key", help="식약처 일반 인증키(미입력 시 숨김 프롬프트)")
    parser.add_argument("--page-size", type=int, default=500, help="페이지당 건수(1~500)")
    parser.add_argument("--delay", type=float, default=0.1, help="페이지 사이 대기 초")
    parser.add_argument("--item-name", default="", help="품목명 검색 필터")
    parser.add_argument("--item-seq", default="", help="품목일련번호 검색 필터")
    parser.add_argument("--cosmetic-report-seq", default="", help="화장품보고일련번호 필터")
    parser.add_argument(
        "--json-out",
        default="oliveyoung_data/성분/mfds_기능성화장품_보고품목정보.json",
    )
    parser.add_argument(
        "--csv-out",
        default="oliveyoung_data/성분/mfds_기능성화장품_보고품목정보.csv",
    )
    args = parser.parse_args()
    if not 1 <= args.page_size <= PAGE_SIZE_MAX:
        parser.error(f"--page-size는 1~{PAGE_SIZE_MAX} 사이여야 합니다.")
    if args.delay < 0:
        parser.error("--delay는 0 이상이어야 합니다.")

    service_key = get_service_key(args.service_key)
    items, total_count = fetch_all(args, service_key)
    write_outputs(items, total_count, args)
    print(f"완료 시각(UTC): {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
