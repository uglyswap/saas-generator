# 🚀 Guide de Démarrage Rapide

## 📌 Comment démarrer l'application

### Option 1 : Double-cliquez sur `start.bat` (Windows)

1. Allez dans le dossier du projet
2. Double-cliquez sur le fichier `start.bat`
3. Attendez que l'application démarre
4. Ouvrez votre navigateur sur : **http://localhost:5000**

### Option 2 : Via la ligne de commande

```bash
cd saas-generator
python -m venv venv
venv\Scripts\activate          # Windows (Linux/Mac : source venv/bin/activate)
pip install -r requirements.txt
python run.py
```

Puis ouvrez : **http://localhost:5000**

### Option 3 : Docker

```bash
echo SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") > .env
docker-compose up -d
```

---

## 👤 Premier lancement

Au premier démarrage, l'application vous demande de **créer un compte administrateur**
(page `/auth/setup`). Choisissez un mot de passe fort (8+ caractères, majuscule,
minuscule, chiffre).

---

## 🔑 Configuration des providers LLM

1. Sur la page d'accueil, ouvrez **Configuration**
2. **Étape 1 - Clés API** : entrez la clé de chaque provider que vous utilisez
   - Z.AI Coding Plan
   - OpenRouter
   - Alibaba Cloud Coding Plan (clé `sk-sp-...`)
   - OpenCode Go (clé OpenCode Zen)
3. **Étape 2 - Provider & Modèle par défaut** : choisissez votre couple par défaut
   (ex. Alibaba + `qwen3.7-plus`), puis **Sauvegarder**

Ce **défaut général** s'applique à tous vos templates, sauf si un template
définit explicitement son propre provider/modèle dans son formulaire.

---

## 📝 Comment utiliser l'application

1. **Créez un template** avec des variables : `Rédige un brief pour {entreprise} sur {sujet}`
2. **Utilisez le template** : remplissez les variables
3. **Générez** (streaming temps réel ou mode synchrone)
4. **Exportez** en Markdown, HTML, PDF ou Word
5. **Consultez l'historique** pour retrouver, éditer et versionner vos générations

---

## ⚠️ Erreurs fréquentes

| Erreur | Solution |
|--------|----------|
| "Cle API invalide ou expiree" | Vérifiez votre clé dans Configuration > Étape 1 |
| "Trop de requêtes" | Attendez 1-2 minutes (quota du provider atteint) |
| "Erreur serveur du provider" | Le provider est temporairement indisponible, réessayez |
| "Aucun provider configure" | Définissez votre provider/modèle par défaut (Étape 2) |
| L'app refuse de démarrer en production | Définissez la variable d'environnement `SECRET_KEY` |

**Guide complet de dépannage** : voir `TROUBLESHOOTING.md` s'il est présent, et le fichier `app.log`.

---

## 📂 Fichiers importants

| Fichier | Utilité |
|---------|---------|
| `start.bat` | Script de démarrage Windows |
| `run.py` | Point d'entrée de l'application |
| `config.py` | Configuration (providers, environnements) |
| `.env` | Variables d'environnement (SECRET_KEY, ENCRYPTION_KEY...) |
| `app.log` | Logs applicatifs |
| `README.md` | Documentation complète |

---

**Bon développement ! 🚀**
