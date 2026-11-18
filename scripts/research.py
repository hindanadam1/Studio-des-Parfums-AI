
from ddgs import DDGS
from urllib.parse import urlparse
from collections import Counter
import json
import time
from pathlib import Path

# 1. Mots-clés utilisés pour la recherche
ROOT_DIR = Path(__file__).resolve().parents[1]
COMPETITORS_FILE = ROOT_DIR / "data" / "competitors.json"

KEYWORDS = [
    "atelier création parfum Paris",
    "créer son propre parfum Paris",
    "atelier parfum personnalisé Paris",
    "expérience création parfum Paris",
    "coffret cadeau création parfum Paris"
]

# 2. Sites à exclure
EXCLUDED_DOMAINS = [
    "studiodesparfums-paris.fr",
    "generationvoyage.fr",
    "bing.com",
    "doubleclick.net",
    "viator.com",
    "getyourguide.com"
]

# 3. Sites connus
KNOWN_SITES = {
    "galimard.com": {
        "name": "Galimard",
        "category": "direct"
    },
    "musee-parfum-paris.fragonard.com": {
        "name": "Fragonard",
        "category": "direct"
    },
    "funbooker.com": {
        "name": "Funbooker",
        "category": "indirect"
    },
    "cinquiemesens.com": {
        "name": "Cinquième Sens",
        "category": "direct"
    }
}


# 4. Vérifier si un domaine est autorisé
def is_valid_domain(domain):
    for excluded in EXCLUDED_DOMAINS:
        if domain == excluded or domain.endswith("." + excluded):
            return False

    return True


# 5. Identifier le site
def classify_site(domain):
    if domain in KNOWN_SITES:
        return KNOWN_SITES[domain]

    return {
        "name": domain,
        "category": "to_verify"
    }


# 6. Effectuer les recherches
def find_competitors():

    print("\n=== VEILLE CONCURRENTIELLE ===")

    domain_counts = Counter()
    domain_data = {}
    errors = []

    for keyword in KEYWORDS:

        print(f"\nRecherche : {keyword}")

        try:
            with DDGS() as ddgs:
                results = list(
                    ddgs.text(
                        keyword,
                        region="fr-fr",
                        max_results=10
                    )
                )

            print(f"Résultats reçus : {len(results)}")

            for result in results:

                url = result.get("href", "")

                if not url.startswith(("http://", "https://")):
                    continue

                domain = urlparse(url).netloc.lower()
                domain = domain.removeprefix("www.")

                if not domain or not is_valid_domain(domain):
                    continue

                domain_counts[domain] += 1

                if domain not in domain_data:
                    domain_data[domain] = {
                        "title": result.get("title", ""),
                        "sources": []
                    }

                if url not in domain_data[domain]["sources"]:
                    domain_data[domain]["sources"].append(url)

        except Exception as error:
            print(f"Erreur : {error}")
            errors.append({
                "keyword": keyword,
                "error": str(error)
            })

        time.sleep(3)

    # 7. Construire uniquement les concurrents ayant des résultats
    competitors = []

    for domain, appearances in domain_counts.items():

        # Vérifier qu'il existe au moins une source valide
        sources = domain_data[domain]["sources"]

        if not sources:
            continue

        site_info = classify_site(domain)

        if site_info["category"] == "to_verify":
            relevance = "to_review"
        elif appearances >= 3:
            relevance = "high"
        elif appearances >= 2:
            relevance = "medium"
        else:
            relevance = "potential"

        competitors.append({
            "name": site_info["name"],
            "domain": domain,
            "category": site_info["category"],
            "appearances": appearances,
            "relevance": relevance,
            "sources": sources,
            "last_analyzed": None
        })

    # 8. Classer les concurrents
    competitors.sort(
        key=lambda item: (
            item["category"] != "direct",
            -item["appearances"]
        )
    )

    # 9. Garder les trois premiers concurrents
    top_competitors = competitors[:3]

    # 10. Préparer les données JSON
    output = {
        "competitors": top_competitors,
        "search_errors": errors
    }

    # 11. Enregistrer le fichier
    with COMPETITORS_FILE.open("w", encoding="utf-8") as file:
        json.dump(output, file, indent=4, ensure_ascii=False)

    # 12. Afficher les résultats
    print("\n=== TOP 3 DES CONCURRENTS ===")

    if not top_competitors:
        print("Aucun concurrent valide trouvé.")
    else:
        for competitor in top_competitors:
            print(
                f"{competitor['name']} | "
                f"{competitor['category']} | "
                f"{competitor['appearances']} apparitions | "
                f"{competitor['relevance']}"
            )

    print(f"\nNombre de concurrents enregistrés : {len(top_competitors)}")
    print(f"Erreurs de recherche : {len(errors)}")
    print("Fichier competitors.json enregistré !")

    return output


# 13. Lancer le programme
if __name__ == "__main__":
    find_competitors()
