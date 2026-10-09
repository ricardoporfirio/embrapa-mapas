/* global Swal */
(function (global) {
  "use strict";

  function ensureSwal() {
    if (typeof Swal === "undefined") {
      console.warn("[alerts.js] SweetAlert2 não encontrado. Inclua-o antes deste arquivo.");
      return false;
    }
    return true;
  }

  const iconMap = {
    success: "success",
    info: "info",
    warning: "warning",
    danger: "error",
    error: "error",
  };

  // Modais centralizados (padrão novo)
  const defaultModal = {
    position: "center",
    showConfirmButton: true,
    confirmButtonText: "OK",
    allowOutsideClick: false,
    allowEscapeKey: true,
    timer: undefined,          // sem autohide
    buttonsStyling: true,
  };

  function modal(icon, title, text, opts) {
    if (!ensureSwal()) return;
    Swal.fire(Object.assign({}, defaultModal, { icon, title, text }, opts || {}));
  }

  // Toasts continuam disponíveis, mas também centralizados e sem timer
  const defaultToast = {
    toast: true,
    position: "center",
    showConfirmButton: true,   // exige ação do usuário
    timer: undefined,          // sem autohide
    timerProgressBar: false,
  };

  function toast(icon, title, opts) {
    if (!ensureSwal()) return;
    Swal.fire(Object.assign({}, defaultToast, { icon, title }, opts || {}));
  }

  async function confirm(opts) {
    if (!ensureSwal()) return { isConfirmed: false };
    const defaults = {
      icon: "question",
      title: "Tem certeza?",
      text: "",
      showCancelButton: true,
      confirmButtonText: "Sim",
      cancelButtonText: "Cancelar",
      position: "center",
      allowOutsideClick: false,
    };
    return Swal.fire(Object.assign(defaults, opts || {}));
  }

  // Exibe uma lista de flashes [{message, category}] como modais, em sequência
  async function flash(flashes) {
    if (!ensureSwal() || !flashes || !flashes.length) return;
    for (const f of flashes) {
      const icon = iconMap[(f.category || "info").toLowerCase()] || "info";
      const title = String(f.message || "");
      await Swal.fire(Object.assign({}, defaultModal, { icon, title }));
    }
  }

  const Alerts = {
    // use estes nas views, se quiser
    toast: {
      success: (title, opts) => toast("success", title, opts),
      info:    (title, opts) => toast("info", title, opts),
      warning: (title, opts) => toast("warning", title, opts),
      error:   (title, opts) => toast("error", title, opts),
      show:    (category, title, opts) => toast(iconMap[(category||"info")] || "info", title, opts),
    },
    modal: {
      success: (title, text, opts) => modal("success", title, text, opts),
      info:    (title, text, opts) => modal("info", title, text, opts),
      warning: (title, text, opts) => modal("warning", title, text, opts),
      error:   (title, text, opts) => modal("error", title, text, opts),
    },
    confirm,
    flash,   // usado automaticamente para window.__FLASHES__
  };

  global.Alerts = Alerts;

  // Auto: mostra flashes do backend (definidos na base como window.__FLASHES__)
  if (typeof window !== "undefined") {
    document.addEventListener("DOMContentLoaded", function () {
      if (Array.isArray(window.__FLASHES__) && window.__FLASHES__.length) {
        flash(window.__FLASHES__);
      }
    });
  }
})(window);
