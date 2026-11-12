# Interface Job Radar

Lancer depuis la racine du projet :

```powershell
python -m src.ui.server
```

Puis ouvrir <http://127.0.0.1:8000>. Le serveur reste local à la machine. La page d’accueil affiche au maximum les cinq offres les plus récemment trouvées ; le lien d’une carte ouvre `application_url`, ou `url` si ce champ est absent.

Les offres sont lues dans `data/offers.json`, un tableau d’objets JSON. Exemple :

```json
[
  {
    "title": "Développeur Python",
    "organization": "Exemple SAS",
    "locations": ["Paris"],
    "date_found": "2026-11-12T10:30:00+01:00",
    "date_posted": "2026-11-10",
    "application_url": "https://example.com/jobs/python",
    "score": 85,
    "employment_type": ["FULL_TIME"],
    "is_remote": true
  }
]
```

Le tri utilise `date_found`, puis `date_posted` en repli. La date de publication ne représente pas nécessairement la date de collecte. Le profil de recherche se modifie depuis le bouton en haut à droite et reste enregistré dans le stockage local du navigateur ; il n’est pas envoyé au serveur.

Pour le moment, l’interface lit le fichier JSON, mais le collecteur et l’analyseur ne sauvegardent pas encore automatiquement leurs résultats dans ce fichier.
