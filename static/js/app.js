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
        const pattern = /\{(\w+)\}/g;
        const matches = [];
        let m;
        while ((m = pattern.exec(content)) !== null) matches.push(m[1]);
        return [...new Set(matches)];
    }

    function displayVariables(variables) {
        const preview = document.getElementById('variablesPreview');
        const list = document.getElementById('variablesList');
        if (!preview || !list) return;
        if (variables.length > 0) {
            preview.style.display = 'block';
            list.innerHTML = variables.map(v => `<span class="variable-tag">${escapeHtml(v)}</span>`).join('');
        } else {
            preview.style.display = 'none';
        }
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
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
                toggleBtn.querySelector('span').textContent = visible
                    ? 'Configuration Provider & Modele'
                    : 'Masquer la configuration';
            });
        }

        const providerSelect = document.getElementById('providerSelect');
        if (providerSelect) {
            providerSelect.addEventListener('change', () => {
                loadProviderModels(providerSelect.value, null);
            });
        }

        const refreshBtn = document.getElementById('refreshModelsBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                const pid = document.getElementById('providerSelect')?.value;
                if (pid) refreshProviderModels(pid);
            });
        }
    }

    // ---------------------------------------------------------------
    // Dashboard Page
    // ---------------------------------------------------------------

    let historyPage = 1;

    function initDashboard(config) {
        setupConfigPanel();
        loadProviderModels(config.selected_provider, config.selected_model);

        // Save config button
        const saveBtn = document.getElementById('saveConfigBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', async () => {
                const pid = document.getElementById('providerSelect')?.value;
                const apiKey = document.getElementById('apiKeyInput')?.value.trim();
                const modelId = document.getElementById('modelSelect')?.value;
                if (!pid) { showToast('Selectionnez un provider', 'error'); return; }
                const ok = await saveProviderConfig(pid, apiKey, modelId);
                if (ok && apiKey) {
                    document.getElementById('apiKeyInput').value = '';
                    await refreshProviderModels(pid);
                }
            });
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
            list.innerHTML = '<p class="empty-history">Aucune generation trouvee</p>';
            if (paginationEl) paginationEl.style.display = 'none';
            return;
        }

        list.innerHTML = data.entries.map(entry => `
            <div class="history-item">
                <div class="history-header">
                    <div class="history-prompt">
                        <strong>${escapeHtml(entry.template_name || 'Template inconnu')}</strong>
                        ${Object.keys(entry.variables || {}).length > 0
                            ? '<br><small>' + Object.entries(entry.variables).map(([k, v]) =>
                                `${escapeHtml(k)}: ${escapeHtml(String(v).substring(0, 80))}`).join(', ') + '</small>'
                            : ''}
                        <br><small class="provider-info">${escapeHtml(entry.provider)} - ${escapeHtml(entry.model)}</small>
                    </div>
                    <div class="history-timestamp">${formatTimestamp(entry.timestamp)}</div>
                </div>
                <div class="history-actions">
                    <button class="btn btn-primary btn-sm" onclick="App.viewHistoryEntry(${entry.id})">Voir</button>
                    <button class="btn btn-secondary btn-sm" onclick="App.exportHistoryEntry(${entry.id})">Exporter</button>
                    <button class="btn btn-danger btn-sm" onclick="App.deleteHistoryEntry(${entry.id})">Supprimer</button>
                </div>
            </div>
        `).join('');

        // Pagination
        if (paginationEl && data.pages > 1) {
            paginationEl.style.display = 'flex';
            let html = '';
            if (data.page > 1) html += `<button class="btn btn-sm btn-outline" onclick="App.goHistoryPage(${data.page - 1})">Precedent</button>`;
            html += `<span class="pagination-info">Page ${data.page} / ${data.pages} (${data.total} resultats)</span>`;
            if (data.page < data.pages) html += `<button class="btn btn-sm btn-outline" onclick="App.goHistoryPage(${data.page + 1})">Suivant</button>`;
            paginationEl.innerHTML = html;
        } else if (paginationEl) {
            paginationEl.style.display = 'none';
        }
    }

    function goHistoryPage(page) {
        historyPage = page;
        loadHistory();
    }

    async function viewHistoryEntry(entryId) {
        const { ok, data } = await apiFetch(`/api/v1/history/${entryId}`);
        if (!ok) { showToast('Entree non trouvee', 'error'); return; }
        const entry = data.entry;

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
        if (resultEl) resultEl.textContent = entry.result || '';

        const exportBtn = document.getElementById('exportHistoryBtn');
        if (exportBtn) exportBtn.onclick = () => exportHistoryEntry(entryId);

        document.getElementById('historyModal').style.display = 'block';
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
    // Template Form Page
    // ---------------------------------------------------------------

    function initTemplateForm(config, templateId, templateData) {
        const providerSelect = document.getElementById('defaultProvider');
        const modelSelect = document.getElementById('defaultModel');
        const contentArea = document.getElementById('templateContent');

        // Load models for the default provider
        const defaultPid = templateData?.default_provider || 'zai';
        const defaultModel = templateData?.default_model || null;
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
    }

    // ---------------------------------------------------------------
    // Use Template Page
    // ---------------------------------------------------------------

    let lastEntryId = null;

    function initUseTemplate(config, template, templateId) {
        setupConfigPanel();

        const defaultPid = template.default_provider || config.selected_provider || 'zai';
        const defaultModel = template.default_model || config.selected_model || '';
        loadProviderModels(defaultPid, defaultModel);

        // Save API key button
        const saveApiKeyBtn = document.getElementById('saveApiKeyBtn');
        if (saveApiKeyBtn) {
            saveApiKeyBtn.addEventListener('click', async () => {
                const pid = document.getElementById('providerSelect')?.value;
                const apiKey = document.getElementById('apiKeyInput')?.value.trim();
                if (!apiKey) { showToast('Entrez une cle API', 'error'); return; }
                const ok = await saveProviderConfig(pid, apiKey, null);
                if (ok) {
                    document.getElementById('apiKeyInput').value = '';
                    await refreshProviderModels(pid);
                }
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

        // Export
        const exportBtn = document.getElementById('exportBtn');
        if (exportBtn) exportBtn.addEventListener('click', () => {
            if (lastEntryId) window.location.href = `/api/v1/export/${lastEntryId}`;
            else showToast('Aucun resultat a exporter', 'error');
        });
    }

    async function generateSync(payload, btn) {
        try {
            const { ok, data } = await apiFetch('/api/v1/generate', { method: 'POST', body: JSON.stringify(payload) });
            if (ok) {
                lastEntryId = data.entry_id;
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
        content.textContent = '';
        if (progress) progress.style.display = 'flex';
        if (statusEl) statusEl.textContent = 'Generation en cours...';

        try {
            const response = await fetch('/api/v1/generate/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify(payload),
            });

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
                            content.textContent += event.content;
                            content.scrollTop = content.scrollHeight;
                        } else if (event.type === 'done') {
                            content.textContent = event.content;
                            if (progress) progress.style.display = 'none';
                            showToast('Generation terminee !', 'success');
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
        }
    }

    function showResult(result) {
        const modal = document.getElementById('resultModal');
        const content = document.getElementById('resultContent');
        const progress = document.getElementById('streamProgress');
        if (progress) progress.style.display = 'none';
        if (content) content.textContent = result;
        if (modal) modal.style.display = 'block';
    }

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
        deleteHistoryEntry,
        closeHistoryModal,
        goHistoryPage,
        showToast,
    };
})();
