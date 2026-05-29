"""Scoring engine for the fragrance quiz (/podbor/)."""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Fragrance families → note / text keywords (RU + EN) ─────────────────────

FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Свежий": (
        "bergamot", "lemon", "grapefruit", "mint", "lime", "neroli", "aldehyd",
        "aquatic", "ozon", "water", "sea", "marine",
        "бергамот", "лимон", "грейпфрут", "мята", "лайм", "нероли", "альдегид",
        "акват", "морск", "озон",
    ),
    "Цветочный": (
        "rose", "jasmine", "iris", "violet", "peony", "ylang", "geranium",
        "lily", "tuberose", "magnolia", "orange blossom", "freesia",
        "роза", "жасмин", "iris", "ирис", "фиал", "пион", "иланг", "герань",
        "лили", "тубероз", "магнол", "фreesia",
    ),
    "Сладкий": (
        "vanilla", "honey", "tonka", "benzoin", "caramel", "praline", "sugar",
        "cotton candy", "chocolate", "almond",
        "ванил", "мёд", "мед", "тонка", "бензоин", "карамел", "пraline",
        "шоколад", "миндал",
    ),
    "Пряный": (
        "cinnamon", "cardamom", "nutmeg", "saffron", "pepper", "ginger", "clove",
        "coriander", "anise", "star anise",
        "кориц", "cardamom", "мускат", "шаfran", "саfran", "перец", "имbir",
        "имбир", "гвоздик", "кoriander", "кориандр", "анис",
    ),
    "Древесный": (
        "sandalwood", "cedar", "vetiver", "oak", "guaiac", "cashmere wood",
        "pine", "cypress", "ebony",
        "sandal", "сандал", "кедр", "vetiver", "ветiver", "ветивер", "дуб",
        "cashmere", "сосн", "кипарис",
    ),
    "Восточный": (
        "oud", "amber", "incense", "olibanum", "myrrh", "labdanum", "resin",
        "balsam", "opoponax",
        "уд", "oud", "амбр", "amber", "ладан", "olibanum", "олibanum",
        "myrrh", "мирр", "лаbdanum", "смол",
    ),
    "Цитрусовый": (
        "bergamot", "lemon", "grapefruit", "orange", "tangerine", "mandarin",
        "lime", "yuzu", "citron",
        "бергamot", "бергамот", "лимон", "грейпфрут", "апельсин", "мандарин",
        "лайм", "yuzu", "цитрус", "citrus",
    ),
    "Фруктовый": (
        "apple", "pear", "peach", "plum", "berry", "blackcurrant", "raspberry",
        "fig", "lychee", "mango", "pineapple", "cherry",
        "яблок", "груш", "персик", "слив", "berry", "ягод", "смород",
        "малин", "fig", "инжир", "личи", "манго", "ананас", "вишн",
    ),
    "Кожаный": (
        "leather", "cuir", "suede", "birch tar",
        "кожа", "leather", "замш", "birch",
    ),
    "Фужерный": (
        "lavender", "oakmoss", "coumarin", "tonka", "geranium", "aromatic",
        "фужer", "фужер", "lavender", "лаванда", "oakmoss", "мох", "coumarin",
    ),
    "Акватический": (
        "aquatic", "marine", "sea", "ozonic", "water", "calone",
        "акват", "морск", "marine", "ozon", "водн", "calone",
    ),
    "Гурманский": (
        "vanilla", "caramel", "coffee", "chocolate", "praline", "almond",
        "honey", "tonka", "cocoa", "hazelnut",
        "ванил", "карамел", "кофе", "шоколад", "praline", "миндал", "мёд",
        "тонка", "какао", "фундук", "гурман",
    ),
}

INTENSITY_HEAVY = (
    "oud", "patchouli", "leather", "tobacco", "incense", "olibanum", "amber",
    "benzoin", "myrrh", "labdanum", "saffron",
    "уд", "пachuli", "пачули", "кожа", "табак", "ладан", "амбр", "benzoin",
)
INTENSITY_LIGHT = (
    "bergamot", "lemon", "grapefruit", "mint", "lime", "aldehyd", "aquatic",
    "marine", "ozon", "water",
    "бергamot", "бергамот", "лимон", "грейпфрут", "мята", "лайм", "альдегид",
    "акват", "морск",
)

OCCASION_BOOSTS: dict[str, dict[str, float]] = {
    "everyday": {
        "Свежий": 1.0, "Фужерный": 0.9, "Цитрусовый": 0.85, "Акватический": 0.8,
        "Древесный": 0.5, "Цветочный": 0.45,
    },
    "work": {
        "Древесный": 1.0, "Фужерный": 0.95, "Свежий": 0.85, "Цитрусовый": 0.6,
        "Цветочный": 0.4,
    },
    "evening": {
        "Восточный": 1.0, "Древесный": 0.9, "Сладкий": 0.85, "Кожаный": 0.8,
        "Пряный": 0.75, "Цветочный": 0.6,
    },
    "special": {
        "Восточный": 1.0, "Кожаный": 0.95, "Пряный": 0.9, "Сладкий": 0.85,
        "Древесный": 0.8, "Гурманский": 0.7,
    },
}

OCCASION_INTENSITY: dict[str, tuple[str, ...]] = {
    "everyday": ("Лёгкий", "Умеренный"),
    "work": ("Умеренный", "Лёгкий"),
    "evening": ("Насыщенный", "Умеренный"),
    "special": ("Насыщенный", "Умеренный"),
}

@dataclass
class QuizAnswers:
    occasion: str = ""
    families: list[str] = field(default_factory=list)
    intensity: str = ""
    avoid: list[str] = field(default_factory=list)
    budget: float | None = None


def _norm(text: str) -> str:
    return (text or "").strip().lower().replace("ё", "е")


def _text_hits(text: str, keywords: tuple[str, ...]) -> int:
    t = _norm(text)
    return sum(1 for kw in keywords if kw in t)


def detect_families(note_names: list[str], product_name: str = "", description: str = "") -> set[str]:
    blob_parts = list(note_names) + [product_name, description]
    blob = " ".join(_norm(p) for p in blob_parts if p)
    found: set[str] = set()
    for family, keywords in FAMILY_KEYWORDS.items():
        if _text_hits(blob, keywords) > 0:
            found.add(family)
    return found


def infer_intensity(note_names: list[str], note_types: dict[str, str]) -> str:
    """Return one of: Лёгкий, Умеренный, Насыщенный."""
    blob = " ".join(_norm(n) for n in note_names)
    heavy = _text_hits(blob, INTENSITY_HEAVY)
    light = _text_hits(blob, INTENSITY_LIGHT)
    base_count = sum(1 for n in note_names if note_types.get(n) == "base")

    if heavy >= 2 or (heavy >= 1 and base_count >= 2):
        return "Насыщенный"
    if light >= 2 and heavy == 0 and base_count <= 1:
        return "Лёгкий"
    if heavy >= 1 or base_count >= 3:
        return "Насыщенный"
    if light >= 1 and base_count <= 1:
        return "Лёгкий"
    return "Умеренный"


def _intensity_score(wanted: str, actual: str) -> float:
    order = {"Лёгкий": 0, "Умеренный": 1, "Насыщенный": 2}
    if not wanted:
        return 0.5
    if wanted == actual:
        return 1.0
    diff = abs(order.get(wanted, 1) - order.get(actual, 1))
    return 0.45 if diff == 1 else 0.0


def _family_overlap_score(selected: list[str], detected: set[str]) -> float:
    if not selected:
        return 0.5
    if not detected:
        return 0.15
    hits = len(set(selected) & detected)
    return hits / len(selected)


def _profile_boost(profile: dict[str, float], detected: set[str]) -> float:
    if not profile or not detected:
        return 0.0
    scores = [profile[f] for f in detected if f in profile]
    return max(scores) if scores else 0.0


def score_product(
    *,
    note_names: list[str],
    note_types: dict[str, str],
    product_name: str,
    description: str,
    min_price: float,
    answers: QuizAnswers,
) -> float:
    """Return raw score in 0..100 (higher = better match)."""
    detected = detect_families(note_names, product_name, description)
    intensity = infer_intensity(note_names, note_types)

    # ── Family preference (max ~35) ──
    family_score = _family_overlap_score(answers.families, detected) * 35.0

    # ── Intensity (max ~12) ──
    intensity_score = _intensity_score(answers.intensity, intensity) * 12.0

    # ── Occasion (max ~12) ──
    occasion_score = 0.0
    if answers.occasion:
        occ_boost = _profile_boost(OCCASION_BOOSTS.get(answers.occasion, {}), detected)
        occasion_score += occ_boost * 8.0
        pref = OCCASION_INTENSITY.get(answers.occasion, ())
        if intensity in pref:
            occasion_score += (4.0 if intensity == pref[0] else 2.5)

    # ── Budget fit (max ~5) ──
    budget_score = 0.0
    whom_score = 2.5
    if answers.budget and answers.budget < 999_000:
        ratio = min_price / answers.budget
        if min_price <= answers.budget * 0.85:
            whom_score += 2.5
        if 0.35 <= ratio <= 0.95:
            budget_score = 5.0 * (1.0 - abs(ratio - 0.65) / 0.65)
        elif ratio <= 1.0:
            budget_score = 1.5

    raw = family_score + intensity_score + occasion_score + whom_score + budget_score
    return min(raw, 100.0)


def raw_to_match_pct(raw: float, rank_index: int = 0) -> int:
    """Map raw score to display percentage (58–98)."""
    base = 52 + raw * 0.46
    pct = int(round(base))
    pct = max(58, min(98, pct))
    if rank_index > 0:
        pct = max(58, pct - rank_index)
    return pct


def parse_quiz_answers(params) -> QuizAnswers:
    """Build QuizAnswers from a Django QueryDict or mapping."""
    get = params.get
    families_raw = get("families", "") or ""
    avoid_raw = get("avoid", "") or ""
    budget_raw = get("budget", "")

    budget_val = None
    if budget_raw:
        try:
            budget_val = float(budget_raw)
        except (TypeError, ValueError):
            budget_val = None

    return QuizAnswers(
        occasion=(get("occasion", "") or "").strip(),
        families=[f.strip() for f in families_raw.split(",") if f.strip()],
        intensity=(get("intensity", "") or "").strip(),
        avoid=[k.strip() for k in avoid_raw.split(",") if k.strip()],
        budget=budget_val,
    )
