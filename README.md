# SaaS Generator

Application Flask pour generer du contenu avec des templates de prompts personnalises, propulsee par des modeles LLM (Z.AI Coding Plan, OpenRouter, Alibaba Cloud Coding Plan, OpenCode Go).

## Fonctionnalites

### Gestion des Templates
- Creation, modification et suppression de templates de prompts
- Variables dynamiques avec syntaxe `{variable_name}`
- Modele par defaut general (compte) avec override optionnel par template :
  un template sans choix explicite suit toujours le defaut general
- Generation automatique de contenu de template via IA (meta-prompt)

### Generation de Contenu
- Appels synchrones et en streaming (Server-Sent Events)
- Support multi-provider (Z.AI Coding Plan, OpenRouter, Alibaba Cloud Coding Plan, OpenCode Go)
- Routage automatique OpenAI-compatible / Anthropic-compatible selon le modele (OpenCode Go)
- Regeneration partielle de sections selectionnees
- Historique complet des generations avec pagination

### Versioning
- Sauvegarde automatique des versions a chaque modification
- Restauration d'une version precedente
- Historique des changements

### Export Multi-format
- Markdown (.md)
- HTML
- PDF
- DOCX (Word)
- Templates de branding personnalises (header, footer, couleurs)

### Securite
- Authentification utilisateur (inscription, connexion)
- Chiffrement AES (Fernet) des cles API
- Protection CSRF
- Validation des entrees (types JSON inclus)
- Rate limiting (login, inscription, generation)
- Refus de demarrer en production sans SECRET_KEY fort
- Sanitisation DOMPurify des sorties LLM rendues
- Cookies de session durcis (Secure, HttpOnly, SameSite)

### Interface
- Mode sombre / clair
- Interface responsive
- Rafraichissement dynamique des modeles disponibles

## Providers Supportes

| Provider | Endpoint | Modeles (juin 2026) |
|----------|----------|---------------------|
| Z.AI Coding Plan | `https://api.z.ai/api/coding/paas/v4/` | glm-4.5-air, glm-4.7, glm-5, glm-5-turbo, glm-5.1 |
| OpenRouter | `https://openrouter.ai/api/v1/` | Claude, GPT, Gemini, etc. (liste dynamique) |
| Alibaba Cloud Coding Plan | `https://coding-intl.dashscope.aliyuncs.com/v1/` | qwen3.7-plus, qwen3.6-plus, qwen3.5-plus, qwen3-max-2026-01-23, qwen3-coder-plus, qwen3-coder-next, glm-5, glm-4.7, kimi-k2.5, MiniMax-M2.5 |
| OpenCode Go | `https://opencode.ai/zen/go/v1/` | glm-5.1, glm-5, kimi-k2.5/k2.6, deepseek-v4-pro/flash, mimo-v2.x, minimax-m2.5/m2.7/m3, qwen3.5/3.6/3.7-plus, qwen3.7-max, hy3-preview |

Notes :
- Alibaba Coding Plan : pas d'endpoint `GET /models`, la liste est embarquee (IDs sensibles a la casse, ex. `MiniMax-M2.5`).
- OpenCode Go : les familles MiniMax et Qwen passent par l'endpoint Anthropic `/messages` (header `x-api-key`), les autres par `/chat/completions` (header `Authorization: Bearer`). Le routage est automatique.

## Installation

### Prerequis
- Python 3.11+
- pip

### Installation locale

```bash
# Cloner le repository
git clone https://github.com/votre-username/saas-generator.git
cd saas-generator

# Creer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Installer les dependances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env
# Editer .env avec vos valeurs

# Lancer l'application
python run.py
```

L'application sera accessible sur `http://localhost:5000`

### Docker

```bash
# Build
docker build -t saas-generator .

# Run avec SQLite
docker run -p 5000:5000 -e SECRET_KEY=votre-cle-secrete saas-generator

# Ou avec docker-compose (inclut PostgreSQL)
docker-compose up -d
```

## Configuration

### Variables d'environnement

| Variable | Description | Defaut |
|----------|-------------|--------|
| `SECRET_KEY` | Cle secrete Flask (OBLIGATOIRE en production : l'app refuse de demarrer avec la valeur par defaut) | `dev-change-me-in-production` |
| `DATABASE_URL` | URL de connexion BD | `sqlite:///saas_generator.db` |
| `FLASK_ENV` | Environnement | `production` |
| `ENCRYPTION_KEY` | Cle Fernet pour le chiffrement des cles API (derivee de SECRET_KEY si absente) | - |
| `SESSION_COOKIE_SECURE` | Cookies servis uniquement en HTTPS (production) | `true` |

### Fichier .env exemple

```env
SECRET_KEY=votre-cle-secrete-tres-longue
DATABASE_URL=postgresql://user:pass@localhost/saas_generator
FLASK_ENV=production
ENCRYPTION_KEY=0123456789abcdef0123456789abcdef
```

## Structure du Projet

```
saas-generator/
├── app/
│   ├── __init__.py          # Factory Flask
│   ├── api_v1.py            # Endpoints API REST
│   ├── auth.py              # Authentification
│   ├── models.py            # Modeles SQLAlchemy
│   ├── views.py             # Routes web
│   ├── services/
│   │   ├── llm_service.py   # Appels LLM (OpenAI + Anthropic compat)
│   │   ├── config_service.py # Resolution du defaut general provider/modele
│   │   ├── template_service.py
│   │   ├── history_service.py
│   │   └── export_service.py
│   └── utils/
│       ├── security.py      # Chiffrement, hash
│       └── validators.py    # Validation entrees
├── templates/               # Templates Jinja2
├── static/
│   ├── css/
│   └── js/
├── tests/                   # Tests pytest
├── config.py                # Configuration Flask
├── run.py                   # Point d'entree
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## API Endpoints

### Authentification
- `POST /auth/register` - Inscription
- `POST /auth/login` - Connexion
- `GET /auth/logout` - Deconnexion

### Configuration
- `GET /api/v1/config` - Configuration utilisateur
- `POST /api/v1/config` - Sauvegarder config provider
- `GET /api/v1/config/meta-prompt` - Config meta-prompt
- `POST /api/v1/config/meta-prompt` - Sauvegarder meta-prompt

### Templates
- `GET /api/v1/templates` - Lister templates
- `POST /api/v1/templates` - Creer template
- `PUT /api/v1/templates/<id>` - Modifier template
- `DELETE /api/v1/templates/<id>` - Supprimer template

### Generation
- `POST /api/v1/generate` - Generation synchrone
- `POST /api/v1/generate/stream` - Generation streaming (SSE)
- `POST /api/v1/generate/partial` - Regeneration partielle
- `POST /api/v1/generate/template-content` - Generer contenu template

### Historique
- `GET /api/v1/history` - Lister historique (pagine)
- `GET /api/v1/history/<id>` - Detail entree
- `PATCH /api/v1/history/<id>` - Modifier resultat
- `DELETE /api/v1/history/<id>` - Supprimer entree

### Versioning
- `GET /api/v1/history/<id>/versions` - Lister versions
- `GET /api/v1/history/<id>/versions/<num>` - Detail version
- `POST /api/v1/history/<id>/versions/<num>/restore` - Restaurer

### Export
- `GET /api/v1/export/<id>?format=md|html|pdf|docx` - Exporter
- `GET /api/v1/export-templates` - Lister templates branding
- `POST /api/v1/export-templates` - Creer template branding
- `PUT /api/v1/export-templates/<id>` - Modifier
- `DELETE /api/v1/export-templates/<id>` - Supprimer

### Providers
- `GET /api/v1/providers/<id>/models` - Modeles caches
- `POST /api/v1/providers/<id>/refresh` - Rafraichir modeles

## Tests

```bash
# Installer les dependances de test
pip install pytest pytest-flask

# Lancer les tests
pytest

# Avec couverture
pytest --cov=app
```

## Deploiement en Production

### Avec Gunicorn

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app('production')"
```

### Avec Docker Compose

```bash
# Configurer les variables
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env

# Lancer
docker-compose up -d
```

### Checklist Production

- [ ] Definir `SECRET_KEY` securise (l'app refuse de demarrer avec un placeholder connu)
- [ ] Utiliser PostgreSQL (pas SQLite)
- [ ] Configurer HTTPS (sinon mettre `SESSION_COOKIE_SECURE=false`, deconseille)
- [ ] Definir `ENCRYPTION_KEY` pour les cles API (attention : changer `SECRET_KEY` sans
      `ENCRYPTION_KEY` definie invalide les cles API stockees, a re-saisir dans l'UI)
- [ ] Derriere un reverse proxy : `TRUST_PROXY=true` (rate limiting par IP client reelle)
- [ ] En multi-workers : `RATELIMIT_STORAGE_URI=redis://...` pour des limites globales exactes
- [ ] Configurer les sauvegardes DB
- [ ] Limiter les logs sensibles

## Licence

MIT

## Contributions

Les contributions sont les bienvenues! Ouvrez une issue ou une pull request.
