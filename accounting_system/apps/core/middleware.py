"""Request middleware: HTMX detection + current organization resolution."""


class HtmxMiddleware:
    """Attach ``request.htmx`` (True for HTMX-issued requests)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.htmx = request.headers.get("HX-Request") == "true"
        return self.get_response(request)


class CurrentOrganizationMiddleware:
    """Resolve the active organization/membership for the logged-in user.

    Sets ``request.organization`` and ``request.membership`` (or ``None``).
    A user belongs to exactly one organization in this build (first membership).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        request.membership = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            membership = (
                user.memberships.select_related("organization").first()
            )
            if membership is not None:
                request.membership = membership
                request.organization = membership.organization
        return self.get_response(request)
