"""Cálculo do ranking mensal e geral, com cache (Redis quando disponível)."""
from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.utils import timezone

CACHE_VERSION_KEY = "leaderboard:version"
CACHE_TTL = 300

PERIODS = {"mes": "Este mês", "geral": "Geral"}
METRICS = {"pontos": "Pontos", "km": "Quilómetros"}


def bump_version():
    try:
        cache.incr(CACHE_VERSION_KEY)
    except ValueError:
        cache.set(CACHE_VERSION_KEY, 2, None)


def _version():
    return cache.get_or_set(CACHE_VERSION_KEY, 1, None)


def month_bounds(day: date):
    start = day.replace(day=1)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def compute(period="mes", metric="pontos", limit=100):
    User = get_user_model()
    today = timezone.localdate()
    users = User.objects.filter(is_active=True, show_on_leaderboard=True)

    if metric == "km":
        run_filter = Q(runs__is_valid=True)
        if period == "mes":
            start, end = month_bounds(today)
            run_filter &= Q(runs__date__gte=start, runs__date__lt=end)
        qs = users.annotate(score=Sum("runs__distance_km", filter=run_filter),
                            runs_count=Count("runs", filter=run_filter))
    else:
        pt_filter = None
        if period == "mes":
            start, end = month_bounds(today)
            tz = timezone.get_current_timezone()
            start_dt = timezone.make_aware(datetime.combine(start, time.min), tz)
            end_dt = timezone.make_aware(datetime.combine(end, time.min), tz)
            pt_filter = Q(point_transactions__created_at__gte=start_dt, point_transactions__created_at__lt=end_dt)
        qs = users.annotate(score=Sum("point_transactions__amount", filter=pt_filter))

    qs = qs.filter(score__gt=0).order_by("-score", "date_joined")[:limit]
    rows, rank, prev = [], 0, None
    for i, u in enumerate(qs, start=1):
        if u.score != prev:
            rank, prev = i, u.score
        rows.append({
            "rank": rank,
            "user_id": u.pk,
            "name": u.display_name,
            "initials": u.initials,
            "member_number": u.member_number,
            "avatar_url": u.avatar.url if u.avatar else "",
            "score": u.score,
        })
    return rows


def get_leaderboard(period="mes", metric="pontos", limit=100):
    period = period if period in PERIODS else "mes"
    metric = metric if metric in METRICS else "pontos"
    today = timezone.localdate()
    key = f"leaderboard:v{_version()}:{period}:{metric}:{limit}:{today:%Y%m}"
    rows = cache.get(key)
    if rows is None:
        rows = compute(period, metric, limit)
        cache.set(key, rows, CACHE_TTL)
    return rows

