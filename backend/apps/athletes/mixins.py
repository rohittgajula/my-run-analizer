"""Tenant scoping.

A view that forgets to filter returns another athlete's data with no error and no log
line. The failure is invisible until it is a breach, so this is not optional and there
is no "I'll add it later" version.
"""


class AthleteScopedMixin:
    """Filters every queryset to the requesting athlete."""

    def get_queryset(self):
        return super().get_queryset().filter(athlete=self.request.user.athlete)
