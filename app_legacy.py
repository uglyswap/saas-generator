import os
import json
import re
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["JSON_ENSURE_ASCII"] = False
app.config["JSON_SORT_KEYS"] = False

# Configuration
HISTORY_FILE = "history.json"
TEMPLATES_FILE = "templates.json"
CONFIG_FILE = "config.json"


def load_config():
    """Charge la configuration depuis le fichier JSON"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass

    # Configuration par défaut
    return {
        "providers": {
            "zai": {
                "name": "Z.AI",
                "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "api_key": "",
                "default_model": "glm-4.7",
                "models_url": "https://open.bigmodel.cn/api/paas/v4/models",
                "models": [],
            },
            "openrouter": {
                "name": "OpenRouter",
                "api_url": "https://openrouter.ai/api/v1/chat/completions",
                "api_key": "",
                "default_model": "anthropic/claude-3.5-sonnet",
                "models_url": "https://openrouter.ai/api/v1/models",
                "models": [],
            },
        },
        "selected_provider": "zai",
        "selected_model": "glm-4.7",
    }


def save_config(config):
    """Sauvegarde la configuration dans le fichier JSON"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_provider_config(provider_id):
    """Récupère la configuration d'un provider"""
    config = load_config()
    return config["providers"].get(provider_id)


def get_selected_provider():
    """Récupère le provider sélectionné"""
    config = load_config()
    provider_id = config.get("selected_provider", "zai")
    return provider_id, config["providers"][provider_id]


def get_selected_model():
    """Récupère le modèle sélectionné"""
    config = load_config()
    return config.get("selected_model", "glm-4.7")


def fetch_zai_models():
    """Récupère la liste des modèles depuis Z.AI"""
    config = load_config()
    provider = config["providers"]["zai"]
    api_key = provider.get("api_key", "")

    if not api_key:
        print("[ERROR] Clé API Z.AI manquante")
        return (
            None,
            "Clé API Z.AI manquante. Veuillez configurer votre clé API dans le panneau de configuration.",
        )

    try:
        response = requests.get(
            provider["models_url"],
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Extraire et formater les modèles
        models = []
        for model in data.get("data", []):
            models.append(
                {
                    "id": model.get("id"),
                    "name": model.get("id", ""),
                    "description": model.get("object", ""),
                }
            )

        # Trier par ordre alphabétique
        models.sort(key=lambda x: x["id"].lower())

        return models, None

    except requests.exceptions.HTTPError as e:
        error_msg = f"Erreur HTTP {response.status_code}: {str(e)}"
        if response.status_code == 401:
            error_msg = "Clé API Z.AI invalide. Veuillez vérifier votre clé."
        elif response.status_code == 403:
            error_msg = "Accès refusé. Vérifiez votre clé API Z.AI."
        elif response.status_code == 429:
            error_msg = "Trop de requêtes. Veuillez attendre quelques instants."
        print(f"[ERROR] Erreur HTTP Z.AI: {error_msg}")
        return None, error_msg
    except requests.exceptions.ConnectionError as e:
        error_msg = "Erreur de connexion à Z.AI. Vérifiez votre connexion internet."
        print(f"[ERROR] Erreur de connexion Z.AI: {e}")
        return None, error_msg
    except requests.exceptions.Timeout:
        error_msg = "Délai d'attente dépassé. Z.AI ne répond pas."
        print(f"[ERROR] Timeout Z.AI")
        return None, error_msg
    except Exception as e:
        error_msg = f"Erreur inattendue: {str(e)}"
        print(f"[ERROR] Erreur Z.AI: {e}")
        return None, error_msg


def fetch_openrouter_models():
    """Récupère la liste des modèles depuis OpenRouter"""
    config = load_config()
    provider = config["providers"]["openrouter"]
    api_key = provider.get("api_key", "")

    if not api_key:
        print("[ERROR] Clé API OpenRouter manquante")
        return (
            None,
            "Clé API OpenRouter manquante. Veuillez configurer votre clé API dans le panneau de configuration.",
        )

    try:
        response = requests.get(
            provider["models_url"],
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Extraire et formater les modèles
        models = []
        for model in data.get("data", []):
            models.append(
                {
                    "id": model.get("id"),
                    "name": model.get("name", model.get("id", "")),
                    "description": model.get("description", ""),
                    "context_length": model.get("context_length", 0),
                    "pricing": model.get("pricing", {}),
                }
            )

        # Trier par ordre alphabétique
        models.sort(key=lambda x: x["id"].lower())

        return models, None

    except requests.exceptions.HTTPError as e:
        error_msg = f"Erreur HTTP {response.status_code}: {str(e)}"
        if response.status_code == 401:
            error_msg = "Clé API OpenRouter invalide. Veuillez vérifier votre clé."
        elif response.status_code == 403:
            error_msg = "Accès refusé. Vérifiez votre clé API OpenRouter."
        elif response.status_code == 429:
            error_msg = "Trop de requêtes. Veuillez attendre quelques instants."
        print(f"[ERROR] Erreur HTTP OpenRouter: {error_msg}")
        return None, error_msg
    except requests.exceptions.ConnectionError as e:
        error_msg = (
            "Erreur de connexion à OpenRouter. Vérifiez votre connexion internet."
        )
        print(f"[ERROR] Erreur de connexion OpenRouter: {e}")
        return None, error_msg
    except requests.exceptions.Timeout:
        error_msg = "Délai d'attente dépassé. OpenRouter ne répond pas."
        print(f"[ERROR] Timeout OpenRouter")
        return None, error_msg
    except Exception as e:
        error_msg = f"Erreur inattendue: {str(e)}"
        print(f"[ERROR] Erreur OpenRouter: {e}")
        return None, error_msg


def update_zai_models():
    """Met à jour la liste des modèles Z.AI dans la config"""
    models, error = fetch_zai_models()

    if models:
        config = load_config()
        config["providers"]["zai"]["models"] = models
        save_config(config)

    return models, error


def update_openrouter_models():
    """Met à jour la liste des modèles OpenRouter dans la config"""
    models, error = fetch_openrouter_models()

    if models:
        config = load_config()
        config["providers"]["openrouter"]["models"] = models
        save_config(config)

    return models, error


def extract_variables(template_content):
    """Extrait les variables d'un template (format: {variable})"""
    pattern = r"\{([^}]+)\}"
    variables = re.findall(pattern, template_content)
    return list(set(variables))  # Éliminer les doublons


def load_templates():
    """Charge les templates depuis le fichier JSON"""
    if os.path.exists(TEMPLATES_FILE):
        try:
            with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []


def save_templates(templates):
    """Sauvegarde les templates dans le fichier JSON"""
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)


def load_history():
    """Charge l'historique depuis le fichier JSON"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def save_history(history):
    """Sauvegarde l'historique dans le fichier JSON"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def call_llm_api(prompt, provider_id, model_id):
    """Appelle l'API du provider sélectionné"""
    config = load_config()
    provider = config["providers"][provider_id]

    api_url = provider["api_url"]
    api_key = provider.get("api_key", "")

    if not api_key:
        return None, f"Clé API manquante pour {provider['name']}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 8192,
        "top_p": 0.95,
    }

    # Ajouter des paramètres spécifiques selon le provider
    if provider_id == "zai":
        payload["thinking"] = {"type": "disabled"}

    try:
        print(f"[API] Appel à {provider['name']} avec modèle {model_id}...")
        response = requests.post(api_url, headers=headers, json=payload, timeout=180)
        print(f"[API] Réponse reçue - Status: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        # Extraire le contenu de la réponse
        if "choices" in data and len(data["choices"]) > 0:
            message = data["choices"][0]["message"]
            content = message.get("content", "")

            # Si content est vide, essayer reasoning_content (Z.AI)
            if not content and "reasoning_content" in message:
                content = message["reasoning_content"]

            if content:
                print(
                    f"[API] Succès - Longueur de la réponse: {len(content)} caractères"
                )
                return content, None
            else:
                error_msg = f"Contenu vide dans la réponse API. Réponse: {data}"
                print(f"[API] Erreur: {error_msg}")
                return None, error_msg
        else:
            error_msg = f"Format de réponse invalide de l'API. Réponse: {data}"
            print(f"[API] Erreur: {error_msg}")
            return None, error_msg

    except requests.exceptions.Timeout:
        error_msg = "Délai d'attente dépassé (3 minutes). Le provider met trop de temps à répondre."
        print(f"[API] Timeout: {error_msg}")
        return None, error_msg
    except requests.exceptions.HTTPError as e:
        error_msg = f"Erreur HTTP {response.status_code}: {e}"
        if response.status_code == 401:
            error_msg = "Erreur d'authentification. Vérifiez votre clé API."
        elif response.status_code == 429:
            error_msg = "Trop de requêtes. Veuillez attendre quelques instants."
        elif response.status_code >= 500:
            error_msg = "Erreur serveur. Veuillez réessayer dans quelques minutes."
        print(f"[API] HTTP Error: {error_msg}")
        return None, error_msg
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Erreur de connexion au serveur: {str(e)}. Vérifiez votre connexion internet."
        print(f"[API] Connection Error: {error_msg}")
        return None, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"Erreur API: {str(e)}"
        print(f"[API] Request Error: {error_msg}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Erreur inattendue: {str(e)}"
        print(f"[API] Unexpected Error: {error_msg}")
        return None, error_msg


# Routes principales
@app.route("/")
def index():
    """Page d'accueil - Liste des templates"""
    config = load_config()
    templates = load_templates()

    return render_template(
        "index.html",
        templates=templates,
        config=config,
        selected_provider=config.get("selected_provider", "zai"),
    )


@app.route("/template/new")
def new_template():
    """Page de création de template"""
    config = load_config()
    return render_template("template_form.html", template=None, config=config)


@app.route("/template/<template_id>")
def view_template(template_id):
    """Page d'utilisation d'un template"""
    config = load_config()
    templates = load_templates()
    template = next((t for t in templates if t["id"] == template_id), None)

    if not template:
        return jsonify({"error": "Template non trouvé"}), 404

    # Extraire les variables
    variables = extract_variables(template["content"])

    return render_template(
        "use_template.html",
        template=template,
        variables=variables,
        config=config,
    )


@app.route("/template/<template_id>/edit")
def edit_template(template_id):
    """Page d'édition de template"""
    config = load_config()
    templates = load_templates()
    template = next((t for t in templates if t["id"] == template_id), None)

    if not template:
        return jsonify({"error": "Template non trouvé"}), 404

    return render_template("template_form.html", template=template, config=config)


# Routes API - Configuration
@app.route("/api/config", methods=["GET"])
def get_config_api():
    """API - Récupérer la configuration"""
    config = load_config()
    return jsonify({"config": config})


@app.route("/api/config", methods=["POST"])
def save_config_api():
    """API - Sauvegarder la configuration"""
    data = request.get_json()

    provider_id = data.get("provider")
    model_id = data.get("model")
    api_key = data.get("api_key", "").strip()

    if not provider_id:
        return jsonify({"error": "Provider obligatoire"}), 400

    config = load_config()

    # Sauvegarder la clé API si fournie
    if api_key:
        config["providers"][provider_id]["api_key"] = api_key
        save_config(config)

    # Sauvegarder le modèle si fourni (modifie la config globale)
    if model_id:
        config["selected_provider"] = provider_id
        config["selected_model"] = model_id
        save_config(config)

        return jsonify(
            {
                "success": True,
                "message": "Configuration sauvegardée avec succès.",
                "config": config,
            }
        )

    # Si seulement la clé API a été sauvegardée (sans modèle)
    if api_key and not model_id:
        return jsonify(
            {"success": True, "message": "Clé API sauvegardée.", "config": config}
        )


@app.route("/api/providers/<provider_id>/models", methods=["GET"])
def get_provider_models_api(provider_id):
    """API - Récupérer les modèles d'un provider"""
    config = load_config()
    provider = config["providers"].get(provider_id)

    if not provider:
        return jsonify({"error": "Provider non trouvé"}), 404

    models = provider.get("models", [])

    # Pour Z.AI, essayer de rafraîchir les modèles si une clé est configurée
    if provider_id == "zai" and provider.get("api_key"):
        updated_models, error = update_zai_models()
        if error:
            print(
                f"[ERROR] Erreur lors du rafraîchissement automatique des modèles Z.AI: {error}"
            )
            # Retourner les modèles en cache même s'il y a une erreur
        else:
            models = updated_models

    # Pour OpenRouter, essayer de rafraîchir les modèles si une clé est configurée
    if provider_id == "openrouter" and provider.get("api_key"):
        updated_models, error = update_openrouter_models()
        if error:
            print(
                f"[ERROR] Erreur lors du rafraîchissement automatique des modèles OpenRouter: {error}"
            )
            # Retourner les modèles en cache même s'il y a une erreur
        else:
            models = updated_models

    return jsonify({"models": models})


@app.route("/api/providers/<provider_id>/refresh", methods=["POST"])
def refresh_provider_models_api(provider_id):
    """API - Rafraîchir la liste des modèles d'un provider"""
    if provider_id == "zai":
        models, error = update_zai_models()
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"success": True, "models": models})
    elif provider_id == "openrouter":
        models, error = update_openrouter_models()
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"success": True, "models": models})
    else:
        return jsonify({"error": "Provider non trouvé"}), 404


# Routes API - Templates
@app.route("/api/templates", methods=["GET"])
def get_templates_api():
    """API - Récupérer tous les templates"""
    templates = load_templates()
    return jsonify({"templates": templates})


@app.route("/api/templates", methods=["POST"])
def create_template_api():
    """API - Créer un nouveau template"""
    data = request.get_json()

    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    description = data.get("description", "").strip()

    if not name or not content:
        return jsonify({"error": "Le nom et le contenu sont obligatoires"}), 400

    # Extraire les variables
    variables = extract_variables(content)

    # Créer le template
    default_provider = data.get("default_provider", "zai")
    default_model = data.get("default_model", "glm-4.7")

    template = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "name": name,
        "description": description,
        "content": content,
        "variables": variables,
        "default_provider": default_provider,
        "default_model": default_model,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    # Sauvegarder
    templates = load_templates()
    templates.append(template)
    save_templates(templates)

    return jsonify({"success": True, "template": template})


@app.route("/api/templates/<template_id>", methods=["PUT"])
def update_template_api(template_id):
    """API - Mettre à jour un template"""
    data = request.get_json()

    templates = load_templates()
    template_index = next(
        (i for i, t in enumerate(templates) if t["id"] == template_id), None
    )

    if template_index is None:
        return jsonify({"error": "Template non trouvé"}), 404

    # Mettre à jour le template
    template = templates[template_index]
    template["name"] = data.get("name", template["name"]).strip()
    template["description"] = data.get("description", template["description"]).strip()
    template["content"] = data.get("content", template["content"]).strip()
    template["variables"] = extract_variables(template["content"])

    # Mettre à jour default_provider et default_model si fournis
    if "default_provider" in data:
        template["default_provider"] = data["default_provider"]
    if "default_model" in data:
        template["default_model"] = data["default_model"]

    template["updated_at"] = datetime.now().isoformat()

    # Sauvegarder
    save_templates(templates)

    return jsonify({"success": True, "template": template})


@app.route("/api/templates/<template_id>", methods=["DELETE"])
def delete_template_api(template_id):
    """API - Supprimer un template"""
    templates = load_templates()
    templates = [t for t in templates if t["id"] != template_id]
    save_templates(templates)

    return jsonify({"success": True, "message": "Template supprimé"})


# Routes API - Génération
@app.route("/api/generate", methods=["POST"])
def generate_api():
    """API - Générer un résultat à partir d'un template"""
    data = request.get_json()

    template_id = data.get("template_id")
    variables = data.get("variables", {})
    provider_id = data.get("provider")
    model_id = data.get("model")

    if not template_id:
        return jsonify({"error": "ID de template manquant"}), 400

    # Utiliser le provider et modèle sélectionnés si non fournis
    if not provider_id or not model_id:
        config = load_config()
        provider_id = config.get("selected_provider", "zai")
        model_id = config.get("selected_model", "glm-4.7")

    # Charger le template
    templates = load_templates()
    template = next((t for t in templates if t["id"] == template_id), None)

    if not template:
        return jsonify({"error": "Template non trouvé"}), 404

    # Déterminer le provider et le modèle à utiliser
    # Priorité: paramètres utilisateur > défauts template > config globale
    if not provider_id or not model_id:
        # Utiliser les défauts du template s'ils existent
        if "default_provider" in template and "default_model" in template:
            provider_id = template["default_provider"]
            model_id = template["default_model"]
        else:
            # Utiliser la configuration globale
            config = load_config()
            provider_id = config.get("selected_provider", "zai")
            model_id = config.get("selected_model", "glm-4.7")

    # Remplacer les variables dans le template
    try:
        prompt = template["content"].format(**variables)
    except KeyError as e:
        return jsonify({"error": f"Variable manquante: {e}"}), 400

    # Appeler l'API du provider
    result, error = call_llm_api(prompt, provider_id, model_id)

    if error:
        return jsonify({"error": error}), 500

    # Sauvegarder dans l'historique
    history = load_history()
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "template_id": template_id,
        "template_name": template["name"],
        "variables": variables,
        "provider": provider_id,
        "model": model_id,
        "result": result,
        "timestamp": datetime.now().isoformat(),
    }
    history.insert(0, entry)  # Ajouter au début
    history = history[:50]  # Garder seulement les 50 derniers
    save_history(history)

    return jsonify({"success": True, "result": result, "entry_id": entry["id"]})


# Routes API - Historique
@app.route("/api/history", methods=["GET"])
def get_history_api():
    """API - Récupérer l'historique"""
    history = load_history()
    return jsonify({"history": history})


@app.route("/api/history/<entry_id>", methods=["DELETE"])
def delete_history_entry_api(entry_id):
    """API - Supprimer une entrée de l'historique"""
    history = load_history()
    history = [h for h in history if h["id"] != entry_id]
    save_history(history)

    return jsonify({"success": True, "message": "Entrée supprimée"})


@app.route("/api/export/<entry_id>")
def export_entry(entry_id):
    """API - Exporter une entrée en fichier markdown"""
    history = load_history()
    entry = next((h for h in history if h["id"] == entry_id), None)

    if not entry:
        return jsonify({"error": "Entrée non trouvée"}), 404

    # Créer le fichier markdown
    filename = f"output_{entry_id}.md"
    export_dir = "exports"
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)

    filepath = os.path.join(export_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(entry["result"])

    return send_from_directory(export_dir, filename, as_attachment=True)




@app.route("/api/config/save-defaults", methods=["POST"])
def save_defaults_api():
    """API - Sauvegarder les defaults sans clé API"""
    data = request.get_json()
    
    provider_id = data.get("provider")
    model_id = data.get("model")
    
    if not provider_id or not model_id:
        return jsonify({"error": "Provider et modèle obligatoires"}), 400
    
    config = load_config()
    
    # Sauvegarder les defaults dans config.json
    config["selected_provider"] = provider_id
    config["selected_model"] = model_id
    save_config(config)
    
    return jsonify({
        "success": True,
        "message": "Defaults sauvegardés avec succès.",
        "config": config
    })



if __name__ == "__main__":
    # Créer le répertoire d'exports s'il n'existe pas
    if not os.path.exists("exports"):
        os.makedirs("exports")

    # Lancer l'application
    app.run(host="0.0.0.0", port=5000, debug=True)
