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
})();
