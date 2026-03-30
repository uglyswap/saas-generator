/**
 * SaaS Generator - Centralized Application JavaScript
 * All page-specific logic is initialized via App.init* methods.
 */
const App = (() => {
    'use strict';

    // CSRF token from meta tag
    const csrfToken = () => {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    };

    // ---------------------------------------------------------------
    // Utilities
    // ---------------------------------------------------------------

    function showToast(message, type = 'success') {
        const container = document.getElementById('toastContainer');
        if (container) {
            const toast = document.createElement('div');
            const icon = type === 'success' ? 'check-circle' : type === 'error' ? 'alert-circle' : 'info';
            const colors = type === 'success'
                ? 'bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200'
                : type === 'error'
                ? 'bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800 text-red-800 dark:text-red-200'
                : 'bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-200';
            toast.className = `flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg ${colors} animate-slide-up`;
            toast.innerHTML = `<i data-lucide="${icon}" class="w-5 h-5 shrink-0"></i><span class="text-sm font-medium">${escapeHtml(message)}</span>`;
            container.appendChild(toast);
            if (typeof lucide !== 'undefined') lucide.createIcons({nodes: [toast]});
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                toast.style.transition = 'all 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 4000);
            return;
        }
        // Fallback to legacy toast
        const toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = message;
        toast.className = `toast ${type}`;
        toast.style.display = 'block';
        setTimeout(() => { toast.style.display = 'none'; }, 4000);
    }

    function formatTimestamp(ts) {
        const date = new Date(ts);
        const diff = Date.now() - date.getTime();
        if (diff < 60000) return "A l'instant";
        if (diff < 3600000) { const m = Math.floor(diff / 60000); return `Il y a ${m} min`; }
        if (diff < 86400000) { const h = Math.floor(diff / 3600000); return `Il y a ${h}h`; }
        if (diff < 604800000) { const d = Math.floor(diff / 86400000); return `Il y a ${d}j`; }
        return date.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    async function apiFetch(url, options = {}) {
        const defaults = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken(),
            },
        };
        const merged = { ...defaults, ...options, headers: { ...defaults.headers, ...(options.headers || {}) } };
        const resp = await fetch(url, merged);
        const data = await resp.json().catch(() => ({}));
        return { ok: resp.ok, status: resp.status, data };
    }

    function extractVariables(content) {
        const pattern = /\{([^{}]+)\}/g;
        const matches = [];
        let m;
        while ((m = pattern.exec(content)) !== null) {
            const v = m[1].trim();
            if (v) matches.push(v);
        }
        return [...new Set(matches)];
    }

    function displayVariables(variables) {
        const preview = document.getElementById('variablesPreview');
        const list = document.getElementById('variablesList');
        if (!preview || !list) return;
        if (variables.length > 0) {
            preview.style.display = 'block';
            preview.classList.remove('hidden');
            list.innerHTML = variables.map(v =>
                `<span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">${escapeHtml(v)}</span>`
            ).join('');
        } else {
            preview.style.display = 'none';
            preview.classList.add('hidden');
        }
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ---------------------------------------------------------------
    // Content Rendering - HTML detection + Markdown (Phase 1)
    // ---------------------------------------------------------------

    let markdownReady = false;
    let renderThrottleTimer = null;

    function initMarkdown() {
        if (typeof marked === 'undefined') return;
        marked.setOptions({
            breaks: true,
            gfm: true,
            highlight: function(code, lang) {
                if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                    try { return hljs.highlight(code, { language: lang }).value; } catch {}
                }
                if (typeof hljs !== 'undefined') {
                    try { return hljs.highlightAuto(code).value; } catch {}
                }
                return code;
            },
        });
        if (typeof mermaid !== 'undefined') {
            mermaid.initialize({ startOnLoad: false, theme: 'default' });
        }
        markdownReady = true;
    }

    /**
     * Detect if content is raw HTML rather than Markdown.
     * Prevents marked.parse() from mangling HTML output (escaping, tag
     * reinterpretation, blank-line splitting of HTML blocks, etc.).
     */
    function isHtmlContent(text) {
        if (!text) return false;
        const trimmed = text.trimStart();
        // Full HTML document markers
        if (/^<!doctype\s/i.test(trimmed)) return true;
        if (/^<html[\s>]/i.test(trimmed)) return true;
        // Starts with a block-level HTML tag and has significant tag density
        if (/^<(div|section|article|main|header|footer|nav|aside|table|form|details|figure|style|head|body|ul|ol)[\s>]/i.test(trimmed)) {
            const sample = trimmed.substring(0, 1000);
            const tags = sample.match(/<\/?[a-z][a-z0-9]*[\s>\/]/gi);
            return tags && tags.length >= 4;
        }
        return false;
    }

    /**
     * Render content to element — auto-detects HTML vs Markdown.
     * For HTML content: displays raw source code with syntax highlighting.
     * For Markdown: parses with marked + mermaid support.
     */
    function renderContent(raw, element) {
        if (!element) return;
        if (isHtmlContent(raw)) {
            // Show raw HTML as source code — NOT rendered
            const pre = document.createElement('pre');
            pre.style.cssText = 'margin:0;overflow-x:auto;';
            const code = document.createElement('code');
            code.className = 'language-html hljs';
            code.textContent = raw || '';
            pre.appendChild(code);
            element.innerHTML = '';
            element.appendChild(pre);
            element.classList.remove('markdown');
            element.classList.add('rendered-markdown', 'html-content');
            if (typeof hljs !== 'undefined') {
                try { hljs.highlightElement(code); } catch {}
            }
        } else if (markdownReady) {
            element.innerHTML = marked.parse(raw || '');
            element.classList.remove('markdown', 'html-content');
            element.classList.add('rendered-markdown');
            // Render mermaid diagrams
            if (typeof mermaid !== 'undefined') {
                const mermaidBlocks = element.querySelectorAll('code.language-mermaid');
                mermaidBlocks.forEach((block, i) => {
                    const pre = block.parentElement;
                    const div = document.createElement('div');
                    div.className = 'mermaid';
                    div.textContent = block.textContent;
                    pre.replaceWith(div);
                });
                try { mermaid.run({ nodes: element.querySelectorAll('.mermaid') }); } catch {}
            }
        } else {
            element.textContent = raw || '';
        }
    }

    // Legacy alias — all call sites now go through renderContent
    function renderMarkdown(raw, element) {
        renderContent(raw, element);
    }

    function renderMarkdownThrottled(raw, element) {
        if (!element) return;
        if (!markdownReady && !isHtmlContent(raw)) return;
        if (renderThrottleTimer) return;
        renderThrottleTimer = setTimeout(() => {
            renderThrottleTimer = null;
            renderContent(raw, element);
            element.scrollTop = element.scrollHeight;
        }, 100);
    }

    function flushMarkdownRender(raw, element) {
        if (renderThrottleTimer) {
            clearTimeout(renderThrottleTimer);
            renderThrottleTimer = null;
        }
        renderContent(raw, element);
    }

    // ---------------------------------------------------------------
    // Copy Functions (Phase 1)
    // ---------------------------------------------------------------

    async function copyRichText(element) {
        if (!element) return;
        try {
            const html = element.innerHTML;
            const text = element.innerText;
            const htmlBlob = new Blob([html], { type: 'text/html' });
            const textBlob = new Blob([text], { type: 'text/plain' });
            await navigator.clipboard.write([
                new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })
            ]);
            showToast('Copie (texte riche) reussie !', 'success');
        } catch {
            // Fallback
            try {
                await navigator.clipboard.writeText(element.innerText);
                showToast('Copie en texte brut (fallback)', 'success');
            } catch {
                showToast('Erreur de copie', 'error');
            }
        }
    }

    async function copyHtmlSource(element) {
        if (!element) return;
        try {
            await navigator.clipboard.writeText(element.innerHTML);
            showToast('Code HTML copie !', 'success');
        } catch {
            showToast('Erreur de copie', 'error');
        }
    }

    // ---------------------------------------------------------------
    // Export Dropdown (Phase 2)
    // ---------------------------------------------------------------

    function setupExportDropdown(btnId, entryIdGetter) {
        const btn = document.getElementById(btnId);
        if (!btn) return;

        // Replace button with dropdown
        const wrapper = document.createElement('div');
        wrapper.className = 'relative inline-block';
        wrapper.innerHTML = `
            <button class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-600 hover:bg-slate-700 dark:bg-slate-700 dark:hover:bg-slate-600 text-white rounded-lg text-xs font-medium transition-colors" type="button">
                <i data-lucide="download" class="w-3.5 h-3.5"></i> Exporter
            </button>
            <div class="export-dropdown-menu absolute top-full right-0 mt-1 z-50 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg min-w-[160px] overflow-hidden" style="display:none;">
                <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" data-format="md">Markdown (.md)</button>
                <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" data-format="html">HTML (.html)</button>
                <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" data-format="docx">Word (.docx)</button>
                <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" data-format="pdf">PDF (.pdf)</button>
            </div>
        `;
        btn.replaceWith(wrapper);
        if (typeof lucide !== 'undefined') lucide.createIcons({nodes: [wrapper]});

        const toggleBtn = wrapper.querySelector('button');
        const menu = wrapper.querySelector('.export-dropdown-menu');

        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
        });

        menu.querySelectorAll('button[data-format]').forEach(opt => {
            opt.addEventListener('click', () => {
                const entryId = entryIdGetter();
                if (!entryId) { showToast('Aucun resultat a exporter', 'error'); return; }
                const format = opt.dataset.format;
                window.location.href = `/api/v1/export/${entryId}?format=${format}`;
                menu.style.display = 'none';
            });
        });

        // Close on outside click
        document.addEventListener('click', () => { menu.style.display = 'none'; });
    }

    // ---------------------------------------------------------------
    // Edit Mode (Phase 3)
    // ---------------------------------------------------------------

    let editMode = false;
    let lastRawMarkdown = '';

    function toggleEditMode() {
        const content = document.getElementById('resultContent');
        const editArea = document.getElementById('editTextarea');
        const editBtn = document.getElementById('editBtn');
        const saveEditBtn = document.getElementById('saveEditBtn');
        const cancelEditBtn = document.getElementById('cancelEditBtn');
        if (!content || !editArea) return;

        editMode = !editMode;
        if (editMode) {
            editArea.value = lastRawMarkdown;
            content.style.display = 'none';
            editArea.style.display = 'block';
            if (editBtn) editBtn.style.display = 'none';
            if (saveEditBtn) saveEditBtn.style.display = 'inline-flex';
            if (cancelEditBtn) cancelEditBtn.style.display = 'inline-flex';
            editArea.focus();
        } else {
            content.style.display = 'block';
            editArea.style.display = 'none';
            if (editBtn) editBtn.style.display = 'inline-flex';
            if (saveEditBtn) saveEditBtn.style.display = 'none';
            if (cancelEditBtn) cancelEditBtn.style.display = 'none';
        }
    }

    async function saveEdit() {
        const editArea = document.getElementById('editTextarea');
        const content = document.getElementById('resultContent');
        if (!editArea || !content || !lastEntryId) return;

        const newResult = editArea.value;
        try {
            const { ok, data } = await apiFetch(`/api/v1/history/${lastEntryId}`, {
                method: 'PATCH',
                body: JSON.stringify({ result: newResult }),
            });
            if (ok) {
                lastRawMarkdown = newResult;
                flushMarkdownRender(newResult, content);
                editMode = true; // force toggle to switch back
                toggleEditMode();
                showToast('Modifications sauvegardees', 'success');
            } else {
                showToast(data.error || 'Erreur lors de la sauvegarde', 'error');
            }
        } catch {
            showToast('Erreur de connexion', 'error');
        }
    }

    function cancelEdit() {
        editMode = true; // force toggle to switch back
        toggleEditMode();
    }

    // ---------------------------------------------------------------
    // Partial Regeneration (Phase 4)
    // ---------------------------------------------------------------

    function setupPartialRegen(templateId) {
        const content = document.getElementById('resultContent');
        if (!content) return;

        // Create floating button
        const floatBtn = document.createElement('button');
        floatBtn.id = 'partialRegenBtn';
        floatBtn.className = 'btn btn-primary btn-sm partial-regen-btn';
        floatBtn.textContent = 'Regenerer cette section';
        floatBtn.style.display = 'none';
        document.body.appendChild(floatBtn);

        content.addEventListener('mouseup', () => {
            const selection = window.getSelection();
            const selectedText = selection.toString().trim();
            if (selectedText.length > 10 && content.contains(selection.anchorNode)) {
                const range = selection.getRangeAt(0);
                const rect = range.getBoundingClientRect();
                floatBtn.style.display = 'block';
                floatBtn.style.top = `${rect.top + window.scrollY - 40}px`;
                floatBtn.style.left = `${rect.left + window.scrollX + (rect.width / 2) - 90}px`;
                floatBtn._selectedText = selectedText;
            } else {
                floatBtn.style.display = 'none';
            }
        });

        document.addEventListener('mousedown', (e) => {
            if (e.target !== floatBtn && !floatBtn.contains(e.target)) {
                floatBtn.style.display = 'none';
            }
        });

        floatBtn.addEventListener('click', async () => {
            const selectedText = floatBtn._selectedText;
            if (!selectedText || !lastRawMarkdown) return;

            const pid = document.getElementById('providerSelect')?.value;
            const modelId = document.getElementById('modelSelect')?.value;
            if (!pid || !modelId) { showToast('Selectionnez un provider et modele', 'error'); return; }

            floatBtn.textContent = 'Regeneration...';
            floatBtn.disabled = true;

            try {
                const { ok, data } = await apiFetch('/api/v1/generate/partial', {
                    method: 'POST',
                    body: JSON.stringify({
                        selected_text: selectedText,
                        full_context: lastRawMarkdown,
                        template_id: templateId,
                        provider: pid,
                        model: modelId,
                    }),
                });
                if (ok && data.replacement) {
                    lastRawMarkdown = lastRawMarkdown.replace(selectedText, data.replacement);
                    flushMarkdownRender(lastRawMarkdown, document.getElementById('resultContent'));
                    // Auto-save
                    if (lastEntryId) {
                        await apiFetch(`/api/v1/history/${lastEntryId}`, {
                            method: 'PATCH',
                            body: JSON.stringify({ result: lastRawMarkdown }),
                        });
                    }
                    showToast('Section regeneree !', 'success');
                } else {
                    showToast(data.error || 'Erreur de regeneration', 'error');
                }
            } catch {
                showToast('Erreur de connexion', 'error');
            } finally {
                floatBtn.textContent = 'Regenerer cette section';
                floatBtn.disabled = false;
                floatBtn.style.display = 'none';
            }
        });
    }

    // ---------------------------------------------------------------
    // Versioning (Phase 6)
    // ---------------------------------------------------------------

    async function loadVersions(entryId, containerEl) {
        if (!containerEl) return;
        try {
            const { ok, data } = await apiFetch(`/api/v1/history/${entryId}/versions`);
            if (ok && data.versions && data.versions.length > 0) {
                containerEl.style.display = 'block';
                const badges = data.versions.map(v =>
                    `<button class="version-badge inline-flex items-center px-3 py-1 border border-slate-200 dark:border-slate-700 rounded-full text-xs font-semibold bg-white dark:bg-slate-800 hover:border-blue-500 hover:text-blue-600 dark:hover:text-blue-400 transition-all cursor-pointer" data-version="${v.version_number}" data-entry="${entryId}" title="${formatTimestamp(v.created_at)}">v${v.version_number}</button>`
                ).join('');
                containerEl.innerHTML = `<div class="flex gap-2 flex-wrap items-center">${badges}</div>`;
                containerEl.querySelectorAll('.version-badge').forEach(badge => {
                    badge.addEventListener('click', () => viewVersion(entryId, badge.dataset.version, containerEl));
                });
            } else {
                containerEl.style.display = 'none';
            }
        } catch {
            containerEl.style.display = 'none';
        }
    }

    async function viewVersion(entryId, versionNum, containerEl) {
        try {
            const { ok, data } = await apiFetch(`/api/v1/history/${entryId}/versions/${versionNum}`);
            if (ok && data.version) {
                const content = document.getElementById('resultContent') || document.getElementById('historyResultContent');
                if (content) {
                    renderMarkdown(data.version.result, content);
                    lastRawMarkdown = data.version.result;
                }
                // Highlight active badge
                if (containerEl) {
                    containerEl.querySelectorAll('.version-badge').forEach(b => {
                        b.classList.remove('bg-blue-600', 'text-white', 'border-blue-600');
                        b.classList.add('bg-white', 'dark:bg-slate-800');
                    });
                    const active = containerEl.querySelector(`[data-version="${versionNum}"]`);
                    if (active) {
                        active.classList.remove('bg-white', 'dark:bg-slate-800');
                        active.classList.add('bg-blue-600', 'text-white', 'border-blue-600');
                    }
                }
                // Show restore button
                let restoreBtn = containerEl?.querySelector('.version-restore-btn');
                if (!restoreBtn && containerEl) {
                    restoreBtn = document.createElement('button');
                    restoreBtn.className = 'version-restore-btn inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition-colors mt-3';
                    restoreBtn.innerHTML = '<i data-lucide="rotate-ccw" class="w-3 h-3"></i> Restaurer cette version';
                    containerEl.appendChild(restoreBtn);
                    if (typeof lucide !== 'undefined') lucide.createIcons({nodes: [restoreBtn]});
                }
                if (restoreBtn) {
                    restoreBtn.style.display = 'inline-flex';
                    restoreBtn.onclick = () => restoreVersion(entryId, versionNum, containerEl);
                }
            }
        } catch {
            showToast('Erreur lors du chargement de la version', 'error');
        }
    }

    async function restoreVersion(entryId, versionNum, containerEl) {
        try {
            const { ok, data } = await apiFetch(`/api/v1/history/${entryId}/versions/${versionNum}/restore`, { method: 'POST' });
            if (ok) {
                showToast('Version restauree !', 'success');
                // Reload versions to show new version badge
                if (containerEl) await loadVersions(entryId, containerEl);
                // Update displayed content
                const content = document.getElementById('resultContent') || document.getElementById('historyResultContent');
                if (content && data.result) {
                    lastRawMarkdown = data.result;
                    renderMarkdown(data.result, content);
                }
            } else {
                showToast(data.error || 'Erreur', 'error');
            }
        } catch {
            showToast('Erreur de connexion', 'error');
        }
    }

    // ---------------------------------------------------------------
    // Provider & Model Management (shared)
    // ---------------------------------------------------------------

    async function loadProviderModels(providerId, selectedModelId, selectEl) {
        const modelSelect = selectEl || document.getElementById('modelSelect');
        if (!modelSelect) return;
        modelSelect.innerHTML = '<option value="">Chargement...</option>';

        try {
            const { ok, data } = await apiFetch(`/api/v1/providers/${providerId}/models`);
            if (ok && data.models && data.models.length > 0) {
                const models = data.models.sort((a, b) => a.id.localeCompare(b.id));
                modelSelect.innerHTML = models.map(m =>
                    `<option value="${escapeHtml(m.id)}" ${m.id === selectedModelId ? 'selected' : ''}>` +
                    `${escapeHtml(m.name)}${m.description ? ' - ' + escapeHtml(m.description.substring(0, 60)) : ''}</option>`
                ).join('');
            } else {
                modelSelect.innerHTML = '<option value="">Aucun modele - configurez votre cle API</option>';
            }
        } catch {
            modelSelect.innerHTML = '<option value="">Erreur de connexion</option>';
        }
    }

    async function refreshProviderModels(providerId, selectEl) {
        const modelSelect = selectEl || document.getElementById('modelSelect');
        if (!modelSelect) return;
        modelSelect.innerHTML = '<option value="">Rafraichissement...</option>';

        try {
            const { ok, data } = await apiFetch(`/api/v1/providers/${providerId}/refresh`, { method: 'POST' });
            if (ok && data.models) {
                const models = data.models.sort((a, b) => a.id.localeCompare(b.id));
                modelSelect.innerHTML = models.map(m =>
                    `<option value="${escapeHtml(m.id)}">${escapeHtml(m.name)}</option>`
                ).join('');
                showToast(`${models.length} modeles charges`, 'success');
            } else {
                modelSelect.innerHTML = '<option value="">Erreur</option>';
                showToast(data.error || 'Erreur lors du rafraichissement', 'error');
            }
        } catch {
            modelSelect.innerHTML = '<option value="">Erreur de connexion</option>';
            showToast('Erreur de connexion', 'error');
        }
    }

    async function saveProviderConfig(providerId, apiKey, modelId) {
        const body = { provider: providerId };
        if (apiKey) body.api_key = apiKey;
        if (modelId) body.model = modelId;

        const { ok, data } = await apiFetch('/api/v1/config', { method: 'POST', body: JSON.stringify(body) });
        if (ok) {
            showToast(data.message || 'Configuration sauvegardee', 'success');
            return true;
        } else {
            showToast(data.error || 'Erreur', 'error');
            return false;
        }
    }

    function setupConfigPanel() {
        const toggleBtn = document.getElementById('toggleConfig');
        const panel = document.getElementById('configPanel');
        if (toggleBtn && panel) {
            toggleBtn.addEventListener('click', () => {
                const visible = panel.style.display !== 'none';
                panel.style.display = visible ? 'none' : 'block';
                const spanEl = toggleBtn.querySelector('span');
                if (spanEl) spanEl.textContent = visible ? 'Configuration' : 'Masquer la configuration';
            });
        }

        // Step 1: Save API key per provider
        document.querySelectorAll('.save-api-key-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const pid = btn.dataset.provider;
                const input = document.getElementById(`apiKey_${pid}`);
                const apiKey = input?.value.trim();
                if (!apiKey) { showToast('Entrez une cle API', 'error'); return; }
                const ok = await saveProviderConfig(pid, apiKey, null);
                if (ok) {
                    input.value = '';
                    input.placeholder = 'Laisser vide pour garder la cle actuelle';
                    // Update badge
                    const badge = btn.closest('.config-key-row')?.querySelector('.badge');
                    if (badge) { badge.className = 'badge badge-ok'; badge.textContent = 'OK'; }
                    // Enable in provider dropdown
                    const opt = document.querySelector(`#defaultProviderSelect option[value="${pid}"]`);
                    if (opt) { opt.disabled = false; opt.textContent = opt.textContent.replace(' (cle manquante)', ''); }
                    // Refresh models if this is the selected provider
                    const sel = document.getElementById('defaultProviderSelect');
                    if (sel && sel.value === pid) {
                        await refreshProviderModels(pid, document.getElementById('defaultModelSelect'));
                    }
                }
            });
        });

        // Step 2: Provider/model selection
        const providerSel = document.getElementById('defaultProviderSelect');
        const modelSel = document.getElementById('defaultModelSelect');

        if (providerSel) {
            providerSel.addEventListener('change', () => {
                loadProviderModels(providerSel.value, null, modelSel);
            });
        }

        const refreshBtn = document.getElementById('refreshDefaultModelsBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                if (providerSel?.value) refreshProviderModels(providerSel.value, modelSel);
            });
        }

        const saveBtn = document.getElementById('saveDefaultBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', async () => {
                const pid = providerSel?.value;
                const modelId = modelSel?.value;
                if (!pid) { showToast('Selectionnez un provider', 'error'); return; }
                if (!modelId) { showToast('Selectionnez un modele', 'error'); return; }
                await saveProviderConfig(pid, null, modelId);
            });
        }
    }

    // ---------------------------------------------------------------
    // Branding / Export Templates (Phase 5)
    // ---------------------------------------------------------------

    async function loadExportTemplates() {
        const list = document.getElementById('brandingList');
        if (!list) return;
        const { ok, data } = await apiFetch('/api/v1/export-templates');
        if (!ok || !data.templates) return;
        if (data.templates.length === 0) {
            list.innerHTML = '<p class="text-xs text-slate-400 dark:text-slate-500 py-2">Aucun template de branding</p>';
            return;
        }
        list.innerHTML = data.templates.map(t => `
            <div class="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200 dark:border-slate-700" data-id="${t.id}">
                <div class="flex items-center gap-3">
                    <div class="w-4 h-4 rounded-full border border-slate-200 dark:border-slate-600" style="background:${t.primary_color || '#2563eb'}"></div>
                    <span class="text-sm font-medium">${escapeHtml(t.name)}</span>
                </div>
                <div class="flex gap-2">
                    <button class="inline-flex items-center gap-1 px-2.5 py-1 border border-slate-200 dark:border-slate-700 rounded-lg text-xs hover:bg-white dark:hover:bg-slate-800 transition-colors" onclick="App.editExportTemplate(${t.id})">
                        <i data-lucide="edit-2" class="w-3 h-3"></i> Modifier
                    </button>
                    <button class="inline-flex items-center gap-1 px-2.5 py-1 border border-red-200 dark:border-red-800/50 text-red-600 dark:text-red-400 rounded-lg text-xs hover:bg-red-50 dark:hover:bg-red-950/50 transition-colors" onclick="App.deleteExportTemplate(${t.id})">
                        <i data-lucide="trash-2" class="w-3 h-3"></i>
                    </button>
                </div>
            </div>
        `).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    async function saveExportTemplate() {
        const name = document.getElementById('brandingName')?.value.trim();
        const header = document.getElementById('brandingHeader')?.value.trim();
        const footer = document.getElementById('brandingFooter')?.value.trim();
        const color = document.getElementById('brandingColor')?.value || '#2563eb';
        const editId = document.getElementById('brandingEditId')?.value;

        if (!name) { showToast('Nom requis', 'error'); return; }

        const payload = { name, header_text: header, footer_text: footer, primary_color: color };
        let url = '/api/v1/export-templates';
        let method = 'POST';
        if (editId) {
            url = `/api/v1/export-templates/${editId}`;
            method = 'PUT';
        }

        const { ok, data } = await apiFetch(url, { method, body: JSON.stringify(payload) });
        if (ok) {
            showToast('Template de branding sauvegarde', 'success');
            resetBrandingForm();
            loadExportTemplates();
        } else {
            showToast(data.error || 'Erreur', 'error');
        }
    }

    async function editExportTemplate(templateId) {
        const { ok, data } = await apiFetch(`/api/v1/export-templates`);
        if (!ok || !data.templates) return;
        const tpl = data.templates.find(t => t.id === templateId);
        if (!tpl) return;

        const nameEl = document.getElementById('brandingName');
        const headerEl = document.getElementById('brandingHeader');
        const footerEl = document.getElementById('brandingFooter');
        const colorEl = document.getElementById('brandingColor');
        const editIdEl = document.getElementById('brandingEditId');

        if (nameEl) nameEl.value = tpl.name;
        if (headerEl) headerEl.value = tpl.header_text || '';
        if (footerEl) footerEl.value = tpl.footer_text || '';
        if (colorEl) colorEl.value = tpl.primary_color || '#2563eb';
        if (editIdEl) editIdEl.value = tpl.id;
    }

    async function deleteExportTemplate(templateId) {
        if (!confirm('Supprimer ce template de branding ?')) return;
        const { ok } = await apiFetch(`/api/v1/export-templates/${templateId}`, { method: 'DELETE' });
        if (ok) { showToast('Supprime', 'success'); loadExportTemplates(); }
        else showToast('Erreur', 'error');
    }

    function resetBrandingForm() {
        const nameEl = document.getElementById('brandingName');
        const headerEl = document.getElementById('brandingHeader');
        const footerEl = document.getElementById('brandingFooter');
        const colorEl = document.getElementById('brandingColor');
        const editIdEl = document.getElementById('brandingEditId');
        if (nameEl) nameEl.value = '';
        if (headerEl) headerEl.value = '';
        if (footerEl) footerEl.value = '';
        if (colorEl) colorEl.value = '#2563eb';
        if (editIdEl) editIdEl.value = '';
    }

    // ---------------------------------------------------------------
    // Meta-Prompt Config (Step 4)
    // ---------------------------------------------------------------

    async function setupMetaPromptConfig() {
        const textarea = document.getElementById('metaPromptText');
        const providerSel = document.getElementById('metaPromptProvider');
        const modelSel = document.getElementById('metaPromptModel');
        const refreshBtn = document.getElementById('refreshMetaModelsBtn');
        const saveBtn = document.getElementById('saveMetaPromptBtn');

        if (!textarea) return;

        // Load existing config
        try {
            const { ok, data } = await apiFetch('/api/v1/config/meta-prompt');
            if (ok) {
                textarea.value = data.meta_prompt || '';
                if (data.provider && providerSel) {
                    providerSel.value = data.provider;
                }
                if (providerSel?.value) {
                    await loadProviderModels(providerSel.value, data.model || null, modelSel);
                }
            }
        } catch { /* ignore */ }

        // Provider change -> load models
        if (providerSel) {
            providerSel.addEventListener('change', () => {
                loadProviderModels(providerSel.value, null, modelSel);
            });
        }

        // Refresh models
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                if (providerSel?.value) refreshProviderModels(providerSel.value, modelSel);
            });
        }

        // Save
        if (saveBtn) {
            saveBtn.addEventListener('click', async () => {
                const { ok, data } = await apiFetch('/api/v1/config/meta-prompt', {
                    method: 'POST',
                    body: JSON.stringify({
                        meta_prompt: textarea.value,
                        provider: providerSel?.value || '',
                        model: modelSel?.value || '',
                    }),
                });
                if (ok) {
                    showToast(data.message || 'Configuration sauvegardee', 'success');
                } else {
                    showToast(data.error || 'Erreur', 'error');
                }
            });
        }
    }

    // ---------------------------------------------------------------
    // Dashboard Page
    // ---------------------------------------------------------------

    let historyPage = 1;
    let currentHistoryEntryId = null;

    function initDashboard(config) {
        initMarkdown();
        setupConfigPanel();

        // Load models for the selected default provider
        const defaultProvider = document.getElementById('defaultProviderSelect');
        const defaultModel = document.getElementById('defaultModelSelect');
        if (defaultProvider && defaultModel) {
            loadProviderModels(defaultProvider.value, config.selected_model, defaultModel);
        }

        // History
        const loadHistoryBtn = document.getElementById('loadHistoryBtn');
        if (loadHistoryBtn) loadHistoryBtn.addEventListener('click', () => { historyPage = 1; loadHistory(); });

        // History filters
        const searchInput = document.getElementById('historySearch');
        const providerFilter = document.getElementById('historyProviderFilter');
        let searchTimeout;
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => { historyPage = 1; loadHistory(); }, 500);
            });
        }
        if (providerFilter) {
            providerFilter.addEventListener('change', () => { historyPage = 1; loadHistory(); });
        }

        // Branding
        loadExportTemplates();
        const saveBrandingBtn = document.getElementById('saveBrandingBtn');
        if (saveBrandingBtn) saveBrandingBtn.addEventListener('click', saveExportTemplate);

        // Meta-prompt config (Step 4)
        setupMetaPromptConfig();
    }

    async function loadHistory() {
        const search = document.getElementById('historySearch')?.value.trim() || '';
        const provider = document.getElementById('historyProviderFilter')?.value || '';
        let url = `/api/v1/history?page=${historyPage}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (provider) url += `&provider=${encodeURIComponent(provider)}`;

        const { ok, data } = await apiFetch(url);
        if (!ok) { showToast('Erreur lors du chargement', 'error'); return; }

        const list = document.getElementById('historyList');
        const paginationEl = document.getElementById('historyPagination');
        if (!list) return;

        if (!data.entries || data.entries.length === 0) {
            list.innerHTML = '<div class="flex flex-col items-center justify-center py-12 text-slate-400 dark:text-slate-500"><p class="text-sm">Aucune generation trouvee</p></div>';
            if (paginationEl) paginationEl.style.display = 'none';
            return;
        }

        list.innerHTML = data.entries.map(entry => `
            <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 hover:border-blue-300 dark:hover:border-blue-700 transition-all">
                <div class="flex items-start justify-between gap-3 mb-2">
                    <div class="flex-1 min-w-0">
                        <p class="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">${escapeHtml(entry.template_name || 'Template inconnu')}</p>
                        ${Object.keys(entry.variables || {}).length > 0
                            ? '<p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate">' + Object.entries(entry.variables).map(([k, v]) =>
                                `${escapeHtml(k)}: ${escapeHtml(String(v).substring(0, 60))}`).join(', ') + '</p>'
                            : ''}
                        <p class="text-[11px] text-slate-400 dark:text-slate-500 mt-1">${escapeHtml(entry.provider)} &middot; ${escapeHtml(entry.model)}</p>
                    </div>
                    <span class="text-[11px] text-slate-400 dark:text-slate-500 whitespace-nowrap">${formatTimestamp(entry.timestamp)}</span>
                </div>
                <div class="flex items-center gap-2 flex-wrap">
                    <button class="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition-colors" onclick="App.viewHistoryEntry(${entry.id})">
                        <i data-lucide="eye" class="w-3 h-3"></i> Voir
                    </button>
                    <div class="relative inline-block">
                        <button class="inline-flex items-center gap-1 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg text-xs font-medium transition-colors" onclick="App.toggleExportMenu(this, event)">
                            <i data-lucide="download" class="w-3 h-3"></i> Exporter
                        </button>
                        <div class="export-dropdown-menu absolute top-full left-0 mt-1 z-50 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg min-w-[140px] overflow-hidden" style="display:none;">
                            <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" onclick="App.exportHistoryFormat(${entry.id}, 'md')">Markdown</button>
                            <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" onclick="App.exportHistoryFormat(${entry.id}, 'html')">HTML</button>
                            <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" onclick="App.exportHistoryFormat(${entry.id}, 'docx')">Word</button>
                            <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" onclick="App.exportHistoryFormat(${entry.id}, 'pdf')">PDF</button>
                        </div>
                    </div>
                    <button class="inline-flex items-center gap-1 px-3 py-1.5 border border-red-200 dark:border-red-800/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/50 rounded-lg text-xs font-medium transition-colors" onclick="App.deleteHistoryEntry(${entry.id})">
                        <i data-lucide="trash-2" class="w-3 h-3"></i>
                    </button>
                </div>
            </div>
        `).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();

        // Pagination
        if (paginationEl && data.pages > 1) {
            paginationEl.style.display = 'flex';
            let html = '';
            if (data.page > 1) html += `<button class="inline-flex items-center gap-1 px-3 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg text-xs font-medium hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" onclick="App.goHistoryPage(${data.page - 1})"><i data-lucide="chevron-left" class="w-3 h-3"></i> Precedent</button>`;
            html += `<span class="text-xs text-slate-500 dark:text-slate-400">Page ${data.page} / ${data.pages} (${data.total} resultats)</span>`;
            if (data.page < data.pages) html += `<button class="inline-flex items-center gap-1 px-3 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg text-xs font-medium hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" onclick="App.goHistoryPage(${data.page + 1})">Suivant <i data-lucide="chevron-right" class="w-3 h-3"></i></button>`;
            paginationEl.innerHTML = html;
            if (typeof lucide !== 'undefined') lucide.createIcons();
        } else if (paginationEl) {
            paginationEl.style.display = 'none';
        }
    }

    function toggleExportMenu(btn, event) {
        event.stopPropagation();
        const menu = btn.nextElementSibling;
        // Close all other menus
        document.querySelectorAll('.export-dropdown-menu').forEach(m => {
            if (m !== menu) m.style.display = 'none';
        });
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }

    function exportHistoryFormat(entryId, format) {
        window.location.href = `/api/v1/export/${entryId}?format=${format}`;
        document.querySelectorAll('.export-dropdown-menu').forEach(m => m.style.display = 'none');
    }

    function goHistoryPage(page) {
        historyPage = page;
        loadHistory();
    }

    async function viewHistoryEntry(entryId) {
        const { ok, data } = await apiFetch(`/api/v1/history/${entryId}`);
        if (!ok) { showToast('Entree non trouvee', 'error'); return; }
        const entry = data.entry;
        currentHistoryEntryId = entryId;

        document.getElementById('historyTemplateName').textContent = entry.template_name || '';
        document.getElementById('historyProvider').textContent = entry.provider || '';
        document.getElementById('historyModel').textContent = entry.model || '';
        document.getElementById('historyDate').textContent = formatTimestamp(entry.timestamp);

        const varsEl = document.getElementById('historyVariables');
        if (varsEl) {
            const vars = entry.variables || {};
            varsEl.innerHTML = Object.keys(vars).length > 0
                ? Object.entries(vars).map(([k, v]) => `<p><strong>${escapeHtml(k)} :</strong> ${escapeHtml(String(v))}</p>`).join('')
                : '<p>Aucune variable</p>';
        }

        const resultEl = document.getElementById('historyResultContent');
        if (resultEl) {
            renderMarkdown(entry.result || '', resultEl);
        }

        // Setup export dropdown for modal
        const exportBtn = document.getElementById('exportHistoryBtn');
        if (exportBtn && !exportBtn._dropdownSetup) {
            const wrapper = document.createElement('div');
            wrapper.className = 'relative inline-block';
            wrapper.innerHTML = `
                <button class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-600 hover:bg-slate-700 dark:bg-slate-700 dark:hover:bg-slate-600 text-white rounded-lg text-xs font-medium transition-colors" type="button">
                    <i data-lucide="download" class="w-3.5 h-3.5"></i> Exporter
                </button>
                <div class="export-dropdown-menu absolute top-full right-0 mt-1 z-50 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg min-w-[160px] overflow-hidden" style="display:none;">
                    <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" data-format="md">Markdown (.md)</button>
                    <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" data-format="html">HTML (.html)</button>
                    <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" data-format="docx">Word (.docx)</button>
                    <button class="block w-full text-left px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors" data-format="pdf">PDF (.pdf)</button>
                </div>
            `;
            exportBtn.replaceWith(wrapper);
            if (typeof lucide !== 'undefined') lucide.createIcons({nodes: [wrapper]});
            const toggleBtn = wrapper.querySelector('button');
            const menu = wrapper.querySelector('.export-dropdown-menu');
            toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
            });
            menu.querySelectorAll('button[data-format]').forEach(opt => {
                opt.addEventListener('click', () => {
                    if (currentHistoryEntryId) {
                        window.location.href = `/api/v1/export/${currentHistoryEntryId}?format=${opt.dataset.format}`;
                    }
                    menu.style.display = 'none';
                });
            });
            wrapper._dropdownSetup = true;
        }

        // Copy buttons in history modal
        const copyRichBtn = document.getElementById('histCopyRichBtn');
        if (copyRichBtn) copyRichBtn.onclick = () => copyRichText(resultEl);
        const copyHtmlBtn = document.getElementById('histCopyHtmlBtn');
        if (copyHtmlBtn) copyHtmlBtn.onclick = () => copyHtmlSource(resultEl);

        // Versions
        const versionsPanel = document.getElementById('historyVersionsPanel');
        if (versionsPanel) loadVersions(entryId, versionsPanel);

        document.getElementById('historyModal').style.display = 'block';
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    function closeHistoryModal() {
        const modal = document.getElementById('historyModal');
        if (modal) modal.style.display = 'none';
    }

    function exportHistoryEntry(entryId) {
        window.location.href = `/api/v1/export/${entryId}`;
    }

    async function deleteHistoryEntry(entryId) {
        if (!confirm('Supprimer cette entree de l\'historique ?')) return;
        const { ok } = await apiFetch(`/api/v1/history/${entryId}`, { method: 'DELETE' });
        if (ok) { showToast('Entree supprimee', 'success'); loadHistory(); }
        else showToast('Erreur lors de la suppression', 'error');
    }

    async function deleteTemplate(templateId) {
        if (!confirm('Supprimer ce template ? Cette action est irreversible.')) return;
        const { ok, data } = await apiFetch(`/api/v1/templates/${templateId}`, { method: 'DELETE' });
        if (ok) { showToast('Template supprime', 'success'); setTimeout(() => location.reload(), 800); }
        else showToast(data.error || 'Erreur', 'error');
    }

    // ---------------------------------------------------------------
    // Magic Wand - AI Template Content Generation
    // ---------------------------------------------------------------

    function setupMagicWand() {
        const btn = document.getElementById('magicWandBtn');
        if (!btn) return;

        const nameInput = document.getElementById('templateName');
        const descInput = document.getElementById('templateDescription');
        const contentArea = document.getElementById('templateContent');

        btn.addEventListener('click', async () => {
            const name = nameInput?.value.trim();
            const description = descInput?.value.trim();

            if (!name) {
                showToast('Remplissez le nom du template avant de generer', 'error');
                nameInput?.focus();
                return;
            }
            if (!description) {
                showToast('Remplissez la description du template avant de generer', 'error');
                descInput?.focus();
                return;
            }

            // Confirm if content textarea is not empty
            if (contentArea?.value.trim()) {
                if (!confirm('Le contenu actuel sera remplace. Continuer ?')) return;
            }

            // Loading state
            const originalHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Generation...';
            if (typeof lucide !== 'undefined') lucide.createIcons({ nodes: [btn] });

            try {
                const { ok, data } = await apiFetch('/api/v1/generate/template-content', {
                    method: 'POST',
                    body: JSON.stringify({ name, description }),
                });

                if (ok && data.content) {
                    contentArea.value = data.content;
                    // Trigger variable detection update
                    contentArea.dispatchEvent(new Event('input', { bubbles: true }));
                    showToast('Contenu genere avec succes !', 'success');
                } else {
                    showToast(data.error || 'Erreur lors de la generation', 'error');
                }
            } catch {
                showToast('Erreur de connexion', 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
                if (typeof lucide !== 'undefined') lucide.createIcons({ nodes: [btn] });
            }
        });
    }

    // ---------------------------------------------------------------
    // Template Form Page
    // ---------------------------------------------------------------

    function initTemplateForm(config, templateId, templateData) {
        const providerSelect = document.getElementById('defaultProvider');
        const modelSelect = document.getElementById('defaultModel');
        const contentArea = document.getElementById('templateContent');

        // Load models for the default provider
        const defaultPid = templateData?.default_provider || config.selected_provider || 'zai';
        const defaultModel = templateData?.default_model || config.selected_model || null;
        loadProviderModels(defaultPid, defaultModel, modelSelect);

        if (providerSelect) {
            providerSelect.addEventListener('change', () => {
                loadProviderModels(providerSelect.value, null, modelSelect);
            });
        }

        // Parse variables in real time
        if (contentArea) {
            contentArea.addEventListener('input', () => {
                displayVariables(extractVariables(contentArea.value));
            });
            // Initial parse
            if (contentArea.value) displayVariables(extractVariables(contentArea.value));
        }

        // Form submission
        const form = document.getElementById('templateForm');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(form);
                const body = Object.fromEntries(formData);
                body.default_provider = providerSelect?.value || 'zai';
                body.default_model = modelSelect?.value || '';

                const url = templateId ? `/api/v1/templates/${templateId}` : '/api/v1/templates';
                const method = templateId ? 'PUT' : 'POST';

                const { ok, data } = await apiFetch(url, { method, body: JSON.stringify(body) });
                if (ok) {
                    showToast('Template sauvegarde', 'success');
                    setTimeout(() => window.location.href = '/', 800);
                } else {
                    showToast(data.error || 'Erreur lors de la sauvegarde', 'error');
                }
            });
        }

        // Magic wand button
        setupMagicWand();
    }

    // ---------------------------------------------------------------
    // Use Template Page
    // ---------------------------------------------------------------

    let lastEntryId = null;

    function initUseTemplate(config, template, templateId) {
        initMarkdown();

        // Toggle config panel
        const toggleBtn = document.getElementById('toggleConfig');
        const panel = document.getElementById('configPanel');
        if (toggleBtn && panel) {
            toggleBtn.addEventListener('click', () => {
                const visible = panel.style.display !== 'none';
                panel.style.display = visible ? 'none' : 'block';
                toggleBtn.querySelector('span').textContent = visible
                    ? 'Provider & Modele'
                    : 'Masquer';
            });
        }

        const providerSelect = document.getElementById('providerSelect');
        const modelSelect = document.getElementById('modelSelect');
        const defaultPid = template.default_provider || config.selected_provider || 'zai';
        const defaultModel = template.default_model || config.selected_model || '';
        loadProviderModels(defaultPid, defaultModel, modelSelect);

        if (providerSelect) {
            providerSelect.addEventListener('change', () => {
                loadProviderModels(providerSelect.value, null, modelSelect);
            });
        }

        const refreshBtn = document.getElementById('refreshModelsBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                if (providerSelect?.value) refreshProviderModels(providerSelect.value, modelSelect);
            });
        }

        // Generate form
        const form = document.getElementById('generateForm');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const useStreaming = document.getElementById('streamToggle')?.checked;
                const pid = document.getElementById('providerSelect')?.value || defaultPid;
                const modelId = document.getElementById('modelSelect')?.value || defaultModel;

                if (!modelId) { showToast('Selectionnez un modele', 'error'); return; }

                const formData = new FormData(form);
                const variables = {};
                for (const [key, value] of formData.entries()) variables[key] = value.trim();

                const btn = document.getElementById('generateBtn');
                btn.disabled = true;
                btn.textContent = 'Generation en cours...';
                btn.classList.add('btn-loader');

                const payload = { template_id: templateId, provider: pid, model: modelId, variables };

                if (useStreaming) {
                    await generateWithStreaming(payload, btn);
                } else {
                    await generateSync(payload, btn);
                }
            });
        }

        // Close result modal
        const closeBtn = document.getElementById('closeResultBtn');
        if (closeBtn) closeBtn.addEventListener('click', () => {
            document.getElementById('resultModal').style.display = 'none';
        });

        // Export dropdown
        setupExportDropdown('exportBtn', () => lastEntryId);

        // Copy buttons
        const copyRichBtn = document.getElementById('copyRichBtn');
        if (copyRichBtn) copyRichBtn.addEventListener('click', () => copyRichText(document.getElementById('resultContent')));
        const copyHtmlBtn = document.getElementById('copyHtmlBtn');
        if (copyHtmlBtn) copyHtmlBtn.addEventListener('click', () => copyHtmlSource(document.getElementById('resultContent')));

        // Edit buttons
        const editBtn = document.getElementById('editBtn');
        if (editBtn) editBtn.addEventListener('click', toggleEditMode);
        const saveEditBtn = document.getElementById('saveEditBtn');
        if (saveEditBtn) saveEditBtn.addEventListener('click', saveEdit);
        const cancelEditBtn = document.getElementById('cancelEditBtn');
        if (cancelEditBtn) cancelEditBtn.addEventListener('click', cancelEdit);

        // Partial regen
        setupPartialRegen(templateId);
    }

    async function generateSync(payload, btn) {
        try {
            const { ok, data } = await apiFetch('/api/v1/generate', { method: 'POST', body: JSON.stringify(payload) });
            if (ok) {
                lastEntryId = data.entry_id;
                lastRawMarkdown = data.result;
                showResult(data.result);
                showToast('Generation reussie !', 'success');
            } else {
                showToast(data.error || 'Erreur lors de la generation', 'error');
            }
        } catch {
            showToast('Erreur de connexion', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Generer le resultat';
            btn.classList.remove('btn-loader');
        }
    }

    async function generateWithStreaming(payload, btn) {
        const modal = document.getElementById('resultModal');
        const content = document.getElementById('resultContent');
        const progress = document.getElementById('streamProgress');
        const statusEl = progress?.querySelector('.stream-status');

        modal.style.display = 'block';
        content.innerHTML = '';
        content.classList.remove('markdown');
        content.classList.add('rendered-markdown');
        lastRawMarkdown = '';
        if (progress) progress.style.display = 'flex';
        if (statusEl) statusEl.textContent = 'Generation en cours...';

        // Hide edit buttons during generation
        const editBtn = document.getElementById('editBtn');
        if (editBtn) editBtn.style.display = 'none';

        try {
            const response = await fetch('/api/v1/generate/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                // Non-SSE error response (CSRF, auth, server error)
                let errMsg = 'Erreur serveur';
                try {
                    const errData = await response.json();
                    errMsg = errData.error || errMsg;
                } catch {}
                if (progress) progress.style.display = 'none';
                showToast(errMsg, 'error');
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));
                        if (event.type === 'token') {
                            lastRawMarkdown += event.content;
                            renderMarkdownThrottled(lastRawMarkdown, content);
                        } else if (event.type === 'done') {
                            lastRawMarkdown = event.content;
                            flushMarkdownRender(lastRawMarkdown, content);
                            if (progress) progress.style.display = 'none';
                            if (editBtn) editBtn.style.display = 'inline-flex';
                            showToast('Generation terminee !', 'success');
                            // Load versions
                            const versionsPanel = document.getElementById('versionsPanel');
                            if (versionsPanel && lastEntryId) loadVersions(lastEntryId, versionsPanel);
                        } else if (event.type === 'saved') {
                            lastEntryId = event.entry_id;
                        } else if (event.type === 'error') {
                            if (progress) progress.style.display = 'none';
                            showToast(event.message || 'Erreur', 'error');
                        } else if (event.type === 'start') {
                            if (statusEl) statusEl.textContent = event.message;
                        }
                    } catch { /* ignore malformed events */ }
                }
            }
        } catch (err) {
            if (progress) progress.style.display = 'none';
            showToast('Erreur de connexion au streaming', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Generer le resultat';
            btn.classList.remove('btn-loader');
            // Hide progress bar if still visible (no content received)
            if (progress && progress.style.display !== 'none' && !lastRawMarkdown) {
                progress.style.display = 'none';
                showToast('Aucun contenu recu', 'error');
            }
        }
    }

    function showResult(result) {
        const modal = document.getElementById('resultModal');
        const content = document.getElementById('resultContent');
        const progress = document.getElementById('streamProgress');
        if (progress) progress.style.display = 'none';
        if (content) renderMarkdown(result, content);
        if (modal) modal.style.display = 'block';
        // Show edit button
        const editBtn = document.getElementById('editBtn');
        if (editBtn) editBtn.style.display = 'inline-flex';
        // Load versions
        const versionsPanel = document.getElementById('versionsPanel');
        if (versionsPanel && lastEntryId) loadVersions(lastEntryId, versionsPanel);
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    // ---------------------------------------------------------------
    // Global: close dropdowns on outside click
    // ---------------------------------------------------------------
    document.addEventListener('click', () => {
        document.querySelectorAll('.export-dropdown-menu').forEach(m => m.style.display = 'none');
    });

    // ---------------------------------------------------------------
    // Public API
    // ---------------------------------------------------------------
    return {
        initDashboard,
        initTemplateForm,
        initUseTemplate,
        deleteTemplate,
        viewHistoryEntry,
        exportHistoryEntry,
        exportHistoryFormat,
        toggleExportMenu,
        deleteHistoryEntry,
        closeHistoryModal,
        goHistoryPage,
        showToast,
        editExportTemplate,
        deleteExportTemplate,
        saveExportTemplate,
    };
})();
