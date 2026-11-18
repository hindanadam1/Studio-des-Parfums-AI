# Studio des Parfums AI

Outil local de veille concurrentielle et de suivi de la visibilité de Studio des Parfums dans les réponses de Groq.

## Fonctionnement

- Les scripts recherchent et analysent les concurrents, mesurent la visibilité dans les réponses de Groq, comparent les exécutions et génèrent des recommandations.
- Le tableau de bord Streamlit affiche les résultats déjà enregistrés. Il est en lecture seule et ne lance pas la veille.
- La veille se lance manuellement depuis le terminal ou chaque semaine avec `run_weekly.bat`.
- Les exécutions incomplètes dues aux limites d’API sont conservées dans l’historique. Le tableau de bord met en avant la dernière mesure complète quand elle existe.

## Contenu du projet

```text
studio-parfums-ai/
├── assets/
│   └── logo_parfum.png
├── config/
│   └── visibility_questions.json
├── data/
│   └── .gitkeep
├── scripts/
│   ├── research.py
│   ├── analyze.py
│   ├── visibility.py
│   ├── compare.py
│   └── recommendations.py
├── dashboard.py
├── requirements.txt
└── run_weekly.bat
```

Les fichiers JSON de résultats sont créés dans `data/`. Ils restent sur votre ordinateur et sont ignorés par Git pour ne pas publier l’historique. Le tableau de bord d’un nouveau clone affichera les données disponibles après une première veille.

## Installation sous Windows

Dans PowerShell, à la racine du projet :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Configuration de Groq

Créer ou compléter le fichier `.env` à la racine avec votre clé API :

```text
GROQ_API_KEY=votre_cle_groq
```

Ne publiez jamais `.env` ni votre clé API. `.env` et `.venv/` restent locaux et sont ignorés par Git.

## Lancer le tableau de bord

Avec l’environnement virtuel activé :

```powershell
streamlit run dashboard.py
```

Le navigateur s’ouvre sur le tableau de bord. Pour obtenir de nouveaux résultats, lancez d’abord la veille depuis le terminal.

## Lancer la veille

Depuis PowerShell, à la racine du projet :

```powershell
.\run_weekly.bat
```

Le fichier lance les cinq scripts dans l’ordre avec l’environnement `.venv` du projet. Pour les lancer un par un :

```powershell
python scripts\research.py
python scripts\analyze.py
python scripts\visibility.py
python scripts\compare.py
python scripts\recommendations.py
```

La veille contacte des services externes de recherche web et l’API Groq. Les limites de requêtes peuvent produire une exécution partielle.

## Automatisation hebdomadaire

Dans le Planificateur de tâches Windows, choisir `run_weekly.bat` comme programme à exécuter. Le script se place dans le dossier du projet et lance les étapes dans le bon ordre.

## Résultats enregistrés

- `visibility_history.json` : réponses, questions, mentions et taux de visibilité Groq.
- `comparisons.json` : comparaison des exécutions.
- `alerts.json` : alertes de baisse de visibilité.
- `competitors.json` et `competitors_analysis.json` : concurrents identifiés et analyses.
- `history.json` : historique des analyses concurrentielles.
- `recommendations.json` : diagnostic et recommandations.

Tous ces fichiers restent dans `data/` en local. Le fichier `data/.gitkeep` permet de conserver le dossier dans GitHub sans publier les résultats.
