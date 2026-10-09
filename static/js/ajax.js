(function () {
    'use strict';

    // ===== Utils
    const $ = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

    // ===== Elements
    const btnAll = $('#btn-select-all');
    const btnClr = $('#btn-clear-all');
    const btnGenerate = $('#btn-generate');
    const statusEl = $('#run-status');

    const endpoint = $('meta[name="endpoint-run"]')?.content || '';
    const culture = $('meta[name="culture"]')?.content || 'cow';
    const currentType = $('meta[name="current-type"]')?.content || '';
    let selectedPersonalBins = null;

    // ===== Years: select/clear
    btnAll?.addEventListener('click', () => {
        $$('#grid-years input[type="checkbox"]').forEach(c => (c.checked = true));
    });
    btnClr?.addEventListener('click', () => {
        $$('#grid-years input[type="checkbox"]').forEach(c => (c.checked = false));
    });

    // ===== Bins panels toggle
    const modeRadios = $$('input[name="bin_mode"]');
    function syncPanels() {
        const mode = ($('input[name="bin_mode"]:checked') || {}).value;
        const autoEl = $('#bin-panel-automatic');
        const equalEl = $('#bin-panel-equal');
        const manualEl = $('#bin-panel-manual');
        if (autoEl) autoEl.style.display = mode === 'automatic' ? 'block' : 'none';
        if (equalEl) equalEl.style.display = mode === 'equal_width' ? 'block' : 'none';
        if (manualEl) manualEl.style.display = mode === 'manual' ? 'block' : 'none';
        const cileiteEl = $('#bin-panel-cileite');
        if (cileiteEl) cileiteEl.style.display = mode === 'cileite' ? 'block' : 'none';
        if ($('#personal-presets')) $('#personal-presets').style.display = mode === 'personal' ? 'block' : 'none';
        if ($('#fixed-bins')) $('#fixed-bins').disabled = mode === 'cileite';
    }
    modeRadios.forEach(r => r.addEventListener('change', syncPanels));
    if ($('#bin-panel-automatic') && $('#bin-panel-equal') && $('#bin-panel-manual')) syncPanels();

    // ===== Colormap label update (from modal)
    window.addEventListener('cm:chosen', ev => {
        const d = ev.detail || {};
        if (d.key === 'global' && d.label) {
            const el = $('#cm-label-global');
            if (el) el.textContent = d.label;
        }
    });

    // ===== Config
    const TASKS_PER_YEAR = 64; // mapas
    const BASES_STEP_PER_YEAR = 1;  // 1 passo extra por ano (Bases — Municípios)
    const groupsCfg = [
        ['dynamic_brazil', 1, 'Interativo — Brasil'],
        ['dynamic_regions', 5, 'Interativo — Regiões'],
        ['dynamic_states', 26, 'Interativo — Estados'],
        ['static_brazil', 1, 'Estático — Brasil'],
        ['static_regions', 5, 'Estático — Regiões'],
        ['static_states', 26, 'Estático — Estados'],
    ];

    function makeBar(container, label, gradient) {
        const wrap = document.createElement('div');
        wrap.className = 'group';
        wrap.innerHTML = `
      <div class="progress-label">${label}</div>
      <div class="progress-bar"><span></span></div>
      <div class="progress-numbers"></div>
    `;
        container.appendChild(wrap);
        const span = wrap.querySelector('.progress-bar > span');
        const nums = wrap.querySelector('.progress-numbers');
        if (span) {
            span.style.background = gradient || 'linear-gradient(90deg, #4c8bf5, #7db3ff)';
            span.style.transition = 'width .25s ease';
            span.style.display = 'block';
            span.style.height = '100%';
            span.style.width = '0%';
        }
        return {
            cur: 0,
            set(cur, total) {
                const pct = total ? Math.round((cur * 100) / total) : 0;
                if (span) span.style.width = pct + '%';
                if (nums) nums.textContent = `${cur} / ${total} (${pct}%)`;
            },
            reset(total) {
                this.cur = 0;
                if (span) span.style.width = '0%';
                if (nums) nums.textContent = `0 / ${total} (0%)`;
            },
        };
    }

    // ===== Bases — Municípios (APENAS a barra, sem linhas por ano)
    function setupBasesUI(wrap, selectedYears) {
        let box = $('#bases-box');
        if (!box) {
            box = document.createElement('div');
            box.id = 'bases-box';
            box.style.marginTop = '1rem';
            box.innerHTML = `
        <div class="progress-label" style="font-weight:600">Bases — Municípios</div>
        <div class="progress-bar"><span></span></div>
        <div class="progress-numbers" id="bases-numbers"></div>
      `;
            const overallBlock = $('.progress-overall', wrap);
            if (overallBlock) overallBlock.insertAdjacentElement('afterend', box);
            else wrap.insertBefore(box, wrap.firstChild);
        }
        const totalYears = selectedYears.length;
        const span = box.querySelector('.progress-bar > span');
        const nums = $('#bases-numbers', box);
        if (span) {
            span.style.background = 'linear-gradient(90deg, #8a63d2, #b08cff)';
            span.style.transition = 'width .25s ease';
            span.style.display = 'block';
            span.style.height = '100%';
            span.style.width = '0%';
        }
        if (nums) nums.textContent = `0 / ${totalYears} (0%)`;

        let doneYears = 0;
        const finished = new Set();
        function setOverallYears(cur) {
            const pct = totalYears ? Math.round((cur * 100) / totalYears) : 0;
            if (span) span.style.width = pct + '%';
            if (nums) nums.textContent = `${cur} / ${totalYears} (${pct}%)`;
        }

        function onBases(msg) {
            const { year, stage } = msg;
            if ((stage === 'saved' || stage === 'computed') && !finished.has(year)) {
                finished.add(year);
                doneYears = Math.min(doneYears + 1, totalYears);
                setOverallYears(doneYears);
                return true;
            }
            return false;
        }

        return { onBases };
    }

    // ===== Helpers: obter shapes_year de forma segura
    function getShapesYear() {
        const sel = $('#shapes-year');
        if (!sel) return null;
        const val = sel.value;
        // se vier vazio por algum motivo, caímos para null (backend decide fallback)
        return val && /^\d{4}$/.test(val) ? parseInt(val, 10) : null;
    }

    // ===== Payload
    function collectPayload() {
        const years = $$('input[name="years"]:checked').map(i => parseInt(i.value, 10));
        const colormap = $('#cm-label-global')?.textContent?.trim() || 'Blues';
        const mode = ($('input[name="bin_mode"]:checked') || {}).value;

        const bins = mode === 'personal' ? { ...selectedPersonalBins } : { mode };
        if (mode === 'automatic') {
            bins.method = 'quantile';
        } else if (mode === 'equal_width') {
            bins.method = 'equal_width';
            const k = parseInt($('#equal-k')?.value || '5', 10);
            bins.k = Number.isFinite(k) && k > 1 ? k : 5;
        } else if (mode === 'manual') {
            bins.breaks = $('#manual-breaks')?.value?.trim() || '';
        }

        // >>> NOVO: shapes_year incluído no payload
        const shapes_year = getShapesYear();

        return {
            culture,
            type: currentType || null,
            years,
            shapes_year, // <<< AQUI
            colormap,
            bins,
            basemap: $('#basemap')?.value || 'none',
            fixed_bins: $('#fixed-bins')?.checked ?? true,
            action: 'generate_maps',
            stream: true
        };
    }

    // ===== Presets pessoais
    const presetBox = $('#personal-presets');
    if (presetBox) {
        const select = $('#personal-preset-list');
        const message = $('#personal-preset-status');
        const preview = $('#personal-preset-preview');
        const remove = $('#personal-preset-delete');
        const save = $('#personal-preset-save');
        const createNew = $('#personal-preset-new');
        let presets = [];
        let busy = false;
        function buttons() {
            remove.disabled = busy || !select.value;
            save.disabled = select.disabled = busy;
            createNew.disabled = busy;
            $('#personal-preset-name').disabled = $('#personal-preset-breaks').disabled = busy;
        }
        async function api(url, method = 'GET', data) {
            const response = await fetch(url, {
                method, headers: { 'Content-Type': 'application/json',
                    'X-CSRFToken': $('meta[name="csrf-token"]')?.content || '' },
                ...(data ? { body: JSON.stringify(data) } : {})
            });
            if (response.redirected) throw new Error('Faça login novamente para acessar seus presets.');
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.message || 'Não foi possível acessar os presets.');
            return result;
        }
        async function refresh(selected = '') {
            const result = await api(presetBox.dataset.endpoint);
            presets = result.presets;
            select.replaceChildren(new Option('Selecione um preset', ''));
            for (const preset of presets) select.add(new Option(preset.name, preset.id));
            select.value = selected;
            choose();
        }
        async function action(work) {
            busy = true; buttons(); message.textContent = 'Aguarde…';
            try { await work(); }
            catch (error) { message.textContent = error.message; }
            finally { busy = false; buttons(); }
        }
        function choose() {
            const preset = presets.find(p => p.id === select.value);
            selectedPersonalBins = preset ? preset.bins : null;
            const bins = selectedPersonalBins;
            $('#personal-preset-name').value = preset ? preset.name : '';
            $('#personal-preset-breaks').value = bins?.mode === 'manual' ? bins.breaks : '';
            save.textContent = preset ? 'Salvar alterações' : 'Criar preset';
            preview.textContent = !bins ? '' : bins.mode === 'manual'
                ? `Limites: ${bins.breaks}. Última classe: acima do maior limite.`
                : bins.mode === 'equal_width' ? `${bins.k} classes iguais.`
                : bins.mode === 'cileite' ? 'Classes Cileite por ano e território.' : 'Classes por quantis.';
            buttons();
        }
        select.addEventListener('change', () => {
            choose();
            message.textContent = select.value ? 'Preset selecionado para a geração.' : '';
        });
        createNew.addEventListener('click', () => {
            select.value = '';
            choose();
            message.textContent = 'Informe o nome e os limites do novo preset.';
            $('#personal-preset-name').focus();
        });
        save.addEventListener('click', () => action(async () => {
            const name = $('#personal-preset-name').value.trim();
            if (!name) throw new Error('Informe um nome para o preset.');
            const breaks = $('#personal-preset-breaks').value.trim();
            if (!breaks) throw new Error('Informe os limites dos bins.');
            const editing = select.value;
            const url = editing ? `${presetBox.dataset.endpoint}/${encodeURIComponent(editing)}` : presetBox.dataset.endpoint;
            const result = await api(url, editing ? 'PUT' : 'POST', { name, bins: { mode: 'manual', breaks } });
            await refresh(result.id);
            message.textContent = editing ? 'Alterações salvas no preset.' : 'Preset criado na sua conta.';
        }));
        remove.addEventListener('click', () => {
            const preset = presets.find(p => p.id === select.value);
            if (!preset || !window.confirm(`Excluir o preset “${preset.name}”?`)) return;
            action(async () => {
                await api(presetBox.dataset.deleteUrl.replace('PRESET_ID', encodeURIComponent(preset.id)), 'DELETE');
                await refresh();
                message.textContent = 'Preset excluído. A configuração atual continua disponível.';
            });
        });
        action(async () => { await refresh(); message.textContent = presets.length ? '' : 'Você ainda não tem presets para este indicador.'; });
    }

    // ===== Run
    async function run() {
        if (!endpoint) { statusEl.textContent = 'Endpoint não configurado.'; return; }
        if ($('input[name="bin_mode"]:checked')?.value === 'personal' && !selectedPersonalBins) {
            statusEl.textContent = 'Selecione ou crie um preset em Meus presets.';
            return;
        }

        const payload = collectPayload();

        if (!payload.type) { statusEl.textContent = 'Escolha um tipo no menu (Ordenha, Produção, etc.)'; return; }
        if (!payload.years?.length) { statusEl.textContent = 'Selecione pelo menos um ano.'; return; }

        const wrap = $('#progress-wrap');
        const groupsEl = $('#progress-groups');
        if (groupsEl) groupsEl.innerHTML = '';
        if (wrap) wrap.style.display = 'block';

        // TOTAL (mapas + bases) no topo
        const yearsCount = payload.years.length;
        const totalOverall = yearsCount * (TASKS_PER_YEAR + BASES_STEP_PER_YEAR);
        const overallSpan = $('.progress-overall .progress-bar > span');
        const overallNums = $('.progress-overall .progress-numbers');
        if (overallSpan) {
            overallSpan.style.background = 'linear-gradient(90deg, #24b47e, #36d49b)';
            overallSpan.style.transition = 'width .25s ease';
            overallSpan.style.display = 'block';
            overallSpan.style.height = '100%';
            overallSpan.style.width = '0%';
        }
        const setOverall = (cur) => {
            const pct = totalOverall ? Math.round((cur * 100) / totalOverall) : 0;
            if (overallSpan) overallSpan.style.width = pct + '%';
            if (overallNums) overallNums.textContent = `${cur} / ${totalOverall} (${pct}%)`;
        };
        setOverall(0);

        // Bases (somente barra, logo abaixo do total)
        const basesUI = setupBasesUI(wrap, payload.years);

        // Grupos de tarefas
        const bars = {};
        groupsCfg.forEach(([key, perYear, label]) => {
            bars[key] = makeBar(groupsEl, label);
            bars[key].reset(perYear * yearsCount);
        });

        btnGenerate.disabled = true;
        statusEl.textContent = 'Gerando mapas… (stream ativo)';
        let overallCur = 0;

        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': $('meta[name="csrf-token"]')?.content || '' },
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.message || 'Falha ao iniciar execução');
            const jobId = data.job_id;
            if (!jobId) throw new Error('job_id ausente');

            const es = new EventSource(`/setup/events/${encodeURIComponent(jobId)}`);
            let lastActivity = Date.now();
            let activityLabel = 'Preparando a geração';
            let finished = false;
            let checking = false;
            const finish = result => {
                if (finished) return;
                finished = true;
                es.close();
                clearInterval(watchdog);
                statusEl.textContent = result.status === 'completed'
                    ? 'Mapas gerados com sucesso.'
                    : (result.error || 'A geração foi interrompida. Execute novamente.');
                btnGenerate.disabled = false;
            };
            // Confirma o estado por HTTP caso o SSE não esteja entregando eventos.
            const checkStatus = async () => {
                if (checking || finished) return;
                checking = true;
                try {
                    const response = await fetch(`/setup/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store' });
                    if (response.status === 401) {
                        activityLabel = 'Sessão expirada. Recarregue a página para acompanhar';
                        return;
                    }
                    if (!response.ok) return;
                    const job = await response.json();
                    if (job.status !== 'running') { finish(job); return; }
                    const event = job.last_event;
                    if (event?.label) activityLabel = event.label;
                } catch (_) {
                    activityLabel = 'Conexão indisponível; tentando recuperar o acompanhamento';
                } finally {
                    checking = false;
                }
            };
            const watchdog = setInterval(() => {
                const seconds = Math.floor((Date.now() - lastActivity) / 1000);
                if (seconds >= 15) {
                    statusEl.textContent = `${activityLabel} — aguardando há ${seconds}s`;
                    checkStatus();
                }
            }, 5000);
            es.onopen = () => {
                statusEl.textContent = `${activityLabel} — acompanhamento conectado`;
            };

            es.addEventListener('progress', ev => {
                try {
                    const msg = JSON.parse(ev.data || '{}');
                    lastActivity = Date.now();
                    if (msg.label) activityLabel = msg.label;

                    if (msg.phase === 'activity') {
                        statusEl.textContent = msg.label;
                        return;
                    }

                    // Bases contam 1 passo por ano no TOTAL (sem linhas por ano)
                    if (msg.phase === 'bases') {
                        const finishedOne = basesUI.onBases(msg);
                        if (finishedOne) {
                            overallCur = Math.min(overallCur + 1, totalOverall);
                            setOverall(overallCur);
                        }
                        return;
                    }

                    if (msg.phase === 'start') {
                        statusEl.textContent = `Preparando bases para ${yearsCount} ano(s)…`;
                        return;
                    }

                    if (msg.phase === 'tick') {
                        // TOTAL (mapas)
                        overallCur = Math.min(overallCur + 1, totalOverall);
                        setOverall(overallCur);

                        // Grupo
                        const cfg = groupsCfg.find(x => x[0] === msg.group);
                        if (cfg) {
                            const [key, perYear] = cfg;
                            const bar = bars[key];
                            if (bar) {
                                bar.cur = (bar.cur || 0) + 1;
                                bar.set(bar.cur, perYear * yearsCount);
                            }
                        }

                        statusEl.textContent = `(${overallCur}/${totalOverall}) ${msg.label} — ${msg.year}`;
                        return;
                    }

                    if (msg.phase === 'error') {
                        statusEl.textContent = 'Erro: ' + (msg.error || 'desconhecido');
                    }
                } catch (e) {
                    console.error('Erro processando evento SSE:', e);
                }
            });

            es.addEventListener('done', ev => {
                const result = JSON.parse(ev.data || '{}');
                finish(result);
                setTimeout(() => {
                    if ($('#progress-wrap')) {
                        $('#progress-wrap').style.display = 'none';
                        $$('.progress-bar > span').forEach(s => (s.style.width = '0%'));
                        $$('.progress-numbers').forEach(n => (n.textContent = ''));
                    }
                }, 800);
            });

            es.addEventListener('ping', () => { });
            es.onerror = () => {
                if (finished) return;
                statusEl.textContent = 'SSE desconectado; tentando reconectar e consultar o estado da geração…';
                checkStatus();
            };
        } catch (err) {
            console.error(err);
            statusEl.textContent = err.message || 'Não foi possível iniciar o streaming.';
            btnGenerate.disabled = false;
        }
    }

    btnGenerate?.addEventListener('click', run);
})();
