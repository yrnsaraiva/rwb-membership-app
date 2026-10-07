/* RWB — ponte com o casco nativo (Capacitor). Só faz algo dentro da app Android/iOS; no browser não tem efeito. */
(function () {
  "use strict";
  var cap = window.Capacitor;
  if (!cap || !cap.isNativePlatform || !cap.isNativePlatform()) return;

  var plugins = cap.Plugins || {};
  var root = document.documentElement;
  root.classList.add("is-native");

  var csrf = function () {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  };
  var api = function (method, path, body) {
    return fetch(path, {
      method: method, credentials: "same-origin", keepalive: true,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: body ? JSON.stringify(body) : undefined,
    });
  };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
    del: function (k) { try { localStorage.removeItem(k); } catch (e) {} },
  };
  var authed = !!document.querySelector('meta[name="rwb-auth"]');

  // Leitor de QR (staff) -------------------------------------------------------------------
  var CARD_PATH = /^\/conta\/verificar\/[0-9a-f-]{36}\/$/i;
  var toast = function (msg) { window.alert(msg); };
  var scanner = plugins.CapacitorBarcodeScanner;
  document.querySelectorAll("[data-native-scan]").forEach(function (el) { if (scanner) el.hidden = false; });
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-native-scan]");
    if (!btn || !scanner) return;
    e.preventDefault();
    scanner.scanBarcode({ hint: 0 /* QR_CODE */, scanInstructions: "Aponta ao QR do cartão de membro", cameraDirection: 1 })
      .then(function (res) {
        var target;
        try { target = new URL(res.ScanResult, location.origin); } catch (err) { return toast("QR inválido."); }
        // Só abre cartões RWB: o QR pode vir de qualquer lado, por isso valida endereço e caminho.
        var sameSite = target.host === location.host || target.host === new URL(btn.getAttribute("data-site") || location.origin).host;
        if (!sameSite || !CARD_PATH.test(target.pathname)) return toast("Este QR não é um cartão de membro RWB.");
        location.href = target.pathname;
      })
      .catch(function () { /* cancelado pelo utilizador */ });
  });

  // Notificações push -------------------------------------------------------------------------
  var push = plugins.PushNotifications;
  if (push && authed) {
    push.addListener("registration", function (t) {
      if (store.get("rwb-push-token") === t.value) return;
      api("POST", "/api/v1/me/devices/", { token: t.value, platform: cap.getPlatform(), app_version: "1.0" })
        .then(function (r) { if (r.ok) store.set("rwb-push-token", t.value); });
    });
    push.addListener("pushNotificationActionPerformed", function (n) {
      var url = n && n.notification && n.notification.data && n.notification.data.url;
      if (url && url.charAt(0) === "/" && url.charAt(1) !== "/") location.href = url;
    });
    push.checkPermissions().then(function (p) {
      return p.receive === "granted" ? p : push.requestPermissions();
    }).then(function (p) {
      if (p.receive === "granted") push.register();
    }).catch(function () {});
  }

  // Ao terminar sessão, deixa de receber push neste telemóvel
  document.addEventListener("submit", function (e) {
    if (!e.target.hasAttribute("data-logout")) return;
    var token = store.get("rwb-push-token");
    if (token) { api("DELETE", "/api/v1/me/devices/" + encodeURIComponent(token) + "/"); store.del("rwb-push-token"); }
  });

  // Ecrã de arranque nativo desaparece quando a página carregou
  if (plugins.SplashScreen) plugins.SplashScreen.hide();
})();
