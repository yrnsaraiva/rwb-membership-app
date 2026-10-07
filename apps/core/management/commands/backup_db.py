"""
Backup da base de dados PostgreSQL (RNF-07). Agendar semanalmente (cron do Railway):
    python manage.py backup_db --keep 8
Guarda ficheiros .sql.gz em BACKUP_DIR (por defeito ./backups). Em produção, montar um volume
ou sincronizar esta pasta para armazenamento externo.
"""
import gzip
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Cria um dump comprimido da base de dados e mantém os N mais recentes."

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int, default=8)
        parser.add_argument("--dir", default=os.environ.get("BACKUP_DIR", str(settings.BASE_DIR / "backups")))

    def handle(self, *args, **opts):
        db = settings.DATABASES["default"]
        out_dir = Path(opts["dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        if "sqlite" in db["ENGINE"]:
            target = out_dir / f"rwb-{stamp}.sqlite3.gz"
            with open(db["NAME"], "rb") as src, gzip.open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        elif "postgresql" in db["ENGINE"]:
            if not shutil.which("pg_dump"):
                raise CommandError("pg_dump não encontrado no PATH.")
            target = out_dir / f"rwb-{stamp}.sql.gz"
            env = {**os.environ, "PGPASSWORD": db.get("PASSWORD") or ""}
            cmd = ["pg_dump", "--no-owner", "--no-privileges", "-h", db.get("HOST") or "localhost",
                   "-p", str(db.get("PORT") or 5432), "-U", db.get("USER") or "", db["NAME"]]
            with gzip.open(target, "wb") as dst:
                proc = subprocess.run(cmd, env=env, capture_output=True, check=False)
                if proc.returncode != 0:
                    raise CommandError(proc.stderr.decode(errors="replace"))
                dst.write(proc.stdout)
        else:
            raise CommandError(f"Motor de base de dados não suportado: {db['ENGINE']}")

        backups = sorted(out_dir.glob("rwb-*.gz"))
        for old in backups[: max(len(backups) - opts["keep"], 0)]:
            old.unlink()
        self.stdout.write(self.style.SUCCESS(f"Backup criado: {target}"))
