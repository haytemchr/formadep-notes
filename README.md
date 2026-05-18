# 🎓 Formadep Notes, le vérificateur de notes (Windows)

Une petite application Windows légère qui surveille ton ENT Formadep360 et te prévient dès qu'une nouvelle note apparaît. Simple, locale et pensée pour rester discrète.

**Principales fonctionnalités**
- **Surveillance périodique** : vérifie automatiquement toutes les X minutes.
- **Notifications Windows** : notification + son quand une nouvelle note arrive.
- **Minimisation en zone de notification** (systray).
- **Option de démarrage automatique** au lancement de Windows.

## 🚀 Installation rapide

1. Installe Python 3.11+ depuis https://python.org (cochez "Add Python to PATH").
2. Ouvre un terminal dans ce dossier.
3. Installe les dépendances :

```powershell
pip install -r requirements.txt

```

4. Lance l'application :

```powershell
python app.py

```

## 💻 Utilisation

* Renseigne ton **email ENT** et ton **mot de passe**.
* Choisis l'intervalle de vérification (1–30 minutes).
* (Optionnel) Coche **Se souvenir du mot de passe** pour stocker le mot de passe de façon sécurisée.
* Clique sur **Démarrer**. Tu peux ensuite masquer l'app : elle restera active dans la zone de notification.

## 🔒 Sécurité & confidentialité

* Par défaut, le mot de passe **n'est pas** enregistré en clair dans le fichier de configuration.
* Si tu actives **Se souvenir du mot de passe**, l'application utilisera `keyring` pour stocker le mot de passe dans le gestionnaire de mots de passe du système (Windows Credential Manager) au lieu d'écrire le mot de passe dans `~/.formadep_config.json`.
* Les seules requêtes sont celles nécessaires pour se connecter à ton ENT ; rien n'est envoyé à des services tiers par l'application.

## ⚙️ Fichier de configuration

* Le fichier de configuration est situé dans :
* Windows : `%USERPROFILE%\.formadep_config.json`


* Par défaut il contient des préférences (email, intervalle, autostart, save_password). Le mot de passe n'est **pas** stocké en clair.

## 🤝 Contribuer / Remarques

* Problème, idée d'amélioration ou bug ? Ouvre une issue ou propose une PR.
* Si tu veux que j'ajoute un installeur Windows (.exe), dis-le-moi et je m'en occupe.

## 📝 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 👨‍💻 Auteur

Créé par **Haytem CHRYAT**.
N'hésitez pas à laisser une ⭐ sur le repo si le projet vous plaît !



Merci d'utiliser Formadep Notes, conçu pour t'éviter de surveiller manuellement ton ENT.
