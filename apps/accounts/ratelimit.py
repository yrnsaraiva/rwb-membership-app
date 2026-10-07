"""Rate-limiting simples baseado em cache (RNF-04: rate-limiting no login)."""
import hashlib

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _key(scope, ident):
    digest = hashlib.sha256(ident.lower().encode()).hexdigest()[:32]
    return f"rl:{scope}:{digest}"


def login_keys(request, email):
    return [_key("login-ip", client_ip(request)), _key("login-email", email or "")]


def is_blocked(request, email):
    limit = settings.LOGIN_RATE_LIMIT_ATTEMPTS
    ip_key, email_key = login_keys(request, email)
    # O limite por IP é mais permissivo (redes móveis partilham IPs via CGNAT)
    return cache.get(email_key, 0) >= limit or cache.get(ip_key, 0) >= limit * 4


def register_failure(request, email):
    window = settings.LOGIN_RATE_LIMIT_WINDOW
    for key in login_keys(request, email):
        cache.add(key, 0, window)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, window)


def reset(request, email):
    cache.delete_many(login_keys(request, email))
