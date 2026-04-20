"""Pagination utilities."""

from typing import Optional

from rest_framework.pagination import PageNumberPagination


class LargePageNumberPagination(PageNumberPagination):
    """
    Default page size is large enough that most list views behave as before,
    but heavy endpoints won't silently return 100k+ rows.

    Clients opt into smaller/larger pages via ?page_size=...
    """

    page_size = 1000
    page_size_query_param = "page_size"
    max_page_size = 5000


class OptInPageNumberPagination(LargePageNumberPagination):
    """
    Backward-compatible pagination: legacy callers that don't pass any
    pagination hints get the full unpaginated list (DRF returns a flat array
    when ``paginate_queryset`` returns ``None``). New callers opt in by
    passing ``?page=``, ``?page_size=``, or ``?paginate=true``, which yields
    the usual paginated envelope (``count``/``next``/``previous``/``results``).

    Use this on ModelViewSets where the legacy frontend consumed a flat array
    but we still want a pagination escape hatch for new code / heavy queries.
    """

    #: Explicit opt-in flag, accepted on top of the standard page/page_size.
    paginate_query_param = "paginate"

    @staticmethod
    def _is_truthy(value: Optional[str]) -> bool:
        if value is None:
            return False
        return value.strip().lower() in ("1", "true", "yes", "on")

    def paginate_queryset(self, queryset, request, view=None):
        qp = request.query_params
        opted_in = (
            qp.get("page") is not None
            or qp.get(self.page_size_query_param) is not None
            or self._is_truthy(qp.get(self.paginate_query_param))
        )
        if not opted_in:
            # Returning None tells DRF to skip pagination and serialize the
            # full queryset, which is what the legacy frontend expects.
            return None
        return super().paginate_queryset(queryset, request, view)
