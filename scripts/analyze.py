
import os
import json
import requests

from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from bs4 import BeautifulSoup


# ==========================================
# 1. CONFIGURATION
# ==========================================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

load_dotenv(ROOT_DIR / ".env")

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("La clé GROQ_API_KEY est introuvable dans .env")

client = Groq(api_key=api_key)

MODEL = "openai/gpt-oss-20b"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ==========================================
# 2. CHARGER LES CONCURRENTS
# ==========================================

def load_competitors():

    with (DATA_DIR / "competitors.json").open("r", encoding="utf-8") as file:
        data = json.load(file)

    return data["competitors"]


# ==========================================
# 3. RECUPERER LE CONTENU D'UN SITE
# ==========================================

def get_website_content(url):

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Supprimer les éléments inutiles
        for element in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "noscript"
        ]):
            element.decompose()

        text = soup.get_text(separator=" ", strip=True)

        # Limiter la taille du contenu envoyé à l'IA
        return text[:6000]

    except requests.RequestException as error:
        print(f"Impossible de récupérer {url} : {error}")
        return ""


# ==========================================
# 4. VALIDER LA REPONSE DE L'IA
# ==========================================

def validate_analysis(analysis, valid_urls):

    if not isinstance(analysis, dict):
        raise ValueError("La réponse JSON doit être un objet.")

    for category in ["strengths", "weaknesses"]:

        items = analysis.get(category)

        if not isinstance(items, list) or len(items) != 2:
            raise ValueError(
                f"Il faut exactement 2 éléments dans {category}."
            )

        for item in items:

            if not isinstance(item, dict):
                raise ValueError(
                    f"Un élément de {category} est invalide."
                )

            observation = item.get("observation")
            source_url = item.get("source_url")

            if not isinstance(observation, str) or not observation.strip():
                raise ValueError(
                    f"Observation manquante dans {category}."
                )

            if source_url not in valid_urls:
                raise ValueError(
                    f"URL non vérifiée dans {category}."
                )

    return True


# ==========================================
# 5. ANALYSER LE CONCURRENT AVEC GROQ
# ==========================================

def analyze_competitor(competitor):

    print(f"\nAnalyse de : {competitor['name']}")

    website_contents = []
    valid_urls = []

    # Récupérer les pages du concurrent
    for url in competitor.get("sources", []):

        content = get_website_content(url)

        if content:
            website_contents.append(
                f"URL : {url}\nCONTENU : {content}"
            )
            valid_urls.append(url)

    if not website_contents:
        print("Aucune page accessible. Analyse ignorée.")
        return None

    # Préparer les informations pour Groq
    website_text = "\n\n".join(website_contents)

    prompt = f"""
Tu es un expert en marketing digital et en analyse concurrentielle.

Analyse le concurrent suivant pour Studio des Parfums.

Nom du concurrent : {competitor['name']}
Domaine : {competitor['domain']}
Catégorie : {competitor['category']}

Voici le contenu réellement récupéré sur son site :

{website_text}

Ta mission :
- Identifier exactement 2 points forts.
- Identifier exactement 2 points faibles.
- Justifier chaque observation avec le contenu fourni.
- Associer chaque observation à une URL parmi les sources fournies.
- Ne jamais inventer une information ou une URL.
- Un élément non visible sur le site ne constitue pas automatiquement
  un point faible.
- Si une information est insuffisante, indique-le clairement.

Réponds uniquement avec un JSON valide ayant cette structure :

{{
    "strengths": [
        {{
            "observation": "Description du point fort",
            "source_url": "URL exacte"
        }},
        {{
            "observation": "Description du point fort",
            "source_url": "URL exacte"
        }}
    ],
    "weaknesses": [
        {{
            "observation": "Description du point faible",
            "source_url": "URL exacte"
        }},
        {{
            "observation": "Description du point faible",
            "source_url": "URL exacte"
        }}
    ]
}}

Les source_url doivent obligatoirement appartenir à cette liste :
{json.dumps(valid_urls, ensure_ascii=False)}
"""

    # Deux tentatives maximum
    for attempt in range(2):

        try:

            current_prompt = prompt

            if attempt == 1:

                current_prompt += """

ATTENTION : ta réponse précédente ne respectait pas le format demandé.

Corrige ta réponse en respectant impérativement les règles suivantes :

- Exactement 2 éléments dans strengths.
- Exactement 2 éléments dans weaknesses.
- Chaque élément doit contenir observation et source_url.
- Chaque source_url doit appartenir à la liste autorisée.
- Ne retourne aucun texte en dehors du JSON.
- Ne crée pas de faits non vérifiables.
"""

                print("Nouvelle tentative de correction du JSON...")

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": current_prompt
                    }
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=1500
            )

            result_text = response.choices[0].message.content

            if not result_text:
                raise ValueError("La réponse de l'IA est vide.")

            analysis = json.loads(result_text)

            # Vérifier la structure et les URLs
            validate_analysis(analysis, valid_urls)

            print("Analyse terminée avec succès !")

            return {
                "name": competitor["name"],
                "domain": competitor["domain"],
                "category": competitor["category"],
                "analysis": analysis,
                "sources": valid_urls,
                "analyzed_at": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                )
            }

        except Exception as error:

            print(
                f"Tentative {attempt + 1}/2 échouée "
                f"({type(error).__name__})."
            )

            if attempt == 1:
                print(
                    f"Analyse de {competitor['name']} abandonnée."
                )

    return None


# ==========================================
# 6. LANCER L'ANALYSE DE TOUS LES CONCURRENTS
# ==========================================

def run_analysis():

    competitors = load_competitors()

    results = []

    print("\n========== ANALYSE DES CONCURRENTS ==========")

    for competitor in competitors:

        result = analyze_competitor(competitor)

        if result:
            results.append(result)

            competitor["last_analyzed"] = result["analyzed_at"]

    # Enregistrer les dernières analyses
    with (DATA_DIR / "competitors_analysis.json").open(
        "w", encoding="utf-8"
    ) as file:

        json.dump(
            {"analyses": results},
            file,
            indent=4,
            ensure_ascii=False
        )

    # Mettre à jour competitors.json
    with (DATA_DIR / "competitors.json").open(
        "w", encoding="utf-8"
    ) as file:

        json.dump(
            {"competitors": competitors},
            file,
            indent=4,
            ensure_ascii=False
        )

    # Charger l'ancien historique
    try:

        with (DATA_DIR / "history.json").open("r", encoding="utf-8") as file:
            history_data = json.load(file)

        if not isinstance(history_data, dict):
            history_data = {"history": []}

        if not isinstance(history_data.get("history"), list):
            history_data["history"] = []

    except (FileNotFoundError, json.JSONDecodeError):

        history_data = {"history": []}

    # Ajouter les nouvelles analyses sans supprimer les anciennes
    if results:

        history_data["history"].append({
            "run_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "analyses": results
        })

    # Enregistrer l'historique
    with (DATA_DIR / "history.json").open("w", encoding="utf-8") as file:

        json.dump(
            history_data,
            file,
            indent=4,
            ensure_ascii=False
        )

    # Résultat final
    print("\n========== RESULTAT FINAL ==========")
    print(f"Concurrents trouvés : {len(competitors)}")
    print(f"Concurrents analysés : {len(results)}")
    print(f"Concurrents non analysés : {len(competitors) - len(results)}")

    print("\nFichier competitors_analysis.json enregistré !")
    print("Fichier competitors.json mis à jour !")
    print("Historique mis à jour !")


# ==========================================
# 7. EXECUTION
# ==========================================

if __name__ == "__main__":
    run_analysis()
