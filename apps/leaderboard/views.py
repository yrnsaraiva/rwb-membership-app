from django.shortcuts import render

from .services import METRICS, PERIODS, get_leaderboard


def leaderboard(request):
    period = request.GET.get("periodo", "mes")
    metric = request.GET.get("metrica", "pontos")
    period = period if period in PERIODS else "mes"
    metric = metric if metric in METRICS else "pontos"
    rows = get_leaderboard(period, metric)
    me = None
    if request.user.is_authenticated:
        me = next((r for r in rows if r["user_id"] == request.user.pk), None)
    return render(request, "leaderboard/index.html", {
        "rows": rows,
        # Ordem visual do pódio: 2.º, 1.º, 3.º
        "podium": [(pos, rows[pos - 1]) for pos in (2, 1, 3) if len(rows) >= pos],
        "rest": rows[3:],
        "me": me,
        "period": period,
        "metric": metric,
        "periods": PERIODS,
        "metrics": METRICS,
    })
