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
- `api_integrations` conserve les endpoints API, la méthode HTTP, les paramètres, les en-têtes et le corps JSON configurés. Les valeurs d’en-têtes ne sont pas renvoyées par l’API locale, mais restent stockées sans chiffrement dans SQLite : ne saisissez pas de secret sensible dans cette version.
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
- `GET /api/integrations` : liste les configurations API sans exposer la valeur des en-têtes.
- `POST /api/integrations` et `PUT /api/integrations/{id}` : enregistrent un endpoint (`name`, `url`, `method` GET/POST, `query_params`, `headers`, `body`, `is_enabled`).
- `PATCH /api/integrations/{id}` : active ou met en pause une configuration.
- `DELETE /api/integrations/{id}` : retire une configuration.

Le formulaire actuel met à jour les critères de recherche et les compétences via ces routes. Le dépôt SQLite prend également en charge les coordonnées, résumé, expériences, formations, certifications, langues et liens via `save_profile`.

Au premier démarrage, les offres de l’ancien `data/offers.json` sont importées sans créer de doublons. Ce fichier n’est ensuite plus utilisé comme stockage principal.

La page Paramètres permet d’ajouter, suspendre et supprimer des sites. Elle n’effectue aucune requête vers les domaines enregistrés. La collecte réelle reste à connecter explicitement au moteur et doit continuer à vérifier les règles d’accès et conditions applicables pour chaque site.

La page Paramètres permet aussi de définir les réglages de requête pour des APIs JSON : endpoint, méthode GET/POST, paramètres, en-têtes et corps JSON (POST). Les valeurs d’en-têtes ne sont pas incluses dans les réponses API locales, mais leur stockage SQLite n’est pas chiffré. À ce stade, ces réglages sont uniquement enregistrés : le bouton de collecte n’appelle pas ces APIs, car il faut encore un connecteur spécifique pour chaque format de réponse afin de convertir ses résultats en offres. L’activation d’une API ne déclenche donc aucun trafic réseau.

Le bouton « Récupérer les offres » lance une collecte manuelle des seuls sites activés et dont les règles ont été marquées comme consultées. Il vérifie `robots.txt` via le scraper avant chaque page, n’autorise pas les redirections, analyse les données structurées Schema.org `JobPosting` et enregistre les résultats dans SQLite. Les sites qui refusent l’accès, les erreurs et les pages sans données structurées sont signalés ; les sites non vérifiés sont ignorés. Un profil vide autorise la collecte mais ne produit pas de scores de pertinence.

Au premier démarrage après cette version, une liste de sites d’emploi connus est ajoutée en pause (sans doublonner les domaines déjà présents) : France Travail, Apec, Indeed, HelloWork, Welcome to the Jungle, LinkedIn Jobs, Cadremploi, Meteojob, Jobijoba et Glassdoor. Les sites ajoutés par l’utilisateur ne sont ni modifiés ni activés. Les suggestions restent de simples liens de veille : elles ne constituent pas une approbation juridique ou une vérification d’éligibilité au scraping.

## Périmètre belge

Lors du premier démarrage après cette version, les lieux recherchés sont initialisés à Bruxelles, Mons et Tournai uniquement si aucun lieu n’était déjà renseigné. Une préférence existante est conservée. Ces lieux contribuent au score de pertinence des annonces ; ils ne filtrent pas les pages de recherche des sites.

La collecte ne prend actuellement en charge que les annonces Schema.org `JobPosting` présentes dans le HTML reçu. L’inspection des sources belges a montré que la page de résultats du Forem est interdite aux robots par son `robots.txt` et que l’API de recherche VDAB se trouve sous un chemin également interdit. La page VDAB accessible ne fournit pas les annonces en HTML statique. Aucune page publique d’offres Actiris exploitable n’a été confirmée pendant cette vérification. Ces limites ne doivent pas être contournées : tant qu’une source belge ne propose pas une page ou un flux autorisé avec des annonces structurées, la collecte peut légitimement retourner zéro résultat. Un connecteur ne sera ajouté qu’après confirmation de son accès et de ses règles.

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
    "desired_locations": ["Bruxelles", "Mons", "Tournai"],
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
