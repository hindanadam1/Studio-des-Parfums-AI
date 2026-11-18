import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
HISTORY_FILE = DATA_DIR / "visibility_history.json"
COMPARISONS_FILE = DATA_DIR / "comparisons.json"
ALERTS_FILE = DATA_DIR / "alerts.json"
ALERT_THRESHOLD = 10
PROVIDERS = ["Groq"]


def load_history():

    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict) and isinstance(data.get("history"), list):
        return data["history"]

    return []


def get_provider_name(result):
    # Les anciennes exécutions ne stockaient pas le nom du fournisseur.
    return result.get("provider") or "Groq"


def get_provider_summary(run, provider):

    results = [
        item for item in run.get("results", [])
        if get_provider_name(item) == provider
        and item.get("status", "success") == "success"
    ]

    if results:
        mentions = sum(bool(item.get("studio_mentioned")) for item in results)
        return {
            "successful_attempts": len(results),
            "studio_mentions": mentions,
            "visibility_rate": round(mentions / len(results) * 100, 2)
        }

    summaries = run.get("summaries", {})
    summary = summaries.get(provider) if isinstance(summaries, dict) else None

    # Compatibilité avec l'ancien champ "summary", réservé à Groq.
    if not summary and provider == "Groq":
        summary = run.get("summary")

    if not isinstance(summary, dict):
        return None

    successful_attempts = summary.get("successful_attempts", 0)
    if not successful_attempts:
        return None

    return {
        "successful_attempts": successful_attempts,
        "studio_mentions": summary.get("studio_mentions", 0),
        "visibility_rate": summary.get("visibility_rate", 0)
    }


def question_rates(run, provider="Groq"):

    questions = {}

    for result in run.get("results", []):
        if get_provider_name(result) != provider:
            continue
        if result.get("status", "success") != "success":
            continue

        question = result.get("question")
        if not question:
            continue

        if question not in questions:
            questions[question] = {"mentions": 0, "total": 0}

        questions[question]["total"] += 1
        if result.get("studio_mentioned"):
            questions[question]["mentions"] += 1

    return {
        question: round(values["mentions"] / values["total"] * 100, 2)
        for question, values in questions.items()
        if values["total"]
    }


def read_json_lines(path):

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []

    if not content.strip():
        return []

    try:
        data = json.loads(content)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    records = []
    for line in content.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)

    return records


def comparison_exists(comparisons, provider, previous_run, latest_run):

    for item in comparisons:
        item_provider = item.get("provider") or "Groq"
        if (
            item_provider == provider
            and item.get("previous_run") == previous_run
            and item.get("latest_run") == latest_run
        ):
            return True

    return False


def alert_exists(alerts, alert):

    for item in alerts:
        item_provider = item.get("provider") or "Groq"
        if item_provider != alert["provider"]:
            continue

        item_date = item.get("latest_run") or item.get("date")
        if item_date != alert["latest_run"]:
            continue

        if item.get("scope") == alert["scope"]:
            if item.get("question") == alert.get("question"):
                return True

        # Les alertes historiques ne distinguaient pas fournisseur et portée.
        if (
            not item.get("provider")
            and alert["provider"] == "Groq"
            and alert.get("question") in item.get("questions", [])
            and item_date == alert["latest_run"]
        ):
            return True

    return False


def append_json_line(path, item):

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")


def build_comparison(previous, latest, provider, old_summary, new_summary):

    old_questions = question_rates(previous, provider)
    new_questions = question_rates(latest, provider)
    question_comparisons = []
    alerts = []

    for question, latest_rate in new_questions.items():
        if question not in old_questions:
            continue

        previous_rate = old_questions[question]
        difference = round(latest_rate - previous_rate, 2)

        if difference <= -ALERT_THRESHOLD:
            status = "BAISSE SIGNIFICATIVE"
            alerts.append({
                "provider": provider,
                "latest_run": latest["run_at"],
                "scope": "question",
                "question": question,
                "difference_points": difference,
                "message": "Baisse significative sur cette question."
            })
        elif difference > 0:
            status = "HAUSSE"
        elif difference < 0:
            status = "BAISSE"
        else:
            status = "STABLE"

        question_comparisons.append({
            "question": question,
            "previous_rate": previous_rate,
            "latest_rate": latest_rate,
            "difference_points": difference,
            "status": status
        })

    overall_difference = round(
        new_summary["visibility_rate"] - old_summary["visibility_rate"], 2
    )

    if overall_difference <= -ALERT_THRESHOLD:
        status = "BAISSE SIGNIFICATIVE"
        alerts.append({
            "provider": provider,
            "latest_run": latest["run_at"],
            "scope": "provider",
            "difference_points": overall_difference,
            "message": "Baisse significative du taux de visibilité."
        })
    elif overall_difference > 0:
        status = "HAUSSE"
    elif overall_difference < 0:
        status = "LEGERE BAISSE"
    else:
        status = "STABLE"

    comparison = {
        "provider": provider,
        "previous_run": previous["run_at"],
        "latest_run": latest["run_at"],
        "previous_visibility": old_summary["visibility_rate"],
        "latest_visibility": new_summary["visibility_rate"],
        "difference_points": overall_difference,
        "status": status,
        "question_comparisons": question_comparisons
    }

    return comparison, alerts


def compare_runs():

    history = [run for run in load_history() if isinstance(run, dict)]
    if len(history) < 2:
        print("Il faut au moins deux exécutions pour comparer.")
        return

    comparisons = read_json_lines(COMPARISONS_FILE)
    alerts = read_json_lines(ALERTS_FILE)
    new_comparison_count = 0
    new_alert_count = 0

    for provider in PROVIDERS:
        provider_runs = [
            (run, get_provider_summary(run, provider))
            for run in history
        ]
        provider_runs = [item for item in provider_runs if item[1] is not None]

        if len(provider_runs) < 2:
            print(f"{provider} : pas encore assez d'historique.")
            continue

        (previous, old_summary), (latest, new_summary) = provider_runs[-2:]
        if not previous.get("run_at") or not latest.get("run_at"):
            print(f"{provider} : date d'exécution manquante, comparaison ignorée.")
            continue

        comparison, detected_alerts = build_comparison(
            previous, latest, provider, old_summary, new_summary
        )

        if comparison_exists(
            comparisons,
            provider,
            comparison["previous_run"],
            comparison["latest_run"]
        ):
            print(
                f"{provider} : comparaison déjà enregistrée "
                f"({comparison['latest_run']})."
            )
        else:
            append_json_line(COMPARISONS_FILE, comparison)
            comparisons.append(comparison)
            new_comparison_count += 1
            print(
                f"{provider} : {comparison['difference_points']:+.2f} points "
                f"({comparison['status']})."
            )

        for alert in detected_alerts:
            if alert_exists(alerts, alert):
                continue
            append_json_line(ALERTS_FILE, alert)
            alerts.append(alert)
            new_alert_count += 1

    print(
        f"Comparaisons ajoutées : {new_comparison_count} | "
        f"alertes ajoutées : {new_alert_count}"
    )


if __name__ == "__main__":
    compare_runs()
