/* RWB — interacções leves (sem frameworks, para carregar rápido em 3G). */
(function () {
  "use strict";

  // Tema claro/escuro -----------------------------------------------------------
  var root = document.documentElement;
  var setTheme = function (t) {
    root.setAttribute("data-theme", t);
    try { localStorage.setItem("rwb-theme", t); } catch (e) {}
    var meta = document.querySelector("meta[data-theme-color]");
    if (meta) meta.setAttribute("content", t === "dark" ? "#0B0B0B" : "#FFFFFF");
  };
  var markThemeChoice = function () {
    var saved = null;
    try { saved = localStorage.getItem("rwb-theme"); } catch (e) {}
    document.querySelectorAll("[data-theme-set]").forEach(function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-theme-set") === (saved || "auto"));
    });
  };
  document.addEventListener("DOMContentLoaded", markThemeChoice);
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-theme-toggle], [data-theme-set]")) setTimeout(markThemeChoice, 0);
    if (e.target.closest("[data-theme-toggle]")) {
      setTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
    }
    var choice = e.target.closest("[data-theme-set]");
    if (choice) {
      var v = choice.getAttribute("data-theme-set");
      if (v === "auto") {
        setTheme(window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
        try { localStorage.removeItem("rwb-theme"); } catch (err) {}
      } else { setTheme(v); }
    }
  });
  // Segue o sistema enquanto o utilizador não escolher manualmente
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function (ev) {
      var saved = null;
      try { saved = localStorage.getItem("rwb-theme"); } catch (err) {}
      if (!saved) { root.setAttribute("data-theme", ev.matches ? "dark" : "light"); }
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
  }

  // Service worker (PWA) ------------------------------------------------------
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
    });
  }

  // Botão "Instalar app" ---------------------------------------------------------
  var deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredPrompt = e;
    document.querySelectorAll("[data-install]").forEach(function (btn) { btn.classList.remove("hidden"); });
  });
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-install]");
    if (btn && deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () { deferredPrompt = null; btn.classList.add("hidden"); });
    }
  });

  // Mensagens: fechar e desaparecer automaticamente ----------------------------------
  document.querySelectorAll("[data-toast]").forEach(function (toast) {
    var close = function () { toast.style.transition = "opacity .2s"; toast.style.opacity = "0"; setTimeout(function () { toast.remove(); }, 200); };
    var btn = toast.querySelector("[data-toast-close]");
    if (btn) btn.addEventListener("click", close);
    if (!toast.classList.contains("toast-error")) setTimeout(close, 6000);
  });

  // Confirmação antes de acções destrutivas ------------------------------------------
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var msg = form.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) { e.preventDefault(); return; }
    // Evita duplo envio em redes lentas
    var submit = form.querySelector("button[type=submit], button:not([type])");
    if (submit && !e.defaultPrevented) {
      setTimeout(function () { submit.disabled = true; submit.classList.add("is-disabled"); }, 0);
    }
    // Ao terminar sessão, limpa páginas guardadas offline (cartão, dashboard)
    if (form.hasAttribute("data-logout") && "caches" in window) {
      caches.keys().then(function (keys) { keys.forEach(function (k) { if (k.indexOf("-pages") > -1) caches.delete(k); }); });
    }
  });

  // Tabs do gráfico do dashboard --------------------------------------------------------
  document.querySelectorAll("[data-chart-tabs]").forEach(function (root) {
    root.querySelectorAll("[data-chart-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        var target = tab.getAttribute("data-chart-tab");
        root.querySelectorAll("[data-chart-tab]").forEach(function (t) { t.classList.toggle("is-active", t === tab); });
        root.querySelectorAll("[data-chart]").forEach(function (c) { c.hidden = c.getAttribute("data-chart") !== target; });
      });
    });
  });

  // Registo de corrida: ritmo e pontos em tempo real ---------------------------------------
  var runForm = document.querySelector("[data-run-form]");
  if (runForm) {
    var $ = function (name) { return runForm.querySelector("[name=" + name + "]"); };
    var paceEl = runForm.querySelector("[data-pace]");
    var pointsEl = runForm.querySelector("[data-points]");
    var perKm = parseInt(pointsEl.getAttribute("data-per-km") || "10", 10);
    var update = function () {
      var km = parseFloat(($("distance_km").value || "").replace(",", "."));
      var secs = (parseInt($("hours").value || 0, 10) * 3600) + (parseInt($("minutes").value || 0, 10) * 60) + parseInt($("seconds").value || 0, 10);
      if (km > 0) { pointsEl.textContent = "+" + Math.floor(km * perKm); } else { pointsEl.textContent = "—"; }
      if (km > 0 && secs > 0) {
        var pace = Math.round(secs / km);
        paceEl.textContent = Math.floor(pace / 60) + ":" + String(pace % 60).padStart(2, "0");
      } else { paceEl.textContent = "—"; }
    };
    ["distance_km", "hours", "minutes", "seconds"].forEach(function (n) { var el = $(n); if (el) el.addEventListener("input", update); });
    update();
  }

  // Loja: seletor de quantidade -----------------------------------------------------------------
  document.addEventListener("click", function (e) {
    var step = e.target.closest("[data-qty-step]");
    if (!step) return;
    var input = step.closest("[data-qty]").querySelector("input");
    var min = parseInt(input.min || "0", 10), max = parseInt(input.max || "99", 10);
    var v = Math.min(max, Math.max(min, (parseInt(input.value || "0", 10) || 0) + parseInt(step.getAttribute("data-qty-step"), 10)));
    input.value = v;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  // Carrinho: actualiza automaticamente ao mudar a quantidade
  document.querySelectorAll("[data-cart-form] [data-autosubmit]").forEach(function (input) {
    var t;
    input.addEventListener("change", function () { clearTimeout(t); t = setTimeout(function () { input.form.requestSubmit ? input.form.requestSubmit() : input.form.submit(); }, 400); });
  });
  // Produto: miniaturas e aviso de stock
  document.querySelectorAll("[data-thumb]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var main = document.querySelector("[data-main-image]");
      if (main) main.src = btn.getAttribute("data-thumb");
    });
  });
  var addForm = document.querySelector("[data-add-to-cart]");
  if (addForm) {
    var note = addForm.querySelector("[data-stock-note]");
    addForm.addEventListener("change", function (e) {
      if (e.target.name !== "variant" || !note) return;
      var stock = parseInt(e.target.getAttribute("data-stock"), 10);
      note.textContent = stock <= 5 ? "Só restam " + stock + "!" : "";
      var qty = addForm.querySelector("[name=quantity]");
      if (qty) qty.max = Math.min(stock, 10);
    });
  }
  // Checkout: mostra campos conforme a entrega e actualiza o total
  var checkout = document.querySelector("[data-checkout]");
  if (checkout) {
    var fee = parseFloat(checkout.getAttribute("data-delivery-fee") || "0");
    var items = parseFloat(checkout.getAttribute("data-items-total") || "0");
    var fmt = function (n) { return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " MZN"; };
    var sync = function () {
      var checked = checkout.querySelector("[name=fulfilment]:checked");
      var mode = checked ? checked.value : "event";
      checkout.querySelectorAll("[data-show-for]").forEach(function (el) { el.hidden = el.getAttribute("data-show-for") !== mode; });
      var deliveryLine = checkout.querySelector("[data-delivery-line]");
      var totalEl = checkout.querySelector("[data-total]");
      if (deliveryLine) deliveryLine.textContent = mode === "delivery" ? fmt(fee) : "Grátis";
      if (totalEl) totalEl.textContent = fmt(items + (mode === "delivery" ? fee : 0));
    };
    checkout.addEventListener("change", sync);
    sync();
  }
})();
