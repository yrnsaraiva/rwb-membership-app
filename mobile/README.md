# RunWithBroto — app Android (Capacitor)

Casco nativo à volta do site Django. A app abre o site (`server.url`) dentro de uma WebView e acrescenta o que o browser não dá:
**notificações push**, **leitor de QR para o staff** (botão «Ler QR» no painel), ícone/ecrã de arranque e publicação na Play Store.
O código da app continua a ser o do Django — uma alteração ao site chega à app sem nova versão nas lojas.

```
mobile/
  capacitor.config.ts   URL do site, id da app, plugins
  www/index.html        página de reserva (só se vê sem ligação)
  android/              projecto Android Studio (gerado pelo Capacitor, com ícones e permissões da marca)
../static/js/native.js  ponte JS: push, scanner, logout — só actua dentro da app
```

## Requisitos
Node 22+, JDK 21, Android Studio (SDK 36). Verificar com `npm run doctor`.

## Correr no emulador (contra o Django local)
```bash
cd mobile && npm install
python ../manage.py runserver 0.0.0.0:8000      # noutro terminal
RWB_APP_URL=http://10.0.2.2:8000 npx cap sync android   # 10.0.2.2 = o teu PC visto do emulador
npx cap open android                             # abre o Android Studio → Run
```
Em dev o Django tem de aceitar o host: `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,10.0.2.2`.

## Apontar para produção
```bash
RWB_APP_URL=https://app.runwithbroto.co.mz npx cap sync android
```
(é o valor por omissão). Depois: Android Studio → *Build → Generate Signed Bundle (AAB)* para a Play Store.

## Notificações push (falta ligar)
1. Criar um projecto no [Firebase](https://console.firebase.google.com) e registar a app Android com o id `co.mz.runwithbroto.app`.
2. Descarregar `google-services.json` para `mobile/android/app/` (o plugin Gradle já o aplica sozinho quando o ficheiro existe).
3. No servidor: implementar `_deliver()` em `apps/core/push.py` (FCM HTTP v1) e definir `PUSH_ENABLED=1`.

Sem isto a app funciona normalmente; só não recebe push. O telemóvel já se regista em `POST /api/v1/me/devices/` quando o membro aceita as notificações.

## Notas
- **Assinatura:** guardar o *keystore* de release fora do repositório (e uma cópia segura — sem ele não há actualizações).
- **Versão:** `versionCode`/`versionName` em `android/app/build.gradle`; subir `versionCode` a cada publicação.
- **iOS:** não está criado (`npx cap add ios` precisa de macOS + Xcode). A decisão sobre o premium e o In-App Purchase da Apple tem de vir antes.
- **Segurança:** `allowNavigation` limita a WebView ao domínio da app; `allowBackup=false`; `cleartext` só é activado se o URL for `http://` (desenvolvimento).
- O QR lido só é aceite se for um link `/conta/verificar/<uuid>/` do próprio site.
