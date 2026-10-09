// ===== Colormaps list (sequenciais clássicos do Matplotlib) =====
const CM_LIST = [
  "Greys","Purples","Blues","Greens","Oranges","Reds",
  "YlOrBr","YlOrRd","OrRd","PuRd","RdPu","BuPu",
  "GnBu","PuBu","YlGnBu","PuBuGn","BuGn","YlGn"
];

// Gradiente aproximado para pré-visualização
const CM_GRADIENT = {
  Greys:    "linear-gradient(to right, #f8f9fa, #6b7280, #111827)",
  Purples:  "linear-gradient(to right, #f3e8ff, #8b5cf6, #3b0764)",
  Blues:    "linear-gradient(to right, #e0f2fe, #3b82f6, #0b3a7e)",
  Greens:   "linear-gradient(to right, #dcfce7, #22c55e, #14532d)",
  Oranges:  "linear-gradient(to right, #ffedd5, #f97316, #7c2d12)",
  Reds:     "linear-gradient(to right, #fee2e2, #ef4444, #7f1d1d)",
  YlOrBr:   "linear-gradient(to right, #fef9c3, #f59e0b, #7c2d12)",
  YlOrRd:   "linear-gradient(to right, #fef9c3, #f59e0b, #b91c1c)",
  OrRd:     "linear-gradient(to right, #ffedd5, #fb923c, #b91c1c)",
  PuRd:     "linear-gradient(to right, #f5e1f7, #c084fc, #7f1d1d)",
  RdPu:     "linear-gradient(to right, #fee2e2, #f472b6, #6b21a8)",
  BuPu:     "linear-gradient(to right, #dbeafe, #6366f1, #6b21a8)",
  GnBu:     "linear-gradient(to right, #dcfce7, #22c55e, #0ea5e9)",
  PuBu:     "linear-gradient(to right, #f3e8ff, #8b5cf6, #0ea5e9)",
  YlGnBu:   "linear-gradient(to right, #fef9c3, #22c55e, #2563eb)",
  PuBuGn:   "linear-gradient(to right, #f3e8ff, #6366f1, #10b981)",
  BuGn:     "linear-gradient(to right, #dbeafe, #3b82f6, #10b981)",
  YlGn:     "linear-gradient(to right, #fef9c3, #84cc16, #14532d)"
};

// ===== Estado global (em inglês) =====
window.CM_SELECTED = window.CM_SELECTED || {
  milking: "Blues",
  production: "Greens",
  animal_density: "Oranges",
  production_density: "PuBuGn",
  productivity: "Purples"
};

(function () {
  const modal = document.getElementById("cm-modal");
  if (!modal) return;

  const grid  = document.getElementById("cm-grid");
  const closeEls = modal.querySelectorAll("[data-close]");
  let currentAction = null;

  // Abrir modal a partir dos botões data-open-cm
  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-open-cm]");
    if (!btn) return;
    currentAction = btn.dataset.openCm; // "milking", "production", etc.
    renderGrid();
    openModal();
  });

  function openModal(){
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    const title = document.getElementById("cm-modal-title");
    if (title) { title.setAttribute("tabindex","-1"); title.focus(); }
  }
  function closeModal(){
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
  }

  closeEls.forEach(el => el.addEventListener("click", closeModal));
  document.addEventListener("keydown", (e)=>{
    if (e.key === "Escape" && modal.classList.contains("is-open")) closeModal();
  });

  function renderGrid(){
    grid.innerHTML = "";
    CM_LIST.forEach(name=>{
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cm-item";
      if (window.CM_SELECTED[currentAction] === name) btn.classList.add("is-selected");

      const bar = document.createElement("span");
      bar.className = "cm-item__bar";
      bar.style.backgroundImage = CM_GRADIENT[name];

      const label = document.createElement("span");
      label.className = "cm-item__label";
      label.textContent = name;

      btn.append(bar, label);
      btn.addEventListener("click", ()=>{
        // salva no estado global e atualiza o label na tela
        window.CM_SELECTED[currentAction] = name;
        const tag = document.getElementById(`cm-label-${currentAction}`);
        if (tag) tag.textContent = name;
        closeModal();
      });

      grid.appendChild(btn);
    });
  }
})();
