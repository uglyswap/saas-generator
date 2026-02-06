# 🚀 Guide de Démarrage Rapide

## 📌 Comment démarrer l'application

### Option 1 : Double-cliquez sur `start.bat` (RECOMMANDÉ)

1. Allez dans le dossier : `C:\Users\quent\saas-generator`
2. Double-cliquez sur le fichier `start.bat`
3. Attendez que l'application démarre
4. Ouvrez votre navigateur sur : **http://localhost:5000**

### Option 2 : Via la ligne de commande

```bash
cd C:\Users\quent\saas-generator
python app.py
```

Puis ouvrez : **http://localhost:5000**

---

## ⚠️ Erreur de connexion ? Lisez ceci

### Problème le plus courant : Timeout de l'API Z.AI

**Message** : "Erreur de connexion au serveur" ou "Délai d'attente dépassé"

**Solution** : C'est normal ! L'API Z.AI prend parfois du temps à répondre.
- **Réessayez simplement** en cliquant à nouveau sur "Générer"
- Vérifiez votre connexion internet
- Attendez quelques secondes entre deux essais

### Autres erreurs fréquentes

| Erreur | Solution |
|--------|----------|
| "Erreur d'authentification" | Vérifiez votre clé API (⚙️ Configuration API) |
| "Trop de requêtes" | Attendez 1-2 minutes avant de réessayer |
| "Erreur serveur Z.AI" | Attendez quelques minutes, le serveur est temporairement indisponible |

**Guide complet de dépannage** : Voir le fichier `TROUBLESHOOTING.md`

---

## 📝 Comment utiliser l'application

1. **Entrez votre idée de SaaS** dans le formulaire
   - Exemple : "Une plateforme de gestion de tâches pour équipes distantes"

2. **Cliquez sur "Générer le cahier des charges"**
   - Attendez 10-30 secondes (parfois plus si l'API est lente)

3. **Lisez le résultat** qui s'affiche automatiquement

4. **Exportez en Markdown** si nécessaire
   - Cliquez sur "📥 Exporter en Markdown"

5. **Consultez l'historique** pour voir vos générations précédentes

---

## 🔑 Configuration de la clé API

Une clé API par défaut est déjà configurée, mais vous pouvez la changer :

1. Cliquez sur "⚙️ Configuration API"
2. Entrez votre clé API Z.AI
3. Cliquez sur "Sauvegarder"

---

## 📂 Fichiers importants

| Fichier | Utilité |
|---------|---------|
| `start.bat` | Script de démarrage facile (double-cliquez) |
| `app.py` | Application principale |
| `TROUBLESHOOTING.md` | Guide de résolution des problèmes |
| `README.md` | Documentation complète |
| `history.json` | Historique de vos générations |
| `exports/` | Dossier des fichiers exportés |

---

## 💡 Astuces

- **Si l'application ne démarre pas** : Vérifiez que Python est installé (`python --version`)
- **Si vous voyez une erreur** : Consultez le fichier `flask.log` pour les détails
- **Pour arrêter l'application** : Appuyez sur `Ctrl+C` dans la console
- **Les cahiers des charges sont sauvegardés** automatiquement dans l'historique

---

## 🆘 Besoin d'aide ?

1. **Consultez le guide de dépannage** : `TROUBLESHOOTING.md`
2. **Vérifiez les logs** : Ouvrez le fichier `flask.log`
3. **Testez votre connexion** : https://www.speedtest.net
4. **Vérifiez Z.AI** : https://docs.z.ai

---

**Bon développement SaaS ! 🚀**
