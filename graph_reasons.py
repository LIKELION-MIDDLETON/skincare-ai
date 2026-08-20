# -*- coding: utf-8 -*-
"""`graph/`(Product-CONTAINS->Ingredient-HAS_FUNCTION->Function) 그래프에서
추천 상품 하나가 "왜" 진단에 맞는지 뒷받침하는 성분·근거만 뽑아낸다.

여기서 나온 사실만 llm_reasons.py의 프롬프트에 넣는다 — LLM이 근거 없는
효능을 지어내지 못하게 하는 grounding 소스다.
"""
import csv, os

BASE = os.path.dirname(os.path.abspath(__file__))
GRAPH_DIR = os.path.join(BASE, "graph")

# ingredient_has_function.csv의 evidence_strength 값. 숫자가 작을수록 근거가 강함.
_RANK = {"regulatory": 0, "official_reference": 1, "heuristic": 2}

_LOADED = False
_ing_name = {}        # ingredient_id -> canonical_name
_ing_functions = {}   # ingredient_id -> [(function_name, evidence_strength), ...]
_product_ings = {}    # product_id -> [ingredient_id, ...] (전성분 표기 순서)
_product_claims = {}  # product_id -> {function_name, ...} (식약처 직접 주장)


def _read(name):
    path = os.path.join(GRAPH_DIR, name)
    if not os.path.exists(path):
        return
    return csv.DictReader(open(path, encoding="utf-8-sig"))


def _load():
    global _LOADED
    if _LOADED:
        return
    _LOADED = True

    rows = _read("ingredient_nodes.csv")
    if rows:
        for r in rows:
            _ing_name[r["ingredient_id"]] = r["canonical_name"] or r["ingredient_id"]

    rows = _read("ingredient_has_function.csv")
    if rows:
        for r in rows:
            _ing_functions.setdefault(r["ingredient_id"], []).append(
                (r["function_name"], r["evidence_strength"]))

    rows = _read("product_contains_ingredient.csv")
    if rows:
        # ingredient_order대로 파일이 정렬돼 있지 않을 수 있어 정렬 후 순서만 뽑는다.
        tmp = {}
        for r in rows:
            try:
                order = int(r["ingredient_order"])
            except (TypeError, ValueError):
                order = 10**9
            tmp.setdefault(r["product_id"], []).append((order, r["ingredient_id"]))
        for pid, lst in tmp.items():
            lst.sort(key=lambda x: x[0])
            _product_ings[pid] = [ing_id for _, ing_id in lst]

    rows = _read("product_claims_function.csv")
    if rows:
        for r in rows:
            _product_claims.setdefault(r["product_id"], set()).add(r["function_name"])


def evidence_for(goods_no, functions, limit=5):
    """goods_no 상품의 성분 중 functions(관심 효능 축 집합)와 겹치는 근거를 뽑는다.

    성분 하나당 근거 하나만(가장 강한 것), 전성분 표기 순서를 1차 기준으로 하고
    근거 강도(공식 규제 > 배합목적 근거 > 이름 기반 추론)로 재정렬한다.
    반환: (성분 근거 리스트, 상품이 식약처에 직접 주장한 효능 집합 중 functions와 겹치는 것)
    """
    _load()
    functions = set(functions)
    out = []
    for ing_id in _product_ings.get(goods_no, []):
        best = None
        for fn, strength in _ing_functions.get(ing_id, ()):
            if fn not in functions:
                continue
            if best is None or _RANK.get(strength, 9) < _RANK.get(best[1], 9):
                best = (fn, strength)
        if best:
            out.append({"성분": _ing_name.get(ing_id, ing_id), "기능": best[0], "근거": best[1]})
    out.sort(key=lambda d: _RANK.get(d["근거"], 9))
    claims = _product_claims.get(goods_no, set()) & functions
    return out[:limit], claims
