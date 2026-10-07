# RWB member app - MVP (RunWithBroto)

Plataforma do clube de corrida RunWithBroto: membros, cartão digital com QR, eventos com inscrição e vagas,
registo de corridas com pontos e streaks, ranking mensal/geral, painel de gestão e API REST.
Monólito modular em **Django 5.2 LTS + DRF**, templates com **Tailwind**, **PostgreSQL**, PWA instalável, tema **claro/escuro**, **loja de merch** e admin com **Django Unfold**.

---

## Arranque rápido (desenvolvimento)

Requisitos: **Python 3.12+** (exigido pelo Django Unfold) e Node 18+ opcional, só para compilar o CSS.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # DJANGO_DEBUG=1 já vem activo
python manage.py migrate
python manage.py createsuperuser                         # pede email, nome, apelido, palavra-passe
python manage.py seed_demo                               # opcional: planos, eventos, 10 membros e corridas
python manage.py runserver
```

Abrir http://localhost:8000 · loja em `/loja/` · painel do clube em `/painel/` · admin (Unfold) em `/django-admin/` · API em `/api/v1/`.

**CSS:** sem compilar, em modo DEBUG a app usa o Tailwind via CDN automaticamente. Para o CSS real (o que vai para produção):

```bash
npm install
npm run build:css        # ou: npm run watch:css durante o desenvolvimento
```

**Testes:**

```bash
python manage.py test
python manage.py makemigrations --check --dry-run   # confirma que as migrações estão alinhadas com os modelos
```

---

## Deploy no Railway

1. Criar projecto no Railway a partir do repositório (usa o `Dockerfile` e o `railway.json`).
2. Adicionar o plugin **PostgreSQL** → o Railway injecta `DATABASE_URL`.
3. (Opcional) adicionar **Redis** → definir `REDIS_URL` (cache do ranking).
4. Adicionar um **Volume** montado em `/app/media` (fotografias de perfil e capas de eventos).
5. Variáveis de ambiente mínimas:
   - `DJANGO_SECRET_KEY` — chave longa e aleatória
   - `SITE_URL` — ex.: `https://app.runwithbroto.co.mz`
   - `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS` — para o domínio próprio (o domínio `*.railway.app` é adicionado automaticamente)
   - `REDIS_URL` — **recomendado em produção**: o rate-limit do login e o ranking precisam de cache partilhada entre workers (`check --deploy` avisa se faltar)
   - `TRUSTED_PROXY_COUNT` — nº de proxies à frente da app (omissão: 1, o Railway); usado para obter o IP real do cliente
   - Opcionais: `SENTRY_DSN` (monitorização de erros), `API_TOKEN_TTL_DAYS` (validade dos tokens da API, 30), `RWB_MAX_RUNS_PER_DAY` (4) e `RWB_MAX_DAILY_KM` (100), limites anti-batota
   - Loja: `RWB_SHOP_MPESA_NUMBER`, `RWB_SHOP_MPESA_NAME`, `RWB_SHOP_BANK_DETAILS` (aparecem nas instruções de pagamento), `RWB_SHOP_DELIVERY_FEE`, `RWB_PREMIUM_SHOP_DISCOUNT`
   - Email Hostinger: `EMAIL_HOST=smtp.hostinger.com`, `EMAIL_PORT=465`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`
6. Após o primeiro deploy: `railway run python manage.py createsuperuser`.
7. Tarefas agendadas (Railway Cron, serviço separado com o mesmo código):
   - diário: `python manage.py expire_subscriptions`
   - diário: `python manage.py cancel_stale_orders` (cancela encomendas por pagar há mais de `RWB_SHOP_HOLD_DAYS` dias e devolve o stock)
   - semanal (RNF-07): `python manage.py backup_db --keep 8` (grava em `BACKUP_DIR`; montar volume ou sincronizar para armazenamento externo). O Postgres do Railway também tem backups próprios — activar.

O arranque corre `migrate` automaticamente e o healthcheck usa `/healthz`.

---

## O que está implementado (mapa aos requisitos)

| Requisito | Onde | Notas |
|---|---|---|
| **RF-01** Autenticação e perfil | `apps/accounts` | Login por email, registo, recuperação de palavra-passe, perfil editável com foto, nº de sócio único `RWB-00042`, cartão digital com QR (SVG inline) |
| **RF-02** Eventos | `apps/events`, `apps/panel` | CRUD no painel, listagem pública (próximos/passados, filtro por tipo), detalhe, inscrição com escolha de distância, cancelamento, vagas com bloqueio de linha (sem overbooking), janela de inscrições, eventos só-premium, email de confirmação, ficheiro `.ics` |
| **RF-03** Dashboard | `apps/activity` | Distância total e do mês, pontos, streak actual/melhor, ritmo médio, gráfico semanal + últimas 8 semanas, eventos inscritos, últimas corridas |
| **RF-04** Registo de corridas | `apps/activity` | Data, distância, duração (h/min/s), ritmo calculado ao vivo, histórico, apagar; validações anti-batota (sem datas futuras, máx. 60 dias atrás, máx. 100 km, ritmo mínimo 2:30/km) |
| **RF-05** Pontos e ranking | `apps/activity`, `apps/leaderboard` | Livro de pontos auditável: 10 pts/km, bónus de 50 pts a cada 7 dias seguidos, 100 pts por presença em evento, ajustes manuais. Ranking mensal e geral, por pontos ou km, empates partilham lugar, cache invalidada automaticamente, membros podem sair do ranking |
| **RF-06** Administração | `apps/panel` (+ Django admin) | Resumo (KPIs, novos membros/semana, top km), membros (pesquisa, ficha, desactivar, ajustar pontos, CSV), eventos (inscritos, presenças, CSV), **check-in por QR** (staff lê o QR do cartão → marca presença), moderação de corridas suspeitas, subscrições |
| **RF-07** Premium | `apps/billing` | Planos, pedido de subscrição, activação manual com método/referência, renovação que estende a partir do fim actual, expiração. **Sem M-Pesa nesta fase** |
| **Loja de merch** | `apps/shop`, `apps/panel` | Catálogo com categorias, fotos e variantes (tamanhos) com stock; carrinho (também para visitantes); checkout com levantamento em evento, no ponto do clube ou entrega (taxa configurável); **stock reservado** ao encomendar com bloqueio de linha; desconto automático para premium (10% por defeito); instruções de pagamento M-Pesa/transferência; estados *por pagar → pago → pronto → entregue*; emails ao membro e ao staff; cancelamento automático de encomendas não pagas; gestão no painel (`/painel/encomendas/`) e produtos/stock no admin |
| **Tema claro/escuro** | `static/css/components.css`, `base.html` | Paleta oficial (ink #0B0B0B, paper #FFFFFF, brand #FABB00…). Segue o sistema por defeito; botão ☾/☀ no topo e opção Automático/Claro/Escuro no Perfil (guardado no dispositivo, sem "flash" ao carregar) |
| **Admin Django Unfold** | `config/settings.py` (`UNFOLD`), `apps/*/admin.py` | Cores da marca, logótipo claro/escuro, menu lateral por áreas (Clube, Atividade, Loja, Premium) com contador de encomendas por pagar, acções em massa (marcar pagas/prontas/entregues) |
| RNF-01 Performance | — | Sem frameworks JS (~3 KB de JS), CSS compilado e minificado, SVG inline, whitenoise com compressão e cache longa |
| RNF-02 pt-MZ / MZN | `settings.py`, `rwb` filters | Tudo em português, fuso `Africa/Maputo`, valores `1 500 MZN`, km `12,5` |
| RNF-03 Mobile-first, Oswald/Inter, escuro | `templates/`, `static/css/components.css` | Barra de navegação inferior no telemóvel, botão central "Correr" |
| RNF-04 Segurança | — | HTTPS forçado, HSTS, cookies seguros, PBKDF2, rate-limit no login (5 tentativas / 15 min por email; mais largo por IP por causa do CGNAT das operadoras), CSRF, throttling na API |
| RNF-05/06 Disponibilidade e picos | — | Healthcheck, gunicorn multi-worker, `select_for_update` nas inscrições, ranking em cache (Redis quando disponível) |
| RNF-07 Backup | `manage.py backup_db` | Dump comprimido com rotação |
| RNF-09 PWA | `/manifest.webmanifest`, `/sw.js` | Instalável em Android/iOS, página offline, cartão e dashboard disponíveis offline depois da primeira visita (cache limpa ao terminar sessão) |

### API REST (`/api/v1/`) — base para a app nativa (fase 3)

Documentação interactiva (OpenAPI 3, Swagger UI) em **`/api/v1/docs/`**; o esquema em `/api/v1/schema/` serve para gerar clientes (Swift, Kotlin, TypeScript). Exportar: `python manage.py spectacular --file schema.yml`. O CI valida o esquema sem avisos, por isso novos endpoints têm de ser documentados (`@extend_schema`).

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `auth/token/` | `{username: email, password}` → `{token, expires_in}` (usar `Authorization: Token …`). Tem rate-limit por conta/IP; o token expira e é revogado ao mudar a palavra-passe |
| POST | `auth/logout/` | Revoga o token actual |
| GET/PATCH | `me/` | Perfil do membro |
| GET | `me/dashboard/` | Estatísticas, semana, próximos eventos |
| GET | `events/`, `events/?when=past`, `events/{slug}/` | Eventos |
| POST | `events/{slug}/register/`, `events/{slug}/cancel/` | Inscrição / cancelamento |
| GET/POST/DELETE | `runs/`, `runs/{id}/` | Corridas (`duration_seconds` no POST) |
| GET | `points/` | Movimentos de pontos |
| GET | `leaderboard/?period=mes\|geral&metric=pontos\|km` | Ranking (público) |

---

## Estrutura

```
config/            settings, urls, wsgi
apps/core          página inicial, PWA (manifest, service worker, offline), emails, filtros de template, seed_demo, backup_db
apps/accounts      utilizador (email), nº sócio, cartão QR, verificação, login com rate-limit
apps/events        eventos, inscrições, regras de vagas, presenças, .ics
apps/activity      corridas, livro de pontos, streaks, estatísticas do dashboard
apps/leaderboard   ranking com cache
apps/billing       planos e subscrições premium (activação manual)
apps/shop          loja de merch: produtos, variantes/stock, carrinho, encomendas
apps/panel         painel de gestão do clube (staff)
apps/api           API REST (DRF)
templates/         HTML (Tailwind + components.css), emails
static/            CSS de componentes, JS, ícones PWA
```

**Regras de pontos** configuráveis por variáveis de ambiente: `RWB_POINTS_PER_KM`, `RWB_STREAK_BONUS_EVERY`,
`RWB_STREAK_BONUS_POINTS`, `RWB_EVENT_CHECKIN_POINTS`, `RWB_MAX_RUN_KM`, `RWB_MIN_PACE_SEC_PER_KM`.

**Cores/identidade:** variáveis no topo de `static/css/components.css` (um bloco para o tema claro, outro para o escuro) e em `tailwind.config.js`.
Logótipos em `static/img/brand/` (versão amarela para fundo escuro, preta para fundo claro, gerados a partir do logótipo oficial). No tema claro, o amarelo da marca é usado em botões e destaques; para **texto** usa-se um amarelo escurecido (`--accent: #8A6500`), porque #FABB00 sobre branco não tem contraste legível.

**Loja — como começar:** Admin → Loja → Categorias/Produtos. Cada produto precisa de pelo menos uma **variante** (ex.: S/M/L ou "Tamanho único") com stock; as fotos são opcionais (sem foto aparece o logótipo). `python manage.py seed_demo` cria 5 produtos de exemplo.

**Tornar alguém administrador do clube:** Django admin → Membros → marcar "staff status". Staff acede a `/painel/`.

---

## Próximos passos

**Fase 1b — API C2B (já preparado):** serve para o premium **e** para a loja (`Order` já tem `payment_method`, `payment_reference`, `paid_at`; o callback só precisa de chamar `shop.services.mark_paid`).
1. Modelo `Payment` (FK para `Subscription`, `msisdn`, `amount`, `transaction_reference`, `third_party_reference`, `conversation_id`, `status`, `raw_response`).
2. Serviço `billing/mpesa.py`: gerar o bearer token (chave de API encriptada com a chave pública RSA), chamar `c2bPayment/singleStage`, `queryTransactionStatus` e `reversal`.
3. Na página Premium, pedir o número M-Pesa → criar `Payment(pending)` → iniciar C2B.
4. Endpoint `/webhooks/payments/` (ou consulta de estado agendada) → confirmar → `subscription.activate(method="mpesa", reference=…)`. O método `activate()` já existe e é o mesmo que o painel usa hoje.
