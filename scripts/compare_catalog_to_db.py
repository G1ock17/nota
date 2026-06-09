#!/usr/bin/env python3
"""Сравнение comparison_result.txt с products в db.sqlite3 (улучшенное сопоставление)."""
from __future__ import annotations

import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from products.brand_aliases import canonical_brand_name  # noqa: E402
from products.display_names import strip_brand_prefix  # noqa: E402

CONC_RE = re.compile(r"\b(ed[ptc]|extrait|parfum|cologne)\b", re.I)
GENDER_MALE = frozenset({"man", "men", "homme", "male", "hombre"})
GENDER_FEMALE = frozenset({"woman", "women", "femme", "female", "lady"})
STOP_TOKENS = frozenset(
    {
        "for", "the", "de", "du", "des", "le", "la", "les", "et", "and",
        "pour", "eau", "parfum", "cologne", "extrait", "absolu", "absolue",
        "man", "men", "woman", "women", "homme", "femme", "unisex", "lady",
    }
)

BRAND_OVERRIDES = {
    "carolina herrera": "Carolina Herrera",
    "giorgio armani": "Giorgio Armani",
    "jean paul gaultier": "Jean Paul Gaultier",
    "yves saint laurent": "Yves Saint Laurent",
    "tom ford": "Tom Ford",
    "jo malone": "Jo Malone London",
    "maison francis kurkdjian": "Maison Francis Kurkdjian",
    "parfums de marly": "Parfums de Marly",
    "initio parfums prives": "Initio Parfums Privés",
    "essential parfums": "Essential Parfums",
    "ex nihilo": "Ex Nihilo",
    "escentric molecules": "Escentric Molecules",
    "emporio armani": "Emporio Armani",
    "hugo boss": "Hugo Boss",
    "paco rabanne": "Paco Rabanne",
    "narciso rodriguez": "Narciso Rodriguez",
    "marc jacobs": "Marc Jacobs",
    "viktor & rolf": "Viktor & Rolf",
    "zadig et voltaire": "Zadig et Voltaire",
    "zielinski & rozen": "Zielinski & Rozen",
    "clive christian": "Clive Christian",
    "frederic malle": "Frederic Malle",
    "tiziana terenzi": "Tiziana Terenzi",
    "vilhelm parfumerie": "Vilhelm Parfumerie",
    "banana republic": "Banana Republic",
    "roja parfums": "Roja",
    "roja dove": "Roja",
    "kilian": "By Kilian",
    "by kilian": "By Kilian",
    "sospiro perfumes": "Sospiro",
    "hormone paris": "Hormone",
    "hormone": "Hormone",
    "le labo": "Le Labo",
    "louis vuitton": "Louis Vuitton",
    "giardini di toscana": "Giardini di Toscana",
    "orto parisi": "Orto Parisi",
    "attar collection": "Attar Collection",
    "franck boclet": "Franck Boclet",
    "marc-antoine barrois": "Marc-Antoine Barrois",
}

# Короткие названия Hormone в каталоге → имя продукта в БД (бренд Hormone)
HORMONE_PRODUCT_ALIASES = {
    "adrenaline": "Paris This is not Adrenaline",
    "dopamine": "Paris This is not Dopamine",
    "endorphin": "Paris This is not Endorphin",
    "oxytocin": "Paris This is not Oxytocin",
    "testosterone": "Paris This is not Testosterone",
}


def _gender_token(words: set[str]) -> str | None:
    for w in words:
        if w in GENDER_MALE:
            return "m"
        if w in GENDER_FEMALE:
            return "f"
    return None


def norm_text(value: str, *, drop_gender: bool = False) -> str:
    s = (value or "").lower()
    s = s.replace("ё", "е")
    for old, new in [
        ("'", "'"), ("'", "'"), ("`", "'"),
        ("–", "-"), ("—", "-"),
        ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
        ("à", "a"), ("â", "a"), ("ô", "o"), ("û", "u"), ("ò", "o"), ("ó", "o"),
        ("ü", "u"), ("ö", "o"), ("ä", "a"), ("ç", "c"),
        ("í", "i"), ("á", "a"), ("ñ", "n"),
    ]:
        s = s.replace(old, new)
    # ? в каталоге — битая кодировка (Gi? → Gio, Ros? → Rose)
    s = s.replace("?", "o")
    s = re.sub(r"\(\d{4}\)", " ", s)
    s = CONC_RE.sub(" ", s)
    s = re.sub(r"\bbergamote\b", " bergamot ", s)
    s = re.sub(r"\bmen\b", " man ", s)
    s = re.sub(r"\bwomen\b", " woman ", s)
    if drop_gender:
        s = re.sub(
            r"\b(test|sample|mini|unisex|pour homme|pour femme|"
            r"man|woman|homme|femme|lady|male|female|hombre)\b",
            " ",
            s,
            flags=re.I,
        )
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def core_tokens(value: str) -> set[str]:
    return {w for w in norm_text(value).split() if w not in STOP_TOKENS and len(w) > 1}


def resolve_brand(raw: str) -> str:
    key = raw.strip().lower()
    if key in BRAND_OVERRIDES:
        return BRAND_OVERRIDES[key]
    return canonical_brand_name(raw)


def score_match(a: str, b: str) -> float:
    ta = set(norm_text(a).split())
    tb = set(norm_text(b).split())
    if not ta or not tb:
        return 0.0
    ga, gb = _gender_token(ta), _gender_token(tb)
    if ga and gb and ga != gb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(len(ta), len(tb))


def gender_compatible(catalog_name: str, db_name: str) -> bool:
    ca = set(norm_text(catalog_name).split())
    da = set(norm_text(db_name).split())
    ga, gb = _gender_token(ca), _gender_token(da)
    if ga and gb and ga != gb:
        return False
    return True


def catalog_variants(line: str) -> list[str]:
    """Варианты строки каталога для обхода битой кодировки."""
    variants = [line.strip()]
    if "?" in line:
        variants.append(line.replace("?", "o"))
        variants.append(line.replace("?", "e"))
        variants.append(re.sub(r"\?", "", line))
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def load_db():
    db = sqlite3.connect(ROOT / "db.sqlite3")
    cur = db.cursor()
    cur.execute(
        """
        SELECT b.name, p.name, p.id
        FROM products_product p
        JOIN products_brand b ON p.brand_id = b.id
        """
    )
    rows = cur.fetchall()
    by_brand: dict[str, list[tuple[str, int]]] = defaultdict(list)
    all_products: list[tuple[str, str, int]] = []
    brand_names: list[str] = []

    for brand, pname, pid in rows:
        cb = resolve_brand(brand)
        by_brand[cb.lower()].append((pname, pid))
        if brand.lower() != cb.lower():
            by_brand[brand.lower()].append((pname, pid))
        all_products.append((cb, pname, pid))
        brand_names.append(brand)
        if cb != brand:
            brand_names.append(cb)

    brand_prefixes = sorted({resolve_brand(b) for b in brand_names} | set(brand_names), key=len, reverse=True)

    norm_full: dict[str, tuple[str, str, int]] = {}
    for brand, pname, pid in all_products:
        for key in (
            norm_text(f"{brand} {pname}"),
            norm_text(pname),
            norm_text(f"{brand} {pname}", drop_gender=True),
            norm_text(pname, drop_gender=True),
        ):
            norm_full.setdefault(key, (brand, pname, pid))

    return by_brand, all_products, brand_prefixes, norm_full


def parse_catalog_line(line: str, brand_prefixes: list[str]) -> tuple[str, str]:
    line = line.strip()
    low = line.lower()
    for brand in brand_prefixes:
        bl = brand.lower()
        if low == bl:
            return resolve_brand(brand), ""
        if low.startswith(bl + " "):
            rest = line[len(brand) :].strip()
            rest = re.sub(r"^[\s\-–—:]+", "", rest).strip()
            return resolve_brand(brand), rest
    for key, canon in sorted(BRAND_OVERRIDES.items(), key=lambda x: -len(x[0])):
        if low.startswith(key + " "):
            return canon, line[len(key) :].strip()
    parts = line.split(" ", 1)
    if len(parts) == 2:
        return resolve_brand(parts[0]), parts[1]
    return "", line


def _match_hormone_short(cb: str, pname: str, by_brand) -> tuple[str, str, int] | None:
    if cb.lower() != "hormone":
        return None
    alias = HORMONE_PRODUCT_ALIASES.get(norm_text(pname))
    if not alias:
        return None
    for db_p, pid in by_brand.get("hormone", []):
        if norm_text(db_p) == norm_text(alias):
            return cb, db_p, pid
    return None


def _match_unique_subset(cb: str, pname: str, by_brand) -> tuple[str, str, int] | None:
    catalog_core = core_tokens(pname)
    if not catalog_core:
        return None
    hits: list[tuple[str, int]] = []
    for db_p, pid in by_brand.get(cb.lower(), []):
        if not gender_compatible(pname, db_p):
            continue
        db_core = core_tokens(db_p)
        if catalog_core <= db_core:
            hits.append((db_p, pid))
    if len(hits) == 1:
        return cb, hits[0][0], hits[0][1]
    return None


def _find_match_one(line: str, by_brand, all_products, brand_prefixes, norm_full):
    brand, pname = parse_catalog_line(line, brand_prefixes)
    cb = resolve_brand(brand)

    hormone = _match_hormone_short(cb, pname, by_brand)
    if hormone:
        return "hormone_alias", hormone[0], hormone[1], hormone[2]

    for db_pname, pid in by_brand.get(cb.lower(), []):
        if norm_text(db_pname) == norm_text(pname) and gender_compatible(pname, db_pname):
            return "exact", cb, db_pname, pid

    nf = norm_text(line)
    if nf in norm_full:
        b, p, pid = norm_full[nf]
        if gender_compatible(pname or line, p):
            return "full_norm", b, p, pid

    if _gender_token(set(norm_text(pname).split())) is None:
        nf2 = norm_text(line, drop_gender=True)
        if nf2 in norm_full:
            b, p, pid = norm_full[nf2]
            return "full_norm_loose", b, p, pid

    stripped = strip_brand_prefix(line, cb)
    ns = norm_text(stripped)
    if ns in norm_full:
        b, p, pid = norm_full[ns]
        if gender_compatible(stripped, p):
            return "stripped", b, p, pid

    subset = _match_unique_subset(cb, pname, by_brand)
    if subset:
        return "subset_unique", subset[0], subset[1], subset[2]

    candidates = by_brand.get(cb.lower(), [])
    if candidates:
        scored = [
            (score_match(pname, db_p), db_p, pid)
            for db_p, pid in candidates
            if gender_compatible(pname, db_p)
        ]
        scored.sort(reverse=True)
        if scored:
            best_score, best_name, best_pid = scored[0]
            if best_score >= 0.72 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08):
                return f"fuzzy_brand:{best_score:.2f}", cb, best_name, best_pid

    scored_all = []
    for b, db_p, pid in all_products:
        if b.lower() != cb.lower():
            continue
        if not gender_compatible(pname or line, db_p):
            continue
        s = score_match(pname or line, db_p)
        if s >= 0.88:
            scored_all.append((s, b, db_p, pid))
    if scored_all:
        scored_all.sort(reverse=True)
        s, b, db_p, pid = scored_all[0]
        if len(scored_all) == 1 or scored_all[0][0] - scored_all[1][0] >= 0.12:
            return f"fuzzy_brand_strict:{s:.2f}", b, db_p, pid

    return None, cb, pname, None


def find_match(line: str, by_brand, all_products, brand_prefixes, norm_full):
    for variant in catalog_variants(line):
        result = _find_match_one(variant, by_brand, all_products, brand_prefixes, norm_full)
        if result[0]:
            return result
    return None, *_find_match_one(line, by_brand, all_products, brand_prefixes, norm_full)[1:]


def suggest_near_miss(line: str, by_brand, brand_prefixes) -> str | None:
    """Подсказка для ручной проверки, если автомат не нашёл."""
    brand, pname = parse_catalog_line(line, brand_prefixes)
    cb = resolve_brand(brand)
    catalog_core = core_tokens(pname)
    if not catalog_core:
        return None
    best: tuple[float, str] | None = None
    for db_p, _pid in by_brand.get(cb.lower(), []):
        if not gender_compatible(pname, db_p):
            continue
        db_core = core_tokens(db_p)
        if not db_core:
            continue
        inter = len(catalog_core & db_core)
        score = inter / max(len(catalog_core), len(db_core))
        if score >= 0.5 and (best is None or score > best[0]):
            best = (score, db_p)
    return best[1] if best else None


def main():
    catalog_path = ROOT / "comparison_result.txt"
    lines = [l.strip() for l in catalog_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    by_brand, all_products, brand_prefixes, norm_full = load_db()

    found = []
    missing = []
    near_miss: list[tuple[str, str]] = []
    methods = defaultdict(int)

    for line in lines:
        method, brand, matched_name, pid = find_match(line, by_brand, all_products, brand_prefixes, norm_full)
        if method:
            found.append((line, method, brand, matched_name))
            methods[method.split(":")[0]] += 1
        else:
            missing.append(line)
            hint = suggest_near_miss(line, by_brand, brand_prefixes)
            if hint:
                near_miss.append((line, hint))

    out_missing = ROOT / "missing_from_db_v3.txt"
    out_near = ROOT / "missing_near_miss_v3.txt"
    out_missing.write_text("\n".join(missing) + "\n", encoding="utf-8")
    out_near.write_text(
        "\n".join(f"{line}\t->\t{hint}" for line, hint in near_miss) + "\n",
        encoding="utf-8",
    )

    print(f"В каталоге:     {len(lines)}")
    print(f"Найдено в БД:   {len(found)}")
    print(f"Не найдено:     {len(missing)}")
    print(f"  из них с похожим в БД (near miss): {len(near_miss)}")
    print(f"  вероятно отсутствуют:              {len(missing) - len(near_miss)}")
    print("Методы:", dict(methods))
    print()
    print("--- Примеры fuzzy / subset ---")
    shown = 0
    for line, method, b, p in found:
        if "fuzzy" in method or "subset" in method or "hormone" in method:
            print(f"  [{method}] {line}")
            print(f"       -> {b} | {p}")
            shown += 1
            if shown >= 15:
                break
    print()
    print("--- Не найдено (первые 35) ---")
    for m in missing[:35]:
        hint = next((h for l, h in near_miss if l == m), None)
        suffix = f"  (~ {hint})" if hint else ""
        print(f"  {m}{suffix}")
    if len(missing) > 35:
        print(f"  ... и ещё {len(missing) - 35}")
    print(f"\nПолный список отсутствующих: {out_missing.name}")
    print(f"Похожие в БД (для проверки):   {out_near.name}")


if __name__ == "__main__":
    main()
