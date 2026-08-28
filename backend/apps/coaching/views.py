import dataclasses

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.activities.models import Activity

from .client import AIUnavailable
from .models import AIRequestLog
from .services import BudgetExceeded, analyse_run, guidance_for, weekly_review


def _degrade(exc: Exception, status: int = 503):
    """Never surface a raw failure. The athlete gets an explanation and the app
    carries on with its deterministic plan, which does not need the model."""
    return Response(
        {"available": False, "detail": str(exc), "budget": isinstance(exc, BudgetExceeded)},
        status=429 if isinstance(exc, BudgetExceeded) else status,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def guidance(request):
    try:
        result, cached = guidance_for(request.user.athlete)
    except AIUnavailable as exc:
        return _degrade(exc)
    return Response({"available": True, "cached": cached, **result.model_dump()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def review(request):
    try:
        result, cached = weekly_review(request.user.athlete)
    except AIUnavailable as exc:
        return _degrade(exc)
    return Response({"available": True, "cached": cached, **result.model_dump()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def run_analysis(request, pk: int):
    activity = Activity.objects.filter(
        athlete=request.user.athlete, pk=pk
    ).select_related("metrics").first()
    if activity is None:
        return Response({"detail": "Not found."}, status=404)
    if getattr(activity, "metrics", None) is None:
        return Response(
            {"available": False,
             "detail": "This activity was not segmented, so there is nothing to interpret."},
            status=400,
        )
    try:
        result, cached = analyse_run(request.user.athlete, activity)
    except AIUnavailable as exc:
        return _degrade(exc)
    return Response({"available": True, "cached": cached, **result.model_dump()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def usage(request):
    """What the coaching has cost this athlete. Visible, not buried in a dashboard."""
    athlete = request.user.athlete
    start = athlete.local_today.replace(day=1)
    rows = AIRequestLog.objects.filter(athlete=athlete, created_at__date__gte=start)
    billable = rows.exclude(status=AIRequestLog.Status.CACHED)
    return Response({
        "month_start": start,
        "calls": billable.count(),
        "input_tokens": sum(r.input_tokens for r in billable),
        "output_tokens": sum(r.output_tokens for r in billable),
        "estimated_cost_usd": round(sum(r.estimated_cost_usd for r in billable), 4),
        "failures": rows.filter(status=AIRequestLog.Status.ERROR).count(),
    })
