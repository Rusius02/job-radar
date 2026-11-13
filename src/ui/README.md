# Interface et base locale Job Radar

Lancer depuis la racine du projet :

```powershell
python -m src.ui.server
```

Puis ouvrir <http://127.0.0.1:8000>. Le serveur écoute uniquement sur `127.0.0.1`. La base SQLite est créée automatiquement dans `data/job_radar.sqlite3`. Les fichiers SQLite locaux sont ignorés par Git.

## Données persistées

`src/storage/database.py` initialise le schéma SQLite (versionné avec `PRAGMA user_version`) et expose `JobRadarDatabase`. Les opérations d’écriture sont transactionnelles.

- `profiles` contient les informations principales d’un profil local unique, et `profile_preferences` ses critères, salaires souhaités et types de contrat.
- `app_metadata` mémorise les migrations ponctuelles de données locales.
- `job_sites` conserve la liste des sites à suivre, leur URL, leur activation et la confirmation de revue des règles. Cette confirmation n’est pas une autorisation juridique.
- `profile_skills`, `experiences`, `educations`, `certifications`, `profile_languages`, `profile_links` et `projects` stockent ses éléments structurés.
- `offers` contient les annonces et leur état de suivi (`new`, `saved`, `applied`, `dismissed`). `offer_locations`, `offer_skills` et `offer_employment_types` portent leurs attributs multiples.
- `offer_matches` conserve le score et les raisons de correspondance entre le profil et l’offre.

L’offre est dédupliquée avec son URL source. `first_seen_at` conserve la première collecte, `last_seen_at` la dernière vérification. La page d’accueil affiche les cinq offres les plus récemment découvertes.

## API locale

- `GET /api/offers` : cinq offres récentes.
- `POST /api/offers` : enregistre ou met à jour une offre et ses attributs. En cas de score, fournir `score` (0–100) et éventuellement `reasons`.
- `GET /api/profile` : retourne le profil complet.
- `PUT /api/profile` : remplace les champs/listes du profil transmis dans une transaction. Omettre une collection revient à l’effacer ; inclure les collections à conserver.
- `GET /api/sites` : liste les sites enregistrés.
- `POST /api/sites` : ajoute un site (`name`, `url`, `terms_reviewed` facultatif, `is_enabled` facultatif). Les URL sont limitées à HTTP(S), sans identifiants intégrés.
- `PATCH /api/sites/{id}` : active ou met en pause un site (`is_enabled`).
- `DELETE /api/sites/{id}` : retire le site.

Le formulaire actuel met à jour les critères de recherche et les compétences via ces routes. Le dépôt SQLite prend également en charge les coordonnées, résumé, expériences, formations, certifications, langues et liens via `save_profile`.

Au premier démarrage, les offres de l’ancien `data/offers.json` sont importées sans créer de doublons. Ce fichier n’est ensuite plus utilisé comme stockage principal.

La page Paramètres permet d’ajouter, suspendre et supprimer des sites. La liste est vide au départ et n’effectue aucune requête vers les domaines enregistrés. La collecte réelle reste à connecter explicitement au moteur et doit continuer à vérifier les règles d’accès et conditions applicables pour chaque site.

## Exemple de profil

```json
{
  "first_name": "Ada",
  "last_name": "Lovelace",
  "headline": "Data engineer",
  "email": "ada@example.com",
  "location": "Paris",
  "preferences": {
    "remote_only": true,
    "salary_min": 60000,
    "salary_currency": "EUR",
    "desired_titles": ["Data engineer"],
    "desired_locations": ["Paris"],
    "keywords": ["Python"],
    "employment_types": ["FULL_TIME"]
  },
  "skills": [{"name": "Python", "proficiency": "Expert", "years_experience": 8}],
  "experiences": [{
    "title": "Senior engineer",
    "company": "Example",
    "start_date": "2020-01-01",
    "is_current": true
  }],
  "education": [{"institution": "University", "degree": "MSc"}],
  "certifications": [{"name": "Cloud architect", "issuer": "Cloud Corp"}],
  "languages": [{"language": "French", "proficiency": "Native"}],
  "links": [{"label": "Portfolio", "url": "https://example.com"}],
  "projects": [{
    "name": "Job Radar",
    "role": "Creator",
    "description": "Built a job matching tool.",
    "skills": ["Python", "SQLite"]
  }]
}
```
