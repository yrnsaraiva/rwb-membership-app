"""Regras de negócio de atividade: pontos, streaks e estatísticas (RF-03, RF-04, RF-05)."""
import math
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import PointTransaction, Run


def today():
    return timezone.localdate()


# --- Formatação -----------------------------------------------------------------
def format_pace(seconds):
    if not seconds:
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


def format_duration(td):
    if td is None:
        return "—"
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# --- Pontos e streaks --------------------------------------------------------------
def points_for_distance(distance_km) -> int:
    return int(math.floor(Decimal(distance_km) * settings.RWB_POINTS_PER_KM))


def run_dates(user):
    return set(Run.objects.valid().filter(user=user).values_list("date", flat=True).distinct())


def streak_ending_at(dates: set, day: date) -> int:
    count = 0
    while day in dates:
        count += 1
        day -= timedelta(days=1)
    return count


def current_streak(user, dates=None) -> int:
    """Dias consecutivos com corrida. Continua 'viva' se o último dia foi ontem."""
    dates = run_dates(user) if dates is None else dates
    t = today()
    if t in dates:
        return streak_ending_at(dates, t)
    return streak_ending_at(dates, t - timedelta(days=1))


def longest_streak(dates: set) -> int:
    best = 0
    for d in dates:
        if d - timedelta(days=1) not in dates:  # início de uma sequência
            best = max(best, streak_ending_at_forward(dates, d))
    return best


def streak_ending_at_forward(dates: set, start: date) -> int:
    count = 0
    while start in dates:
        count += 1
        start += timedelta(days=1)
    return count


def run_limit_error(user, *, date, distance_km, duration) -> str | None:
    """Regras anti-batota partilhadas pelo formulário e pela API. Devolve a mensagem de erro, ou None."""
    same_day = Run.objects.filter(user=user, date=date)
    if same_day.count() >= settings.RWB_MAX_RUNS_PER_DAY:
        return f"Máximo de {settings.RWB_MAX_RUNS_PER_DAY} corridas por dia."
    if same_day.filter(distance_km=distance_km, duration=duration).exists():
        return "Já registaste uma corrida igual neste dia."
    total = same_day.aggregate(km=Sum("distance_km"))["km"] or Decimal("0")
    if total + Decimal(distance_km) > settings.RWB_MAX_DAILY_KM:
        return f"Máximo de {settings.RWB_MAX_DAILY_KM} km por dia."
    return None


@transaction.atomic
def log_run(user, *, date, distance_km, duration, title="", notes="", event=None) -> Run:
    run = Run.objects.create(user=user, date=date, distance_km=distance_km, duration=duration,
                             title=title, notes=notes, event=event)
    award_run_points(run)
    return run


def award_run_points(run: Run):
    points = points_for_distance(run.distance_km)
    if points:
        PointTransaction.objects.create(
            user=run.user, amount=points, reason=PointTransaction.Reason.RUN, run=run,
            reference_date=run.date, description=f"{run.distance_km} km",
        )
    _maybe_award_streak_bonus(run.user, run.date)


def _maybe_award_streak_bonus(user, day):
    every = settings.RWB_STREAK_BONUS_EVERY
    if not every or not settings.RWB_STREAK_BONUS_POINTS:
        return
    streak = streak_ending_at(run_dates(user), day)
    if streak and streak % every == 0:
        try:
            with transaction.atomic():
                PointTransaction.objects.create(
                    user=user, amount=settings.RWB_STREAK_BONUS_POINTS,
                    reason=PointTransaction.Reason.STREAK_BONUS, reference_date=day,
                    description=f"{streak} dias seguidos",
                )
        except IntegrityError:
            pass  # bónus desse dia já atribuído


@transaction.atomic
def delete_run(run: Run):
    user, day = run.user, run.date
    run.delete()  # os movimentos de pontos da corrida caem em cascata
    _cleanup_streak_bonus(user, day)


@transaction.atomic
def set_run_validity(run: Run, is_valid: bool, note: str = ""):
    """Moderação: invalidar remove os pontos; revalidar volta a atribuí-los."""
    if run.is_valid == is_valid:
        return
    run.is_valid = is_valid
    run.moderation_note = note[:200]
    run.save(update_fields=["is_valid", "moderation_note"])
    if is_valid:
        award_run_points(run)
    else:
        run.point_transactions.all().delete()
        _cleanup_streak_bonus(run.user, run.date)


def _cleanup_streak_bonus(user, day):
    if not Run.objects.valid().filter(user=user, date=day).exists():
        PointTransaction.objects.filter(
            user=user, reason=PointTransaction.Reason.STREAK_BONUS, reference_date=day
        ).delete()


# --- Estatísticas / dashboard ------------------------------------------------------
def member_stats(user):
    runs = Run.objects.valid().filter(user=user)
    agg = runs.aggregate(km=Sum("distance_km"), time=Sum("duration"), n=Count("id"))
    km = agg["km"] or Decimal("0")
    total_time = agg["time"] or timedelta()
    t = today()
    month_km = runs.filter(date__year=t.year, date__month=t.month).aggregate(km=Sum("distance_km"))["km"] or Decimal("0")
    points = PointTransaction.objects.filter(user=user).aggregate(p=Sum("amount"))["p"] or 0
    month_points = PointTransaction.objects.filter(
        user=user, created_at__year=t.year, created_at__month=t.month
    ).aggregate(p=Sum("amount"))["p"] or 0
    dates = run_dates(user)
    avg_pace = int(total_time.total_seconds() / float(km)) if km else None
    return {
        "total_km": km,
        "total_runs": agg["n"],
        "total_time": total_time,
        "total_time_display": format_duration(total_time),
        "month_km": month_km,
        "points": points,
        "month_points": month_points,
        "current_streak": current_streak(user, dates),
        "longest_streak": longest_streak(dates),
        "ran_today": t in dates,
        "avg_pace": avg_pace,
        "avg_pace_display": format_pace(avg_pace),
    }


WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def weekly_activity(user):
    """Km por dia da semana corrente (segunda a domingo) — gráfico do dashboard."""
    t = today()
    monday = t - timedelta(days=t.weekday())
    rows = (
        Run.objects.valid()
        .filter(user=user, date__gte=monday, date__lte=monday + timedelta(days=6))
        .values("date").annotate(km=Sum("distance_km"))
    )
    by_day = {r["date"]: r["km"] for r in rows}
    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        days.append({"label": WEEKDAY_LABELS[i], "date": d, "km": by_day.get(d, Decimal("0")), "is_today": d == t,
                     "is_future": d > t})
    return _with_heights(days)


def weeks_trend(user, weeks=8):
    """Km totais das últimas N semanas."""
    t = today()
    this_monday = t - timedelta(days=t.weekday())
    start = this_monday - timedelta(weeks=weeks - 1)
    rows = Run.objects.valid().filter(user=user, date__gte=start).values_list("date", "distance_km")
    totals = [Decimal("0")] * weeks
    for d, km in rows:
        idx = (d - start).days // 7
        if 0 <= idx < weeks:
            totals[idx] += km
    items = []
    for i, km in enumerate(totals):
        monday = start + timedelta(weeks=i)
        items.append({"label": f"{monday:%d/%m}", "km": km, "is_today": i == weeks - 1, "is_future": False})
    return _with_heights(items)


def _with_heights(items):
    peak = max((float(i["km"]) for i in items), default=0)
    for i in items:
        i["height"] = round(float(i["km"]) / peak * 100) if peak else 0
    return items
