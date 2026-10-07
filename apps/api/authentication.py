"""Tokens da API com validade: um token roubado ou esquecido deixa de servir ao fim de API_TOKEN_TTL_DAYS."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


def token_is_expired(token):
    return token.created < timezone.now() - timedelta(days=settings.API_TOKEN_TTL_DAYS)


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if token_is_expired(token):
            token.delete()
            raise AuthenticationFailed("Token expirado. Inicia sessão novamente.")
        return user, token
