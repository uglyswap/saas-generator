// Variables globales
let editingTemplateId = null;

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
});

// Configuration des écouteurs d'événements
function setupEventListeners() {
    // Toggle configuration
    document.getElementById('toggleConfig').addEventListener('click', toggleConfig);

    // Sauvegarde clé API
    document.getElementById('saveApiKey').addEventListener('click', saveApiKey);

    // Créer nouveau template
    document.getElementById('createTemplateBtn').addEventListener('click', openCreateModal);

    // Sauvegarder template
    document.getElementById('saveTemplateBtn').addEventListener('click', saveTemplate);

    // Charger historique
    document.getElementById('loadHistoryBtn').addEventListener('click', loadHistory);

    // Parser les variables en temps réel
    document.getElementById('templateContent').addEventListener('input', parseVariables);
}

// Toggle panneau de configuration
function toggleConfig() {
    const panel = document.getElementById('configPanel');
    const toggle = document.getElementById('toggleConfig');

    if (panel.style.display === 'none') {
        panel.style.display = 'block';
        toggle.querySelector('span').textContent = '⚙️ Masquer la configuration';
    } else {
        panel.style.display = 'none';
        toggle.querySelector('span').textContent = '⚙️ Configuration API';
    }
}

// Sauvegarder la clé API
async function saveApiKey() {
    const apiKey = document.getElementById('apiKeyInput').value.trim();

    if (!apiKey) {
        showToast('Veuillez entrer une clé API', 'error');
        return;
    }

    try {
        // Utiliser l'endpoint /api/config au lieu de l'ancien /api/save-api-key
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                provider: 'zai',  // Provider par défaut
                api_key: apiKey
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Clé API sauvegardée avec succès', 'success');
            document.getElementById('apiKeyInput').value = '';
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast(data.error || 'Erreur lors de la sauvegarde', 'error');
        }
    } catch (error) {
        showToast('Erreur de connexion au serveur', 'error');
        console.error('Error saving API key:', error);
    }
}

// Ouvrir le modal de création
function openCreateModal() {
    editingTemplateId = null;
    document.getElementById('modalTitle').textContent = 'Créer un nouveau template';
    document.getElementById('templateName').value = '';
    document.getElementById('templateDescription').value = '';
    document.getElementById('templateContent').value = '';
    document.getElementById('variablesPreview').style.display = 'none';
    document.getElementById('templateModal').style.display = 'block';
}

// Ouvrir le modal d'édition
function editTemplate(templateId) {
    editingTemplateId = templateId;
    document.getElementById('modalTitle').textContent = 'Modifier le template';
    document.getElementById('templateModal').style.display = 'block';

    // Charger le template
    fetch(`/api/templates`)
        .then(res => res.json())
        .then(data => {
            const template = data.templates.find(t => t.id === templateId);
            if (template) {
                document.getElementById('templateName').value = template.name;
                document.getElementById('templateDescription').value = template.description || '';
                document.getElementById('templateContent').value = template.content;
                parseVariables();
            }
        })
        .catch(error => {
            showToast('Erreur lors du chargement du template', 'error');
            console.error('Error:', error);
        });
}

// Fermer le modal
function closeModal() {
    document.getElementById('templateModal').style.display = 'none';
    editingTemplateId = null;
}

// Parser les variables
function parseVariables() {
    const content = document.getElementById('templateContent').value;
    const variables = extractVariables(content);
    displayVariables(variables);
}

// Extraire les variables
function extractVariables(content) {
    const pattern = /\{([^}]+)\}/g;
    const matches = [];
    let match;
    while ((match = pattern.exec(content)) !== null) {
        matches.push(match[1]);
    }
    return [...new Set(matches)]; // Éliminer les doublons
}

// Afficher les variables
function displayVariables(variables) {
    const preview = document.getElementById('variablesPreview');
    const list = document.getElementById('variablesList');

    if (variables.length > 0) {
        preview.style.display = 'block';
        list.innerHTML = variables.map(v => `<span class="variable-tag">${v}</span>`).join('');
    } else {
        preview.style.display = 'none';
    }
}

// Sauvegarder le template
async function saveTemplate() {
    const name = document.getElementById('templateName').value.trim();
    const description = document.getElementById('templateDescription').value.trim();
    const content = document.getElementById('templateContent').value.trim();

    if (!name || !content) {
        showToast('Le nom et le contenu sont obligatoires', 'error');
        return;
    }

    const data = { name, description, content };

    try {
        let url = '/api/templates';
        let method = 'POST';

        if (editingTemplateId) {
            url = `/api/templates/${editingTemplateId}`;
            method = 'PUT';
        }

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok) {
            showToast(editingTemplateId ? 'Template mis à jour' : 'Template créé', 'success');
            closeModal();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast(result.error || 'Erreur lors de la sauvegarde', 'error');
        }
    } catch (error) {
        showToast('Erreur de connexion au serveur', 'error');
        console.error('Error saving template:', error);
    }
}

// Utiliser un template
function useTemplate(templateId) {
    window.location.href = `/template/${templateId}`;
}

// Supprimer un template
async function deleteTemplate(templateId) {
    if (!confirm('Êtes-vous sûr de vouloir supprimer ce template ?')) {
        return;
    }

    try {
        const response = await fetch(`/api/templates/${templateId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Template supprimé avec succès', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast(data.error || 'Erreur lors de la suppression', 'error');
        }
    } catch (error) {
        showToast('Erreur de connexion au serveur', 'error');
        console.error('Error deleting template:', error);
    }
}

// Charger l'historique
async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();

        if (response.ok) {
            displayHistory(data.history);
        } else {
            showToast(data.error || 'Erreur lors du chargement', 'error');
        }
    } catch (error) {
        showToast('Erreur de connexion au serveur', 'error');
        console.error('Error loading history:', error);
    }
}

// Afficher l'historique
function displayHistory(history) {
    const historyList = document.getElementById('historyList');

    if (!history || history.length === 0) {
        historyList.innerHTML = '<p class="empty-history">Aucune génération pour le moment</p>';
        return;
    }

    historyList.innerHTML = history.map(entry => `
        <div class="history-item">
            <div class="history-header">
                <div class="history-prompt">
                    <strong>${entry.template_name || 'Template inconnu'}</strong>
                    ${Object.keys(entry.variables || {}).length > 0 ? '<br><small>' + Object.entries(entry.variables).map(([k, v]) => `${k}: ${v}`).join(', ') + '</small>' : ''}
                </div>
                <div class="history-timestamp">${formatTimestamp(entry.timestamp)}</div>
            </div>
            <div class="history-actions">
                <button class="btn btn-primary btn-sm" onclick="viewHistoryEntry('${entry.id}')">
                    👁️ Voir
                </button>
                <button class="btn btn-secondary btn-sm" onclick="exportHistoryEntry('${entry.id}')">
                    📥 Exporter
                </button>
                <button class="btn btn-danger btn-sm" onclick="deleteHistoryEntry('${entry.id}')">
                    🗑️ Supprimer
                </button>
            </div>
        </div>
    `).join('');
}

// Voir une entrée de l'historique
function viewHistoryEntry(entryId) {
    // Pour l'instant, on peut seulement exporter
    exportHistoryEntry(entryId);
}

// Exporter une entrée de l'historique
function exportHistoryEntry(entryId) {
    window.location.href = `/api/export/${entryId}`;
}

// Supprimer une entrée de l'historique
async function deleteHistoryEntry(entryId) {
    if (!confirm('Êtes-vous sûr de vouloir supprimer cette entrée ?')) {
        return;
    }

    try {
        const response = await fetch(`/api/history/${entryId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Entrée supprimée avec succès', 'success');
            loadHistory();
        } else {
            showToast(data.error || 'Erreur lors de la suppression', 'error');
        }
    } catch (error) {
        showToast('Erreur de connexion au serveur', 'error');
        console.error('Error deleting entry:', error);
    }
}

// Formater le timestamp
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    // Moins d'une minute
    if (diff < 60000) {
        return 'À l\'instant';
    }

    // Moins d'une heure
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return `Il y a ${minutes} minute${minutes > 1 ? 's' : ''}`;
    }

    // Moins d'un jour
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `Il y a ${hours} heure${hours > 1 ? 's' : ''}`;
    }

    // Moins d'une semaine
    if (diff < 604800000) {
        const days = Math.floor(diff / 86400000);
        return `Il y a ${days} jour${days > 1 ? 's' : ''}`;
    }

    // Format de date complet
    return date.toLocaleDateString('fr-FR', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Afficher une notification toast
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.style.display = 'block';

    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}
