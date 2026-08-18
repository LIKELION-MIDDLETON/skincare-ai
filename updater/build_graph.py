# -*- coding: utf-8 -*-
"""올리브영 상품-성분-기능 그래프 생성기.

그래프의 기본 구조:
    Product -[CONTAINS]-> Ingredient -[HAS_FUNCTION]-> Function

식약처 기능성화장품 보고품목과 올리브영 상품명이 정규화 후 완전 일치하는
경우에만 Product -[CLAIMS]-> Function 엣지를 별도로 생성한다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from alias import canon, canon_en  # noqa: E402
from parser2 import split_components, split_ing  # noqa: E402
from purpose_map import to_tags  # noqa: E402
from rules import classify  # noqa: E402


DEFAULT_PRODUCT_ROOT = ROOT / "oliveyoung_data"
DEFAULT_MASTER = ROOT / "oliveyoung_data" / "성분" / "kcia_mfds_성분사전_병합.csv"
DEFAULT_REPORT = ROOT / "oliveyoung_data" / "성분" / "mfds_기능성화장품_보고품목정보.csv"
DEFAULT_OUT = ROOT / "graph"

SKIN_FUNCTIONS = {
    "보습", "유연", "밀폐보습", "장벽강화", "진정", "항산화", "미백", "주름개선",
    "피지조절", "피지흡착", "여드름", "각질제거", "자외선차단", "재생", "탄력",
}


def digest(value: str, prefix: str) -> str:
    return f"{prefix}:{hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]}"


def norm_product(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (value or "").casefold())


def alias_key(value: str) -> list[str]:
    value = value or ""
    keys = []
    if re.fullmatch(r"[A-Za-z0-9,\-/() ]+", value):
        k = canon_en(value)
        if k:
            keys.append("EN:" + k)
    k = canon(value)
    if k:
        keys.append("KO:" + k)
    return list(dict.fromkeys(keys))


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_master(path: Path):
    rows = read_csv(path)
    groups = {}
    alias_to_groups = defaultdict(set)

    for row in rows:
        standard = (row.get("성분명") or row.get("MFDS_국문명") or "").strip()
        inci = (row.get("영문명") or row.get("MFDS_영문명") or "").strip()
        identity = canon(standard) if standard else "EN:" + canon_en(inci)
        if not identity:
            continue
        group_key = "KO:" + identity if not identity.startswith("EN:") else identity
        if group_key not in groups:
            groups[group_key] = {
                "ingredient_key": digest(group_key, "ING"),
                "canonical_name": standard or inci,
                "kcia_codes": set(),
                "inci_names": set(),
                "cas_numbers": set(),
                "korean_names": set(),
                "mfds_names": set(),
                "synonyms": set(),
                "purposes": set(),
                "source_rows": 0,
            }
        group = groups[group_key]
        group["source_rows"] += 1
        for field, target in (
            ("성분코드", "kcia_codes"),
            ("영문명", "inci_names"),
            ("MFDS_영문명", "inci_names"),
            ("CAS", "cas_numbers"),
            ("MFDS_CAS", "cas_numbers"),
            ("성분명", "korean_names"),
            ("MFDS_국문명", "mfds_names"),
            ("구명칭", "synonyms"),
            ("MFDS_이명", "synonyms"),
            ("배합목적", "purposes"),
        ):
            value = (row.get(field) or "").strip()
            if value:
                group[target].add(value)
        for field in ("성분명", "구명칭", "MFDS_국문명", "MFDS_이명", "영문명", "MFDS_영문명"):
            for key in alias_key(row.get(field) or ""):
                alias_to_groups[key].add(group_key)

    return groups, alias_to_groups


def finalize_ingredient_nodes(groups: dict) -> list[dict]:
    out = []
    for group in sorted(groups.values(), key=lambda x: x["canonical_name"]):
        out.append({
            "ingredient_id": group["ingredient_key"],
            "canonical_name": group["canonical_name"],
            "korean_names": "|".join(sorted(group["korean_names"] | group["mfds_names"])),
            "inci_names": "|".join(sorted(group["inci_names"])),
            "cas_numbers": "|".join(sorted(group["cas_numbers"])),
            "kcia_codes": "|".join(sorted(group["kcia_codes"])),
            "synonyms": "|".join(sorted(group["synonyms"])),
            "purposes": "|".join(sorted(group["purposes"])),
            "source_rows": group["source_rows"],
            "source": "KCIA+MFDS",
        })
    return out


def load_products(root: Path, feature_path: Path | None):
    products = {}
    for path in sorted(root.glob("*/*_result.csv")):
        category = path.parent.name
        for row in read_csv(path):
            goods_no = (row.get("goods_no") or "").strip()
            if not goods_no:
                continue
            product = products.setdefault(goods_no, {
                "goods_no": goods_no,
                "brand": (row.get("brand") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "sale_price": (row.get("sale_price") or "").strip(),
                "product_url": (row.get("product_url") or "").strip(),
                "ingredients": (row.get("성분") or "").strip(),
                "categories": set(),
                "source_files": set(),
            })
            product["categories"].add(category)
            product["source_files"].add(str(path.relative_to(ROOT)))
            if not product["ingredients"] and row.get("성분"):
                product["ingredients"] = row["성분"].strip()

    if feature_path and feature_path.exists():
        for row in read_csv(feature_path):
            goods_no = (row.get("goods_no") or "").strip()
            if goods_no in products and row.get("카테고리"):
                products[goods_no]["categories"].add(row["카테고리"].strip())
    return products


def parse_product_ingredients(text: str, alias_to_groups):
    parsed = []
    for component_name, body in split_components(text or ""):
        # merge=False avoids parser2's environment-specific dictionary lookup.
        tokens = split_ing(body, merge=False)
        i = 0
        while i < len(tokens):
            token = tokens[i]
            # Rejoin common space-separated INCI names when the merged master knows them.
            if i + 1 < len(tokens):
                combined = tokens[i] + tokens[i + 1]
                if any(k in alias_to_groups for k in alias_key(combined)):
                    token = combined
                    i += 1
            if token:
                parsed.append((component_name, token))
            i += 1
    return parsed


def resolve_group(raw_name: str, alias_to_groups, groups):
    candidates = set()
    for key in alias_key(raw_name):
        candidates.update(alias_to_groups.get(key, set()))
    if len(candidates) == 1:
        group_key = next(iter(candidates))
        return groups[group_key]["ingredient_key"], "exact_alias"
    if len(candidates) > 1:
        group_key = sorted(candidates)[0]
        return groups[group_key]["ingredient_key"], "ambiguous_alias"
    return digest("raw:" + canon(raw_name), "RAW"), "unmatched"


def add_function_edge(edges: dict, function_names: set, ingredient_id: str, function_name: str,
                      source: str, evidence_type: str, evidence_strength: str):
    function_name = (function_name or "").strip()
    if not function_name:
        return
    function_id = "FUNC:" + function_name
    key = (ingredient_id, function_id, source, evidence_type)
    edges[key] = {
        "ingredient_id": ingredient_id,
        "function_id": function_id,
        "function_name": function_name,
        "source": source,
        "evidence_type": evidence_type,
        "evidence_strength": evidence_strength,
        "is_inferred": "Y" if evidence_strength == "heuristic" else "N",
    }
    function_names.add(function_name)


def build_function_edges(groups, alias_to_groups, gosi_path: Path):
    edges = {}
    function_names = set()
    for group in groups.values():
        ingredient_id = group["ingredient_key"]
        for purpose in group["purposes"]:
            for tag in to_tags(purpose):
                add_function_edge(edges, function_names, ingredient_id, tag, "KCIA", "배합목적", "official_reference")
        inferred = classify(group["canonical_name"])
        if inferred:
            for tag in inferred["효능태그"].split("|"):
                add_function_edge(edges, function_names, ingredient_id, tag, "RULES", "이름기반추론", "heuristic")

    if gosi_path.exists():
        for row in read_csv(gosi_path):
            function_name = (row.get("고시기능성") or "").strip()
            for key in alias_key(row.get("성분명") or ""):
                for group_key in alias_to_groups.get(key, set()):
                    add_function_edge(
                        edges, function_names, groups[group_key]["ingredient_key"], function_name,
                        "MFDS_GOSI", "고시기능성성분", "regulatory",
                    )
    return list(edges.values()), function_names


def load_report_claims(report_path: Path, products: dict):
    if not report_path.exists():
        return []
    by_name = defaultdict(list)
    for row in read_csv(report_path):
        name = norm_product(row.get("ITEM_NAME") or "")
        if name:
            by_name[name].append(row)

    claims = []
    for goods_no, product in products.items():
        product_name = norm_product(product.get("name") or "")
        if not product_name:
            continue
        for report in by_name.get(product_name, []):
            code = (report.get("EE_CODE") or "").strip()
            if code == "1": functions = ["미백"]
            elif code == "2": functions = ["주름개선"]
            elif code == "3": functions = ["미백", "주름개선"]
            else: functions = []
            for function_name in functions:
                claims.append({
                    "product_id": goods_no,
                    "function_id": "FUNC:" + function_name,
                    "function_name": function_name,
                    "source": "MFDS_REPORT",
                    "evidence_type": "기능성화장품_보고품목",
                    "evidence_strength": "regulatory",
                    "match_method": "exact_normalized_product_name",
                    "report_id": report.get("COSMETIC_REPORT_SEQ", ""),
                    "report_item_name": report.get("ITEM_NAME", ""),
                    "ee_code": code,
                    "ee_name": report.get("EE_NAME", ""),
                })
    return claims


def main():
    parser = argparse.ArgumentParser(description="상품-성분-기능 그래프 CSV 생성")
    parser.add_argument("--product-root", default=str(DEFAULT_PRODUCT_ROOT))
    parser.add_argument("--master", default=str(DEFAULT_MASTER))
    parser.add_argument("--gosi", default=str(SCRIPT_DIR / "gosi.csv"))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--feature-index", default=str(ROOT / "상품별_효능_v4.csv"))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    out_dir = Path(args.out)
    groups, alias_to_groups = load_master(Path(args.master))
    products = load_products(Path(args.product_root), Path(args.feature_index))
    function_edges, function_names = build_function_edges(groups, alias_to_groups, Path(args.gosi))
    claims = load_report_claims(Path(args.report), products)

    product_nodes = []
    ingredient_nodes = finalize_ingredient_nodes(groups)
    ingredient_edges = []
    raw_nodes = {}
    for goods_no, product in sorted(products.items()):
        parsed = parse_product_ingredients(product["ingredients"], alias_to_groups)
        product_nodes.append({
            "product_id": goods_no,
            "brand": product["brand"],
            "name": product["name"],
            "category": "|".join(sorted(product["categories"])),
            "sale_price": product["sale_price"],
            "product_url": product["product_url"],
            "ingredient_count": len(parsed),
            "source_files": "|".join(sorted(product["source_files"])),
        })
        for order, (component_name, raw_name) in enumerate(parsed, 1):
            ingredient_id, match_method = resolve_group(raw_name, alias_to_groups, groups)
            if match_method == "unmatched" and ingredient_id not in raw_nodes:
                raw_nodes[ingredient_id] = {
                    "ingredient_id": ingredient_id,
                    "canonical_name": raw_name,
                    "korean_names": raw_name,
                    "inci_names": "",
                    "cas_numbers": "",
                    "kcia_codes": "",
                    "synonyms": "",
                    "purposes": "",
                    "source_rows": 0,
                    "source": "OLIVEYOUNG_RAW_ONLY",
                }
            ingredient_edges.append({
                "product_id": goods_no,
                "ingredient_id": ingredient_id,
                "ingredient_name_raw": raw_name,
                "ingredient_order": order,
                "component_name": component_name,
                "source": "OLIVEYOUNG",
                "source_url": product["product_url"],
                "match_method": match_method,
            })

    ingredient_nodes.extend(sorted(raw_nodes.values(), key=lambda x: x["canonical_name"]))
    function_nodes = []
    for name in sorted(function_names | {x["function_name"] for x in claims}):
        function_nodes.append({
            "function_id": "FUNC:" + name,
            "function_name": name,
            "function_type": "skin_effect" if name in SKIN_FUNCTIONS else "cosmetic_role",
        })

    write_csv(out_dir / "product_nodes.csv", product_nodes, [
        "product_id", "brand", "name", "category", "sale_price", "product_url",
        "ingredient_count", "source_files",
    ])
    write_csv(out_dir / "ingredient_nodes.csv", ingredient_nodes, [
        "ingredient_id", "canonical_name", "korean_names", "inci_names", "cas_numbers",
        "kcia_codes", "synonyms", "purposes", "source_rows", "source",
    ])
    write_csv(out_dir / "function_nodes.csv", function_nodes, [
        "function_id", "function_name", "function_type",
    ])
    write_csv(out_dir / "product_contains_ingredient.csv", ingredient_edges, [
        "product_id", "ingredient_id", "ingredient_name_raw", "ingredient_order",
        "component_name", "source", "source_url", "match_method",
    ])
    write_csv(out_dir / "ingredient_has_function.csv", function_edges, [
        "ingredient_id", "function_id", "function_name", "source", "evidence_type",
        "evidence_strength", "is_inferred",
    ])
    write_csv(out_dir / "product_claims_function.csv", claims, [
        "product_id", "function_id", "function_name", "source", "evidence_type",
        "evidence_strength", "match_method", "report_id", "report_item_name",
        "ee_code", "ee_name",
    ])

    edge_match = defaultdict(int)
    for edge in ingredient_edges:
        edge_match[edge["match_method"]] += 1
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "product_root": str(Path(args.product_root).relative_to(ROOT)) if Path(args.product_root).is_relative_to(ROOT) else str(args.product_root),
            "ingredient_master": str(Path(args.master).relative_to(ROOT)) if Path(args.master).is_relative_to(ROOT) else str(args.master),
            "functional_report": str(Path(args.report).relative_to(ROOT)) if Path(args.report).is_relative_to(ROOT) else str(args.report),
        },
        "counts": {
            "product_nodes": len(product_nodes),
            "ingredient_nodes": len(ingredient_nodes),
            "master_ingredient_nodes": len(ingredient_nodes) - len(raw_nodes),
            "raw_only_ingredient_nodes": len(raw_nodes),
            "function_nodes": len(function_nodes),
            "product_contains_ingredient_edges": len(ingredient_edges),
            "ingredient_has_function_edges": len(function_edges),
            "product_claims_function_edges": len(claims),
        },
        "ingredient_edge_match_method": dict(edge_match),
        "notes": [
            "전성분 순서는 함량의 정확한 값이 아닌 원문 표기 순서다.",
            "RULES 출처 엣지는 이름 기반 추론이며 공식 효능 근거와 분리해야 한다.",
            "식약처 상품 직접 주장은 올리브영 상품명 정규화 완전일치만 연결했다.",
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
