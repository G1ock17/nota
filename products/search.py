from django.db.models import Q


def product_search_q(query: str) -> Q | None:
    """
    Поиск по бренду и названию аромата: каждое слово запроса должно
    встретиться хотя бы в одном из полей (например «Banana Republic 17 Oud Mosaic»).
    """
    tokens = [part.strip() for part in (query or "").split() if part.strip()]
    if not tokens:
        return None

    combined = Q()
    for token in tokens:
        combined &= Q(name__icontains=token) | Q(brand__name__icontains=token)
    return combined


def filter_products_by_search(qs, query: str):
    search_q = product_search_q(query)
    if search_q is None:
        return qs
    return qs.filter(search_q)
