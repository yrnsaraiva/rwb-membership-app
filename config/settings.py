"""
Configuração do RWB member app (RunWithBroto).

Toda a configuração sensível vem de variáveis de ambiente (ver .env.example).
Em desenvolvimento, sem DATABASE_URL, usa SQLite; em produção (Railway) usa PostgreSQL.
"""
import os
import sys
from pathlib import Path

import dj_database_url
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# Carrega um ficheiro .env simples em desenvolvimento (sem dependências extra).
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
DEBUG = env_bool("DJANGO_DEBUG", False) and not TESTING
SECRET_KEY = env("DJANGO_SECRET_KEY") or ("dev-insecure-key-change-me" if (DEBUG or TESTING) else None)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY é obrigatória em produção.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
if env("RAILWAY_PUBLIC_DOMAIN"):
    ALLOWED_HOSTS.append(env("RAILWAY_PUBLIC_DOMAIN"))
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if env("RAILWAY_PUBLIC_DOMAIN"):
    CSRF_TRUSTED_ORIGINS.append(f"https://{env('RAILWAY_PUBLIC_DOMAIN')}")

SITE_URL = env("SITE_URL", "http://localhost:8000").rstrip("/")
SITE_NAME = "RunWithBroto"
RELEASE = (env("RAILWAY_GIT_COMMIT_SHA") or env("RELEASE") or "v1")[:12]

INSTALLED_APPS = [
    # Django Unfold (tema do admin) — tem de vir antes de django.contrib.admin
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    # Módulos do RWB
    "apps.core",
    "apps.accounts",
    "apps.events",
    "apps.activity",
    "apps.leaderboard",
    "apps.billing",
    "apps.shop",
    "apps.panel",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
                "apps.shop.context_processors.cart",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de dados -----------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Cache (Redis opcional) ---------------------------------------------------
if env("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_URL"),
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "rwb",
        }
    }

# Autenticação ---------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "activity:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Proxies de confiança à frente da app (Railway = 1). Só o IP acrescentado pelo último proxy é fiável;
# o resto do X-Forwarded-For vem do cliente e pode ser forjado.
TRUSTED_PROXY_COUNT = int(env("TRUSTED_PROXY_COUNT", "0" if (DEBUG or TESTING) else "1"))

# Rate-limiting do login (RNF-04)
LOGIN_RATE_LIMIT_ATTEMPTS = int(env("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW = int(env("LOGIN_RATE_LIMIT_WINDOW", "900"))  # segundos

# Internacionalização (RNF-02) ---------------------------------------------
LANGUAGE_CODE = "pt"
LANGUAGES = [("pt", "Português")]
TIME_ZONE = "Africa/Maputo"
USE_I18N = True
USE_TZ = True
CURRENCY = "MZN"

# Ficheiros estáticos e media -----------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
# No MVP o Django serve os uploads (avatares, capas). No Railway, montar um Volume em MEDIA_ROOT.
# Na fase seguinte, mover para S3/R2 e desligar isto.
SERVE_MEDIA = env_bool("SERVE_MEDIA", True)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not (DEBUG or TESTING)
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email (Hostinger SMTP) ------------------------------------------------------
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "465"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", EMAIL_PORT == 465)
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", EMAIL_PORT == 587)
    EMAIL_TIMEOUT = 15
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "RunWithBroto <no-reply@runwithbroto.co.mz>")

# Django REST Framework ---------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.ExpiringTokenAuthentication",  # primeiro: devolve 401 (e não 403) com token inválido
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "240/min", "login": "10/min", "register": "10/hour",
                              "password_reset": "5/hour"},
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "RunWithBroto API",
    "DESCRIPTION": (
        "API REST do clube de corrida RunWithBroto (membros, eventos, corridas, pontos e ranking).\n\n"
        "**Autenticação:** `POST /api/v1/auth/token/` com `{username: email, password}` devolve um token; "
        "enviar em todos os pedidos como `Authorization: Token <token>`. Os tokens expiram (ver `expires_in`)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "RegistrationStatusEnum": "apps.events.models.Registration.Status",
        "OrderStatusEnum": "apps.shop.models.Order.Status",
        "SubscriptionStatusEnum": "apps.billing.models.Subscription.Status",
    },
    "SERVERS": [{"url": SITE_URL}],
}
PUSH_ENABLED = env_bool("PUSH_ENABLED", False)  # só activar quando o transporte FCM estiver implementado
API_TOKEN_TTL_DAYS = int(env("API_TOKEN_TTL_DAYS", "30"))  # os tokens da API expiram e são renovados no login

# Regras de negócio (pontos) ---------------------------------------------------
RWB_POINTS_PER_KM = int(env("RWB_POINTS_PER_KM", "10"))
RWB_STREAK_BONUS_EVERY = int(env("RWB_STREAK_BONUS_EVERY", "7"))   # a cada N dias seguidos
RWB_STREAK_BONUS_POINTS = int(env("RWB_STREAK_BONUS_POINTS", "50"))
RWB_EVENT_CHECKIN_POINTS = int(env("RWB_EVENT_CHECKIN_POINTS", "100"))
RWB_MAX_RUN_KM = int(env("RWB_MAX_RUN_KM", "100"))  # corridas acima disto são rejeitadas
RWB_MIN_PACE_SEC_PER_KM = int(env("RWB_MIN_PACE_SEC_PER_KM", "150"))  # 2:30/km = limite humano razoável
RWB_MAX_RUNS_PER_DAY = int(env("RWB_MAX_RUNS_PER_DAY", "4"))  # anti-batota: corridas por dia e membro
RWB_MAX_DAILY_KM = int(env("RWB_MAX_DAILY_KM", "100"))        # anti-batota: km totais por dia e membro

# Loja -----------------------------------------------------------------------------
RWB_PREMIUM_SHOP_DISCOUNT = int(env("RWB_PREMIUM_SHOP_DISCOUNT", "10"))   # % de desconto para membros premium
RWB_SHOP_DELIVERY_FEE = int(env("RWB_SHOP_DELIVERY_FEE", "150"))          # MZN, entrega ao domicílio
RWB_SHOP_HOLD_DAYS = int(env("RWB_SHOP_HOLD_DAYS", "3"))                  # dias até cancelar encomenda não paga
RWB_SHOP_MPESA_NUMBER = env("RWB_SHOP_MPESA_NUMBER", "")                  # ex.: 84 123 4567
RWB_SHOP_MPESA_NAME = env("RWB_SHOP_MPESA_NAME", "RunWithBroto")
RWB_SHOP_BANK_DETAILS = env("RWB_SHOP_BANK_DETAILS", "")                  # ex.: BCI · NIB 0008 ...

# Admin (Django Unfold) ------------------------------------------------------------
UNFOLD = {
    "SITE_TITLE": "RWB Admin",
    "SITE_HEADER": "RunWithBroto",
    "SITE_SUBHEADER": "Running Club · Maputo",
    "SITE_URL": "/",
    "SITE_SYMBOL": "directions_run",
    "SITE_LOGO": {
        "light": lambda request: static("img/brand/wordmark-ink.png"),
        "dark": lambda request: static("img/brand/wordmark-yellow.png"),
    },
    "SITE_FAVICONS": [
        {"rel": "icon", "sizes": "64x64", "type": "image/png", "href": lambda request: static("img/icons/favicon-64.png")},
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "BORDER_RADIUS": "10px",
    # Paleta da marca (#FABB00 = 400, #E1A800 = 500) em OKLCH, formato exigido pelo Unfold
    "COLORS": {
        "primary": {
            "50": "oklch(98.7% .022 95)",
            "100": "oklch(96.2% .059 95)",
            "200": "oklch(92.4% .12 95)",
            "300": "oklch(87.9% .169 91)",
            "400": "oklch(82.7% .17 84)",
            "500": "oklch(76.4% .157 84)",
            "600": "oklch(66.6% .157 70)",
            "700": "oklch(55.5% .146 60)",
            "800": "oklch(47.3% .124 55)",
            "900": "oklch(41.4% .105 55)",
            "950": "oklch(27.9% .077 50)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Clube",
                "items": [
                    {"title": "Painel do clube", "icon": "space_dashboard", "link": reverse_lazy("panel:index")},
                    {"title": "Membros", "icon": "group", "link": reverse_lazy("admin:accounts_user_changelist")},
                    {"title": "Eventos", "icon": "event", "link": reverse_lazy("admin:events_event_changelist")},
                    {"title": "Inscrições", "icon": "how_to_reg", "link": reverse_lazy("admin:events_registration_changelist")},
                ],
            },
            {
                "title": "Atividade",
                "items": [
                    {"title": "Corridas", "icon": "directions_run", "link": reverse_lazy("admin:activity_run_changelist")},
                    {"title": "Pontos", "icon": "military_tech", "link": reverse_lazy("admin:activity_pointtransaction_changelist")},
                ],
            },
            {
                "title": "Loja",
                "items": [
                    {"title": "Encomendas", "icon": "receipt_long", "link": reverse_lazy("admin:shop_order_changelist"),
                     "badge": "apps.shop.admin.pending_orders_badge"},
                    {"title": "Produtos", "icon": "checkroom", "link": reverse_lazy("admin:shop_product_changelist")},
                    {"title": "Categorias", "icon": "category", "link": reverse_lazy("admin:shop_category_changelist")},
                ],
            },
            {
                "title": "Premium",
                "items": [
                    {"title": "Subscrições", "icon": "workspace_premium", "link": reverse_lazy("admin:billing_subscription_changelist")},
                    {"title": "Planos", "icon": "sell", "link": reverse_lazy("admin:billing_plan_changelist")},
                ],
            },
            {
                "title": "Sistema",
                "collapsible": True,
                "items": [
                    {"title": "Grupos e permissões", "icon": "admin_panel_settings", "link": reverse_lazy("admin:auth_group_changelist")},
                ],
            },
        ],
    },
}

# Segurança (RNF-04) ------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG and not TESTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "2592000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

# Monitorização de erros (opcional): definir SENTRY_DSN
if env("SENTRY_DSN") and not TESTING:
    import sentry_sdk

    sentry_sdk.init(dsn=env("SENTRY_DSN"), release=RELEASE, environment="development" if DEBUG else "production",
                    traces_sample_rate=float(env("SENTRY_TRACES_RATE", "0")), send_default_pii=False)

if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
