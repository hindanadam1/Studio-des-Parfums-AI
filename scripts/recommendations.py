import json
import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"
MODEL = "openai/gpt-oss-20b"

load_dotenv(ROOT_DIR / ".env")
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None


def load_json(filename):

    try:
        with (DATA_DIR / filename).open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_json_lines(filename):

    path = DATA_DIR / filename
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []

    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    records = []
    for line in content.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def get_provider_name(result):
    return result.get("provider") or "Groq"


def get_visibility_summary(run, provider):

    successful = [
        result for result in run.get("results", [])
        if get_provider_name(result) == provider
        and result.get("status", "success") == "success"
    ]

    if successful:
        mentions = sum(bool(item.get("studio_mentioned")) for item in successful)
        return {
            "successful_attempts": len(successful),
            "studio_mentions": mentions,
            "visibility_rate": round(mentions / len(successful) * 100, 2)
        }

    summaries = run.get("summaries", {})
    summary = summaries.get(provider) if isinstance(summaries, dict) else None
    if not summary and provider == "Groq":
        summary = run.get("summary")

    if not isinstance(summary, dict) or not summary.get("successful_attempts"):
        return None

    return {
        "successful_attempts": summary["successful_attempts"],
        "studio_mentions": summary.get("studio_mentions", 0),
        "visibility_rate": summary.get("visibility_rate", 0)
    }


def get_question_rates(run, provider):

    totals = {}
    for result in run.get("results", []):
        if get_provider_name(result) != provider:
            continue
        if result.get("status", "success") != "success":
            continue

        question = result.get("question")
        if not question:
            continue
        totals.setdefault(question, {"mentions": 0, "total": 0})
        totals[question]["total"] += 1
        if result.get("studio_mentioned"):
            totals[question]["mentions"] += 1

    return {
        question: round(values["mentions"] / values["total"] * 100, 2)
        for question, values in totals.items()
        if values["total"]
    }


def prepare_data():

    competitor_file = load_json("competitors_analysis.json")
    visibility_file = load_json("visibility_history.json")
    runs = visibility_file.get("history", [])
    if not isinstance(runs, list):
        runs = []

    competitor_analyses = []
    for competitor in competitor_file.get("analyses", []):
        analysis = competitor.get("analysis", {})
        competitor_analyses.append({
            "name": competitor.get("name"),
            "domain": competitor.get("domain"),
            "strengths": [
                item.get("observation", "")
                for item in analysis.get("strengths", [])
            ],
            "weaknesses": [
                item.get("observation", "")
                for item in analysis.get("weaknesses", [])
            ]
        })

    recent_visibility = []
    for run in runs[-5:]:
        provider_results = {}
        for provider in ("Groq",):
            summary = get_visibility_summary(run, provider)
            if summary:
                provider_results[provider] = {
                    **summary,
                    "question_rates": get_question_rates(run, provider)
                }
        if provider_results:
            recent_visibility.append({
                "run_at": run.get("run_at"),
                "providers": provider_results
            })

    missing_information = []
    for provider in ("Groq",):
        available_runs = sum(
            1 for run in runs
            if get_visibility_summary(run, provider) is not None
        )
        if available_runs < 2:
            missing_information.append(
                f"historique insuffisant pour comparer {provider}"
            )
    if not competitor_analyses:
        missing_information.append("aucune analyse de concurrent disponible")
    if not any("Groq" in run.get("providers", {}) for run in recent_visibility):
        missing_information.append("aucun résultat de visibilité Groq disponible")
    if not any(len(run.get("providers", {})) for run in recent_visibility):
        missing_information.append("aucun résultat de visibilité exploitable")

    comparisons = [
        item for item in load_json_lines("comparisons.json")
        if (item.get("provider") or "Groq") == "Groq"
    ]
    alerts = [
        item for item in load_json_lines("alerts.json")
        if (item.get("provider") or "Groq") == "Groq"
    ]

    return {
        "competitor_analyses": competitor_analyses,
        "visibility_history": recent_visibility,
        "comparisons": comparisons[-10:],
        "alerts": alerts[-10:],
        "missing_information": missing_information
    }


def validate_recommendations(result):

    if not isinstance(result, dict):
        raise ValueError("La réponse doit être un objet JSON.")

    diagnostic = result.get("diagnostic")
    recommendations = result.get("recommendations")
    solutions = result.get("automatable_solutions")

    if not isinstance(diagnostic, str) or not diagnostic.strip():
        raise ValueError("Le diagnostic est manquant.")
    if not isinstance(recommendations, list) or len(recommendations) != 5:
        raise ValueError("Il faut exactement cinq recommandations.")
    if not isinstance(solutions, list) or len(solutions) != 2:
        raise ValueError("Il faut exactement deux solutions automatisables.")

    recommendation_fields = (
        "problem", "action", "priority", "expected_result", "implementation_steps"
    )
    for item in recommendations:
        if not isinstance(item, dict):
            raise ValueError("Une recommandation n'est pas un objet.")
        for field in recommendation_fields[:-1]:
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"Champ de recommandation manquant : {field}.")
        steps = item.get("implementation_steps")
        if (
            not isinstance(steps, list)
            or not steps
            or not all(isinstance(step, str) and step.strip() for step in steps)
        ):
            raise ValueError("implementation_steps doit contenir des étapes lisibles.")

    for item in solutions:
        if not isinstance(item, dict):
            raise ValueError("Une solution automatisable n'est pas un objet.")
        for field in ("name", "description", "trigger"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"Champ de solution manquant : {field}.")

    return result


def generate_recommendations():

    if client is None:
        print("GROQ_API_KEY introuvable dans .env.")
        return

    print("\n========== GENERATION DES RECOMMANDATIONS ==========")
    analysis_data = prepare_data()
    prompt = f"""
Tu aides Studio des Parfums à améliorer sa visibilité dans les assistants IA.
Utilise uniquement les éléments présents dans les données ci-dessous.
N'invente aucun défaut, résultat, concurrent ou tendance.
Si une information manque, dis-le dans le diagnostic et garde les conseils
conditionnels plutôt que de présenter une hypothèse comme un fait.

Données disponibles :
{json.dumps(analysis_data, ensure_ascii=False)}

Génère un diagnostic général, exactement cinq recommandations et exactement
deux solutions automatisables.
Chaque recommandation doit contenir problem, action, priority,
expected_result et implementation_steps (une liste d'étapes).
Chaque solution doit contenir name, description et trigger.

Réponds uniquement en JSON valide avec les clés diagnostic, recommendations,
automatable_solutions. Le diagnostic doit mentionner clairement les données
insuffisantes signalées dans missing_information.
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_completion_tokens=2500
        )

        response_text = response.choices[0].message.content
        if not response_text:
            raise ValueError("Réponse Groq vide.")

        result = validate_recommendations(json.loads(response_text))
        with RECOMMENDATIONS_FILE.open("w", encoding="utf-8") as file:
            json.dump(result, file, indent=4, ensure_ascii=False)

        print("Diagnostic et recommandations enregistrés dans recommendations.json.")

    except Exception as error:
        # Ne pas afficher le texte brut d'une erreur d'API dans les logs.
        print(f"Génération interrompue ({type(error).__name__}).")


if __name__ == "__main__":
    generate_recommendations()
