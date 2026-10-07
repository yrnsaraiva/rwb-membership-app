from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.events.models import Registration

from . import services
from .forms import RunForm
from .models import PointTransaction, Run


@login_required
def dashboard(request):
    user = request.user
    upcoming = (
        Registration.objects.filter(user=user, status=Registration.Status.CONFIRMED, event__starts_at__gte=timezone.now())
        .select_related("event").order_by("event__starts_at")[:5]
    )
    return render(request, "activity/dashboard.html", {
        "stats": services.member_stats(user),
        "week": services.weekly_activity(user),
        "trend": services.weeks_trend(user),
        "upcoming": upcoming,
        "recent_runs": Run.objects.filter(user=user).prefetch_related("point_transactions")[:5],
    })


@login_required
@require_http_methods(["GET", "POST"])
def run_create(request):
    form = RunForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        run = services.log_run(
            request.user, date=d["date"], distance_km=d["distance_km"], duration=d["duration"],
            title=d["title"], notes=d["notes"], event=d.get("event"),
        )
        pace = services.format_pace(run.pace_seconds)
        messages.success(request, f"Corrida registada: {run.distance_km} km a {pace}/km · +{run.points} pontos 🔥")
        return redirect("activity:dashboard")
    return render(request, "activity/run_form.html", {"form": form})


@login_required
def run_list(request):
    runs = Run.objects.filter(user=request.user).select_related("event").prefetch_related("point_transactions")
    page = Paginator(runs, 20).get_page(request.GET.get("page"))
    return render(request, "activity/run_list.html", {"page": page, "stats": services.member_stats(request.user)})


@login_required
@require_POST
def run_delete(request, pk):
    run = get_object_or_404(Run, pk=pk, user=request.user)
    services.delete_run(run)
    messages.info(request, "Corrida apagada e pontos removidos.")
    return redirect("activity:run_list")


@login_required
def points_history(request):
    qs = PointTransaction.objects.filter(user=request.user)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "activity/points.html", {"page": page, "stats": services.member_stats(request.user)})
