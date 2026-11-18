
import os
import json
import time
import unicodedata

from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq


# ==========================================
# 1. CONFIGURATION
# ==========================================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
QUESTIONS_FILE = ROOT_DIR / "config" / "visibility_questions.json"

load_dotenv(ROOT_DIR / ".env")

# Configuration Groq
groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:
    raise ValueError("Clé GROQ_API_KEY introuvable dans .env")

groq_client = Groq(api_key=groq_api_key)

GROQ_MODEL = "openai/gpt-oss-20b"


# Nombre de répétitions par question et par IA
REPETITIONS = 3

SYSTEM_PROMPT = (
    "Tu es un assistant spécialisé dans les ateliers "
    "de création de parfum à Paris. Réponds naturellement "
    "à la question de l'utilisateur. Ne prétends pas "
    "avoir vérifié des informations en temps réel."
)


# ==========================================
# 2. NORMALISER LES TEXTES
# ==========================================

def normalize_text(text):

    text = text.lower()

    text = unicodedata.normalize("NFD", text)

    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )

    return text


# ==========================================
# 3. CHARGER LES QUESTIONS
# ==========================================

def load_questions():

    with QUESTIONS_FILE.open("r", encoding="utf-8") as file:

        data = json.load(file)

    questions = data.get("questions", [])

    if len(questions) != 5:
        raise ValueError("Le fichier doit contenir exactement cinq questions.")

    return questions


# ==========================================
# 4. CHARGER LES CONCURRENTS
# ==========================================

def load_competitor_names():

    with (DATA_DIR / "competitors.json").open(
        "r", encoding="utf-8"
    ) as file:

        data = json.load(file)

    return [
        competitor["name"]
        for competitor in data["competitors"]
    ]


# ==========================================
# 5. INTERROGER GROQ
# ==========================================

def ask_groq(question):

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": question
            }
        ],
        max_completion_tokens=700
    )

    return response.choices[0].message.content or ""


# ==========================================
# 6. DETECTER LES MENTIONS
# ==========================================

def detect_mentions(answer, competitor_names):

    normalized_answer = normalize_text(answer or "")

    # Détection de Studio des Parfums
    studio_mentioned = (
        "studio des parfums" in normalized_answer
    )

    # Détection des concurrents
    mentioned_competitors = []

    for name in competitor_names:

        normalized_name = normalize_text(name)

        if normalized_name in normalized_answer:
            mentioned_competitors.append(name)

    return studio_mentioned, mentioned_competitors


def calculate_summaries(results, providers, question_count):

    summaries = {}

    for provider in providers:

        provider_results = [
            result for result in results
            if result.get("provider") == provider["name"]
            and result.get("status") == "success"
        ]

        studio_mentions = sum(
            bool(result.get("studio_mentioned"))
            for result in provider_results
        )
        successful_attempts = len(provider_results)
        visibility_rate = (
            round(studio_mentions / successful_attempts * 100, 2)
            if successful_attempts else 0
        )

        summaries[provider["name"]] = {
            "total_attempts": REPETITIONS * question_count,
            "successful_attempts": successful_attempts,
            "studio_mentions": studio_mentions,
            "visibility_rate": visibility_rate
        }

    return summaries


def load_history_data(history_file):

    try:
        with history_file.open("r", encoding="utf-8") as file:
            history_data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"history": []}

    if isinstance(history_data, list):
        return {"history": history_data}

    if not isinstance(history_data, dict):
        return {"history": []}

    if not isinstance(history_data.get("history"), list):
        history_data["history"] = []

    return history_data


# ==========================================
# 7. LANCER LES INTERROGATIONS
# ==========================================

def run_visibility_test():

    questions = load_questions()
    competitor_names = load_competitor_names()

    results = []

    providers = [
        {
            "name": "Groq",
            "model": GROQ_MODEL,
            "function": ask_groq
        }
    ]

    print("\n========== TEST DE VISIBILITE IA ==========")

    for provider in providers:

        print(f"\n========== FOURNISSEUR : {provider['name']} ==========")

        for item in questions:

            question = item["question"]

            print(f"\nQuestion {item['id']} : {question}")

            for repetition in range(1, REPETITIONS + 1):

                print(
                    f"\nRépétition {repetition}/{REPETITIONS}"
                )

                try:

                    answer = provider["function"](question)

                    studio_mentioned, mentioned_competitors = (
                        detect_mentions(answer, competitor_names)
                    )

                    result = {
                        "provider": provider["name"],
                        "model": provider["model"],
                        "question_id": item["id"],
                        "question": question,
                        "repetition": repetition,
                        "studio_mentioned": studio_mentioned,
                        "competitors_mentioned": mentioned_competitors,
                        "answer": answer,
                        "tested_at": datetime.now().astimezone().isoformat(
                            timespec="seconds"
                        ),
                        "status": "success"
                    }

                    results.append(result)

                    print(
                        "Studio des Parfums cité :",
                        "OUI" if studio_mentioned else "NON"
                    )

                    print(
                        "Concurrents cités :",
                        mentioned_competitors
                    )

                except Exception as error:

                    print(
                        f"Erreur fournisseur {provider['name']} : "
                        f"{type(error).__name__}. La veille continue."
                    )

                    results.append({
                        "provider": provider["name"],
                        "model": provider["model"],
                        "question_id": item["id"],
                        "question": question,
                        "repetition": repetition,
                        "status": "error",
                        "error": "Échec de l'appel au fournisseur IA.",
                        "error_type": type(error).__name__,
                        "tested_at": datetime.now().astimezone().isoformat(
                            timespec="seconds"
                        )
                    })

                time.sleep(2)

    # ======================================
    # 8. CALCULER LES RESULTATS PAR IA
    # ======================================

    summaries = calculate_summaries(results, providers, len(questions))

    # ======================================
    # 9. ENREGISTRER L'HISTORIQUE
    # ======================================

    history_file = DATA_DIR / "visibility_history.json"

    history_data = load_history_data(history_file)
    run_at = datetime.now().astimezone().isoformat(timespec="seconds")

    new_run = {
        "run_at": run_at,
        "providers": [provider["name"] for provider in providers],
        "summaries": summaries,
        "results": results
    }

    # Un second lancement dans la même seconde ne crée pas un doublon.
    if not any(run.get("run_at") == run_at for run in history_data["history"]):
        history_data["history"].append(new_run)

    with history_file.open("w", encoding="utf-8") as file:

        json.dump(
            history_data,
            file,
            indent=4,
            ensure_ascii=False
        )

    # ======================================
    # 10. AFFICHER LE BILAN
    # ======================================

    print("\n========== BILAN DE VISIBILITE ==========")

    print(f"Nombre total d'interrogations : {len(results)}")

    for provider_name, summary in summaries.items():

        print(f"\n--- {provider_name} ---")

        print(
            "Réponses réussies :",
            summary["successful_attempts"]
        )

        print(
            "Mentions de Studio des Parfums :",
            summary["studio_mentions"]
        )

        print(
            "Taux de visibilité :",
            f"{summary['visibility_rate']}%"
        )

    print(f"\nHistorique enregistré dans : {history_file}")


# ==========================================
# 11. EXECUTION
# ==========================================

if __name__ == "__main__":

    run_visibility_test()
