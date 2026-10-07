"""Rate-limiting simples baseado em cache (RNF-04: rate-limiting no login)."""
import hashlib

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    """IP do cliente. Só confia nos proxies configurados (TRUSTED_PROXY_COUNT): o X-Forwarded-For é uma
    lista em que apenas as últimas entradas foram acrescentadas pela nossa infra-estrutura."""
    proxies = settings.TRUSTED_PROXY_COUNT
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proxies and forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-proxies] if len(hops) >= proxies else hops[0]
    return request.META.get("REMOTE_ADDR", "")


def _key(scope, *parts):
    digest = hashlib.sha256("|".join(p.lower() for p in parts).encode()).hexdigest()[:32]
    return f"rl:{scope}:{digest}"


def login_keys(request, email):
    """(par IP+email, IP, email). Cada contador tem o seu limite em is_blocked()."""
    ip, email = client_ip(request), (email or "").strip()
    return [_key("login-pair", ip, email), _key("login-ip", ip), _key("login-email", email)]


def is_blocked(request, email):
    limit = settings.LOGIN_RATE_LIMIT_ATTEMPTS
    pair_key, ip_key, email_key = login_keys(request, email)
    # Limite estrito por (IP, email): quem erra a palavra-passe não bloqueia o dono da conta noutro IP.
    # Limites mais largos por IP (CGNAT das operadoras) e por email (ataque distribuído).
    return (cache.get(pair_key, 0) >= limit
            or cache.get(ip_key, 0) >= limit * 4
            or cache.get(email_key, 0) >= limit * 6)


def register_failure(request, email):
    window = settings.LOGIN_RATE_LIMIT_WINDOW
    for key in login_keys(request, email):
        cache.add(key, 0, window)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, window)


def reset(request, email):
    # Só limpa o par: os limites por IP e por email continuam a contar tentativas falhadas de outros.
    cache.delete(login_keys(request, email)[0])
