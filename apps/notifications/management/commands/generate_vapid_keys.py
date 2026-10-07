import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_vapid_keys():
    """Par de chaves VAPID (P-256) no formato que o navegador e o pywebpush esperam (base64url)."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = _b64(key.private_numbers().private_value.to_bytes(32, "big"))
    public = _b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    return public, private


class Command(BaseCommand):
    help = "Gera as chaves VAPID para as notificações push. Guardar a privada em segredo (variável de ambiente)."

    def handle(self, *args, **opts):
        public, private = generate_vapid_keys()
        self.stdout.write(f"VAPID_PUBLIC_KEY={public}\nVAPID_PRIVATE_KEY={private}\n")
        self.stderr.write("Define as duas variáveis no ambiente (Railway). Se trocares a chave, todos os membros têm de reactivar as notificações.")
