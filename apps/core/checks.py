from django.conf import settings
from django.core.checks import Warning, register


@register(deploy=True)
def shared_cache_check(app_configs, **kwargs):
    """O rate-limit do login vive na cache: sem Redis cada worker do gunicorn conta à parte."""
    if "locmem" in settings.CACHES["default"]["BACKEND"].lower():
        return [Warning(
            "A cache é local a cada processo (sem REDIS_URL): o rate-limit do login e o ranking não são partilhados entre workers.",
            hint="Define REDIS_URL (plugin Redis do Railway).", id="rwb.W001",
        )]
    return []
