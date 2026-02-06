# 🚀 Générateur de Cahier des Charges SaaS

Application Flask qui transforme vos idées de SaaS en cahiers des charges complets et professionnels grâce à l'API Z.AI GLM 4.7.

## ✨ Fonctionnalités

- 🎯 **Génération automatique** de cahiers des charges complets à partir d'une simple idée
- 📝 **Template SaaS spécialisé** créé par des experts Product Manager et Architecte Logiciel
- 📥 **Export Markdown** pour une intégration facile dans vos workflows
- 📚 **Historique local** de toutes vos générations
- ⚙️ **Configuration API flexible** via l'interface web
- 🎨 **Interface moderne et responsive**
- 🖥️ **Exécutable standalone** grâce à PyInstaller

## 📋 Prérequis

- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)

## 🚀 Installation

### Option 1: Utiliser l'exécutable (Recommandé)

1. Téléchargez l'exécutable `SaaSGenerator.exe`
2. Double-cliquez pour lancer l'application
3. Ouvrez votre navigateur sur `http://localhost:5000`

### Option 2: Installation depuis le code source

1. Clonez ou téléchargez ce repository

```bash
cd saas-generator
```

2. Créez un environnement virtuel (recommandé)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

3. Installez les dépendances

```bash
pip install -r requirements.txt
```

4. (Optionnel) Configurez votre clé API

Créez un fichier `.env` à la racine du projet :

```bash
cp .env.example .env
```

Éditez `.env` et ajoutez votre clé API Z.AI :

```
ZAI_API_KEY=votre_clé_api_ici
```

5. Lancez l'application

```bash
python app.py
```

6. Ouvrez votre navigateur sur `http://localhost:5000`

## 📖 Utilisation

### 1. Configuration de la clé API

- Cliquez sur "⚙️ Configuration API"
- Entrez votre clé API Z.AI
- Cliquez sur "Sauvegarder"

> **Note** : Une clé API par défaut est fournie, mais il est recommandé d'utiliser votre propre clé pour une meilleure sécurité.

### 2. Générer un cahier des charges

1. Dans le formulaire, entrez votre idée de SaaS
2. Exemple : *"Une plateforme de gestion de projets pour équipes marketing avec intégration Slack et Notion"*
3. Cliquez sur "Générer le cahier des charges"
4. Attendez quelques secondes (la génération peut prendre 10-30 secondes)
5. Le résultat s'affiche automatiquement

### 3. Exporter le résultat

- Cliquez sur "📥 Exporter en Markdown" pour télécharger le fichier
- Le fichier est sauvegardé dans le dossier `exports/`

### 4. Gérer l'historique

- **Voir** : Cliquez sur "👁️ Voir" pour afficher une génération précédente
- **Exporter** : Cliquez sur "📥 Exporter" pour télécharger une génération spécifique
- **Supprimer** : Cliquez sur "🗑️ Supprimer" pour retirer une entrée de l'historique

## 🏗️ Créer l'exécutable

Si vous souhaitez créer votre propre exécutable :

1. Installez PyInstaller

```bash
pip install pyinstaller
```

2. Générez l'exécutable

```bash
pyinstaller saas-generator.spec
```

3. L'exécutable sera créé dans le dossier `dist/`

## 📂 Structure du projet

```
saas-generator/
├── app.py                 # Application Flask principale
├── requirements.txt       # Dépendances Python
├── .env.example          # Exemple de configuration
├── saas-generator.spec   # Configuration PyInstaller
├── templates/
│   └── index.html        # Page principale
├── static/
│   ├── css/
│   │   └── style.css     # Styles CSS
│   └── js/
│       └── main.js       # JavaScript client
├── exports/              # Fichiers exportés (créé automatiquement)
├── history.json          # Historique local (créé automatiquement)
└── api_config.json       # Configuration API (créé automatiquement)
```

## 🔧 Dépannage

### L'application ne démarre pas

- Vérifiez que Python 3.8+ est installé : `python --version`
- Vérifiez que toutes les dépendances sont installées : `pip list`
- Essayez de réinstaller les dépendances : `pip install -r requirements.txt --force-reinstall`

### Erreur de connexion API

- Vérifiez que votre clé API est correcte
- Vérifiez votre connexion internet
- Consultez la documentation Z.AI : https://docs.z.ai/api-reference/llm/chat-completion

### L'historique ne s'affiche pas

- Vérifiez que le fichier `history.json` existe dans le dossier du projet
- Vérifiez les permissions d'écriture sur le dossier

### L'export ne fonctionne pas

- Vérifiez que le dossier `exports/` existe et a les permissions d'écriture
- Vérifiez que votre navigateur autorise les téléchargements

## 📝 Format du cahier des charges généré

Chaque cahier des charges inclut 9 sections complètes :

1. **Contexte marché & positionnement** - Problème, marché, USP, pricing
2. **Personas & parcours critiques** - Profils utilisateurs, flows UX
3. **Fonctionnalités MVP (MoSCoW)** - Features prioritaires avec user stories
4. **Architecture données & multi-tenant** - ERD, relations, RLS
5. **API contracts & intégrations** - Endpoints, webhooks, intégrations
6. **Stack technique adaptée** - Frontend, backend, auth, deploy
7. **Non-fonctionnels (SLA)** - Performance, scale, uptime, security
8. **Roadmap & métriques succès** - MVP, KPIs, objectifs
9. **Risques & go/live checklist** - Mitigations, checklist de lancement

## 🔐 Sécurité

- La clé API est sauvegardée localement dans `api_config.json`
- N'ajoutez jamais `api_config.json` ou `.env` à un repository public
- Utilisez toujours votre propre clé API en production

## 🤝 Contribution

Ce projet est open-source. Les contributions sont les bienvenues !

## 📄 Licence

MIT License

## 🙏 Remerciements

- Propulsé par [Z.AI GLM 4.7](https://docs.z.ai/)
- Framework web : [Flask](https://flask.palletsprojects.com/)
- Création d'exécutable : [PyInstaller](https://www.pyinstaller.org/)

## 📞 Support

Pour toute question ou problème :
- Consultez la section Dépannage
- Ouvrez une issue sur GitHub
- Contactez l'équipe de support

---

**Bon développement SaaS ! 🚀**
