/* RWB — recursos de PWA: guia de instalação no iOS, notificações push, leitor de QR e estado offline. */
(function () {
  "use strict";

  var ua = navigator.userAgent;
  var isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  var standalone = navigator.standalone === true || (window.matchMedia && matchMedia("(display-mode: standalone)").matches);
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  window.RWB = window.RWB || {};
  window.RWB.isIOS = isIOS;
  window.RWB.standalone = standalone;

  // 1. Guia de instalação no iOS -----------------------------------------------------------
  var DISMISS_DAYS = 14;
  var guide = document.querySelector("[data-ios-install]");
  if (guide && isIOS && !standalone) {
    var notSafari = /CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
    var note = guide.querySelector("[data-ios-not-safari]");
    if (note && notSafari) note.hidden = false;
    var dismissedAt = parseInt(store.get("rwb-ios-guide") || "0", 10);
    var recentlyDismissed = dismissedAt && Date.now() - dismissedAt < DISMISS_DAYS * 864e5;
    if (!recentlyDismissed) setTimeout(function () { guide.hidden = false; }, 4000);
    document.querySelectorAll("[data-ios-install-open]").forEach(function (b) { b.hidden = false; });
    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-ios-install-open]")) guide.hidden = false;
      if (e.target.closest("[data-ios-install-close]")) { guide.hidden = true; store.set("rwb-ios-guide", String(Date.now())); }
    });
  }

  // 2. Notificações push (Web Push) --------------------------------------------------------
  var card = document.querySelector("[data-push]");
  var csrf = function () {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  };
  var api = function (method, body) {
    return fetch("/api/v1/me/push/", {
      method: method, credentials: "same-origin", keepalive: true,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(body),
    });
  };
  var supportsPush = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  var keyBytes = function (b64) {
    var pad = "=".repeat((4 - (b64.length % 4)) % 4);
    var raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, function (c) { return c.charCodeAt(0); });
  };
  var currentSubscription = function () {
    return navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); });
  };
  var userId = (document.querySelector('meta[name="rwb-auth"]') || {}).content;

  // O mesmo telemóvel pode passar de um membro para outro: volta a associar a subscrição ao membro com sessão.
  if (supportsPush && userId && Notification.permission === "granted" && store.get("rwb-push-user") !== userId) {
    currentSubscription().then(function (sub) {
      if (!sub) return;
      return api("POST", sub.toJSON()).then(function (r) { if (r.ok) store.set("rwb-push-user", userId); });
    }).catch(function () {});
  }
  // Ao terminar sessão este dispositivo deixa de receber as notificações desse membro
  document.addEventListener("submit", function (e) {
    if (!e.target.hasAttribute || !e.target.hasAttribute("data-logout") || !supportsPush) return;
    currentSubscription().then(function (sub) { if (sub) api("DELETE", { endpoint: sub.endpoint }); }).catch(function () {});
    try { localStorage.removeItem("rwb-push-user"); } catch (err) {}
  });

  if (card) {
    var status = card.querySelector("[data-push-status]");
    var toggle = card.querySelector("[data-push-toggle]");
    var show = function (text, button) {
      status.textContent = text;
      toggle.hidden = !button;
      if (button) toggle.textContent = button;
    };
    var render = function () {
      if (isIOS && !standalone) return show("Para receber notificações no iPhone, instala primeiro a app no ecrã principal.", null);
      if (!supportsPush) return show("Este navegador não suporta notificações.", null);
      if (Notification.permission === "denied") return show("Bloqueaste as notificações. Ativa-as nas definições do telemóvel ou do navegador.", null);
      currentSubscription().then(function (sub) {
        if (sub && Notification.permission === "granted") show("Ativas neste dispositivo: eventos novos, lembretes e estado das encomendas.", "Desativar");
        else show("Recebe avisos de eventos novos, lembretes e quando a tua encomenda estiver pronta.", "Ativar notificações");
      }).catch(function () { show("Não foi possível verificar as notificações.", null); });
    };
    toggle.addEventListener("click", function () {
      toggle.disabled = true;
      currentSubscription().then(function (sub) {
        if (sub) {  // desativar
          return api("DELETE", { endpoint: sub.endpoint }).then(function () { return sub.unsubscribe(); });
        }
        return Notification.requestPermission().then(function (perm) {  // tem de vir de um toque (regra do iOS)
          if (perm !== "granted") return null;
          return navigator.serviceWorker.ready.then(function (reg) {
            return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(card.getAttribute("data-vapid-key")) });
          }).then(function (created) {
            return api("POST", created.toJSON()).then(function (r) { if (r.ok && userId) store.set("rwb-push-user", userId); });
          });
        });
      }).catch(function () { status.textContent = "Não foi possível alterar as notificações. Tenta novamente."; })
        .then(function () { toggle.disabled = false; render(); });
    });
    render();
  }
})();
