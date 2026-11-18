import html
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import altair as alt
import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
LOGO_PATH = ROOT_DIR / "assets" / "logo_parfum.png"
PROVIDERS = ("Groq",)
COLORS = {
    "gold": "#D8B280",
    "black": "#1A1A1A",
    "white": "#FFFFFF",
    "gray": "#E0E0E0",
    "brown": "#8F654D",
    "rose": "#A66F72"
}


def configure_chart(chart, height=260):
    return (
        chart.properties(height=height)
        .configure(background=COLORS["white"])
        .configure_axis(
            labelColor=COLORS["black"],
            titleColor=COLORS["brown"],
            gridColor=COLORS["gray"],
            domainColor=COLORS["gray"],
            tickColor=COLORS["gray"]
        )
        .configure_legend(
            labelColor=COLORS["black"],
            titleColor=COLORS["brown"],
            orient="top"
        )
        .configure_view(stroke=COLORS["gray"])
    )


def provider_color_scale():
    return alt.Scale(
        domain=list(PROVIDERS),
        range=[COLORS["gold"]]
    )


def render_observation_table(rows, observation_column):
    """Affiche les observations complètes avec un lien source compact."""
    if not rows:
        return

    body_rows = []
    for row in rows:
        competitor = html.escape(str(row.get("Concurrent", "—")))
        observation = html.escape(str(row.get(observation_column, "—")))
        observation = observation.replace("\n", "<br>")
        source = str(row.get("Source", "")).strip()
        parsed_source = urlsplit(source)
        if parsed_source.scheme in {"http", "https"} and parsed_source.netloc:
            source_html = (
                f'<a class="observation-source-link" href="{html.escape(source, quote=True)}" '
                'target="_blank" rel="noopener noreferrer">Voir ↗</a>'
            )
        else:
            source_html = html.escape(source or "—")

        body_rows.append(
            f"<tr><td>{competitor}</td><td>{observation}</td><td>{source_html}</td></tr>"
        )

    table_html = (
        '<div class="observation-table-wrap"><table class="observation-table">'
        '<colgroup><col class="competitor-col"><col class="observation-col">'
        '<col class="source-col"></colgroup>'
        f"<thead><tr><th>Concurrent</th><th>{html.escape(observation_column)}</th>"
        f"<th>Source</th></tr></thead><tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def render_recommendations_table(recommendations):
    """Affiche les recommandations sans tronquer leurs textes."""
    body_rows = []
    for item in recommendations:
        values = (
            item.get("problem", "—"),
            item.get("priority", "—"),
            item.get("action", "—"),
            item.get("expected_result", "—")
        )
        cells = "".join(
            f"<td>{html.escape(str(value)).replace(chr(10), '<br>')}</td>"
            for value in values
        )
        body_rows.append(f"<tr>{cells}</tr>")

    table_html = (
        '<div class="recommendation-table-wrap"><table class="recommendation-table">'
        '<colgroup><col class="problem-col"><col class="priority-col">'
        '<col class="action-col"><col class="result-col"></colgroup>'
        "<thead><tr><th>Problème</th><th>Priorité</th>"
        "<th>Action proposée</th><th>Résultat attendu</th></tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def render_solutions_table(solutions):
    rows = []
    for item in solutions:
        values = (
            item.get("name", "—"),
            item.get("description", "—"),
            item.get("trigger", "—")
        )
        cells = "".join(
            f"<td>{html.escape(str(value)).replace(chr(10), '<br>')}</td>"
            for value in values
        )
        rows.append(f"<tr>{cells}</tr>")

    st.markdown(
        '<div class="recommendation-table-wrap"><table class="recommendation-table solution-table">'
        '<colgroup><col class="solution-col"><col class="description-col">'
        '<col class="trigger-col"></colgroup>'
        "<thead><tr><th>Solution</th><th>Description</th><th>Déclencheur</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>",
        unsafe_allow_html=True
    )


def read_json(filename):
    """Lit un fichier de résultats sans le modifier."""
    try:
        with (DATA_DIR / filename).open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None


def read_json_lines(filename):
    """Lit un fichier JSON Lines et accepte aussi un JSON classique."""
    try:
        content = (DATA_DIR / filename).read_text(encoding="utf-8")
    except OSError:
        return []

    if not content.strip():
        return []

    try:
        data = json.loads(content)
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    rows = []
    for line in content.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def get_provider_name(result):
    # Les anciennes réponses sans fournisseur proviennent de Groq.
    return result.get("provider") or "Groq"


def provider_summary(run, provider):
    """Calcule le taux depuis les réponses ou lit le résumé historique."""
    if not isinstance(run, dict):
        return None

    results = run.get("results", [])
    if not isinstance(results, list):
        results = []

    attempts = [
        row for row in results
        if isinstance(row, dict) and get_provider_name(row) == provider
    ]
    successful = [
        row for row in attempts
        if row.get("status", "success") == "success"
    ]

    if successful:
        mentions = sum(bool(row.get("studio_mentioned")) for row in successful)
        return {
            "attempts": len(attempts),
            "successful": len(successful),
            "mentions": mentions,
            "rate": round(mentions / len(successful) * 100, 2)
        }

    summaries = run.get("summaries", {})
    summary = summaries.get(provider) if isinstance(summaries, dict) else None
    if not summary and provider == "Groq":
        summary = run.get("summary")
    if not isinstance(summary, dict) or not summary.get("successful_attempts"):
        return None

    return {
        "attempts": summary.get("total_attempts", summary["successful_attempts"]),
        "successful": summary["successful_attempts"],
        "mentions": summary.get("studio_mentions", 0),
        "rate": summary.get("visibility_rate", 0)
    }


def is_complete_run(run, provider="Groq"):
    """Indique si tous les tests prévus ont reçu une réponse réussie."""
    summary = provider_summary(run, provider)
    if not summary:
        return False
    try:
        attempts = int(summary["attempts"])
        successful = int(summary["successful"])
    except (KeyError, TypeError, ValueError):
        return False
    return attempts > 0 and successful >= attempts


def latest_complete_run(history):
    """Renvoie la mesure complète la plus récente, sans toucher à l'historique."""
    return next(
        (
            run for run in reversed(history)
            if isinstance(run, dict) and is_complete_run(run)
        ),
        None
    )


def question_rows(run):
    grouped = defaultdict(lambda: {
        "id": None,
        "question": "",
        "Groq": {"attempts": 0, "successes": 0, "mentions": 0}
    })

    for result in run.get("results", []):
        if not isinstance(result, dict):
            continue
        provider = get_provider_name(result)
        if provider not in PROVIDERS:
            continue

        question = result.get("question") or "Question sans libellé"
        key = (result.get("question_id"), question)
        row = grouped[key]
        row["id"] = result.get("question_id")
        row["question"] = question
        row[provider]["attempts"] += 1
        if result.get("status", "success") == "success":
            row[provider]["successes"] += 1
            if result.get("studio_mentioned"):
                row[provider]["mentions"] += 1

    rows = []
    chart_rows = []
    for row in grouped.values():
        display = {"N°": row["id"] or "—", "Question": row["question"]}
        chart = {"Question": row["question"]}
        for provider in PROVIDERS:
            values = row[provider]
            rate = (
                round(values["mentions"] / values["successes"] * 100, 2)
                if values["successes"] else None
            )
            display[f"{provider} · citations"] = (
                f"{values['mentions']} / {values['successes']}"
                if values["successes"] else "Aucune réponse"
            )
            display[f"{provider} · taux"] = f"{rate:.2f}%" if rate is not None else "—"
            chart[provider] = rate
        rows.append(display)
        chart_rows.append(chart)

    return rows, chart_rows


def render_full_answers(run):
    """Affiche le texte complet de chaque réponse de la dernière exécution."""
    results = run.get("results", [])
    if not isinstance(results, list) or not results:
        st.info("Aucune réponse détaillée n'est enregistrée pour cette exécution.")
        return

    st.subheader("Réponses complètes de la dernière exécution")
    st.caption("Ouvre une question pour lire toute la réponse, sans troncature.")
    provider_results = [
        row for row in results
        if isinstance(row, dict) and get_provider_name(row) == "Groq"
    ]
    if not provider_results:
        st.info("Aucune réponse Groq dans cette exécution.")
        return

    for row in provider_results:
        question_id = row.get("question_id", "—")
        repetition = row.get("repetition", "—")
        status = row.get("status", "success")
        label = (
            f"Question {question_id} · répétition {repetition} · "
            f"{'réussie' if status == 'success' else 'sans réponse'}"
        )

        with st.expander(label):
            st.markdown("**Question posée**")
            st.write(row.get("question", "Question non enregistrée"))
            st.caption(
                f"Modèle : {row.get('model', 'non précisé')} · "
                f"Date : {row.get('tested_at', 'non précisée')}"
            )
            answer = row.get("answer")
            if isinstance(answer, str) and answer.strip():
                st.markdown("**Réponse intégrale**")
                st.markdown(answer)
            else:
                st.info("Aucun texte de réponse n'a été enregistré.")


def render_competitors(competitors, analyses, using_historical_analyses=False):
    st.header("Veille concurrentielle")
    st.subheader("Concurrents identifiés")
    if using_historical_analyses:
        st.info("L'analyse la plus recente n'a pas abouti. Affichage de la derniere analyse complete conservee dans l'historique.")
    if not competitors:
        st.info("Aucun concurrent identifié dans les résultats disponibles.")
        return

    st.dataframe([
        {
            "Concurrent": item.get("name", "Nom inconnu"),
            "Domaine": item.get("domain", "—"),
            "Catégorie": item.get("category", "—"),
            "Présence dans les recherches": item.get("appearances", "—"),
            "Pertinence": item.get("relevance", "—")
        }
        for item in competitors
    ], hide_index=True, width="stretch", column_config={
        "Concurrent": st.column_config.TextColumn(width="medium"),
        "Domaine": st.column_config.TextColumn(width="medium"),
        "Catégorie": st.column_config.TextColumn(width="medium"),
        "Présence dans les recherches": st.column_config.TextColumn(width="medium"),
        "Pertinence": st.column_config.TextColumn(width="medium")
    })

    analyses_by_domain = {
        item.get("domain"): item
        for item in analyses
        if isinstance(item, dict) and item.get("domain")
    }
    strengths = []
    weaknesses = []
    for competitor in competitors:
        record = analyses_by_domain.get(competitor.get("domain"), {})
        analysis = record.get("analysis", {})
        name = competitor.get("name", "Concurrent")
        for point in analysis.get("strengths", []):
            strengths.append({
                "Concurrent": name,
                "Point fort": point.get("observation", "—"),
                "Source": point.get("source_url", "—")
            })
        for point in analysis.get("weaknesses", []):
            weaknesses.append({
                "Concurrent": name,
                "Point faible": point.get("observation", "—"),
                "Source": point.get("source_url", "—")
            })

    strong_tab, weak_tab = st.tabs(["Points forts", "Points faibles"])
    with strong_tab:
        if strengths:
            render_observation_table(strengths, "Point fort")
        else:
            st.info("Aucun point fort n'est présent dans les analyses.")
    with weak_tab:
        if weaknesses:
            render_observation_table(weaknesses, "Point faible")
        else:
            st.info("Aucun point faible n'est présent dans les analyses.")


def render_visibility(history):
    st.header("Visibilité IA")
    if not history:
        st.info("Aucune exécution de visibilité n'est enregistrée.")
        return

    recorded_runs = [run for run in history if isinstance(run, dict)]
    if not recorded_runs:
        st.info("Aucune execution de visibilite exploitable n'est enregistree.")
        return

    latest_recorded = recorded_runs[-1]
    latest_complete = latest_complete_run(recorded_runs)
    latest = latest_complete or latest_recorded
    latest_recorded_summary = provider_summary(latest_recorded, "Groq")
    if latest_complete and latest_complete is not latest_recorded:
        if latest_recorded_summary:
            st.warning(
                "La derniere execution est partielle "
                f"({latest_recorded_summary['successful']}/"
                f"{latest_recorded_summary['attempts']} reponses reussies). "
                "Les indicateurs principaux affichent la derniere mesure complete "
                f"du {latest.get('run_at', 'date inconnue')} ; les essais partiels "
                "restent dans l'historique."
            )
        else:
            st.warning("La derniere execution est partielle ; affichage de la derniere mesure complete.")
    elif not latest_complete:
        st.warning("Aucune execution complete n'est disponible. La derniere mesure peut etre partielle.")
    summaries = {
        provider: provider_summary(latest, provider)
        for provider in PROVIDERS
    }
    columns = st.columns(len(PROVIDERS))
    for column, provider in zip(columns, PROVIDERS):
        summary = summaries[provider]
        with column:
            if summary:
                column.metric(f"Taux de citation · {provider}", f"{summary['rate']:.2f}%")
                column.caption(
                    f"{summary['mentions']} mentions · "
                    f"{summary['successful']} réponses réussies sur "
                    f"{summary['attempts']} tests."
                )
            else:
                column.metric(f"Taux de citation · {provider}", "Non disponible")

    st.caption(f"Mesure complete affichee : {latest.get('run_at', 'date inconnue')}")
    current_rates = {
        provider: [summary["rate"]]
        for provider, summary in summaries.items()
        if summary
    }
    if current_rates:
        st.subheader("Comparaison des taux actuels")
        current_chart_rows = [
            {
                "IA": provider,
                "Taux": summary["rate"],
                "Mentions": summary["mentions"],
                "Réponses": summary["successful"]
            }
            for provider, summary in summaries.items()
            if summary
        ]
        current_chart = alt.Chart(pd.DataFrame(current_chart_rows)).mark_bar(
            cornerRadiusEnd=5,
            size=48
        ).encode(
            x=alt.X("IA:N", sort=list(PROVIDERS), axis=alt.Axis(title=None, labelAngle=0)),
            y=alt.Y("Taux:Q", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(title="Citation (%)")),
            color=alt.Color("IA:N", scale=provider_color_scale(), legend=None),
            tooltip=[
                alt.Tooltip("IA:N", title="Assistant"),
                alt.Tooltip("Taux:Q", title="Taux de citation", format=".2f"),
                alt.Tooltip("Mentions:Q", title="Mentions"),
                alt.Tooltip("Réponses:Q", title="Réponses réussies")
            ]
        )
        st.altair_chart(configure_chart(current_chart, 250), width="stretch")

    rows, chart_rows = question_rows(latest)
    if rows:
        st.subheader("Questions testées")
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            column_config={
                "Question": st.column_config.TextColumn(width="large"),
                "Groq · citations": st.column_config.TextColumn(width="small"),
                "Groq · taux": st.column_config.TextColumn(width="small")
            }
        )
        if any(row["Groq"] is not None for row in chart_rows):
            st.subheader("Taux de citation par question")
            question_chart_rows = [
                {"Question": row["Question"], "IA": provider, "Taux": row[provider]}
                for row in chart_rows
                for provider in PROVIDERS
                if row[provider] is not None
            ]
            question_chart = alt.Chart(pd.DataFrame(question_chart_rows)).mark_bar(
                cornerRadiusEnd=4,
                size=14
            ).encode(
                x=alt.X("Taux:Q", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(title="Citation (%)")),
                y=alt.Y("Question:N", sort=None, axis=alt.Axis(title=None, labelLimit=1000)),
                yOffset=alt.YOffset("IA:N"),
                color=alt.Color("IA:N", scale=provider_color_scale(), legend=alt.Legend(title=None)),
                tooltip=[
                    alt.Tooltip("Question:N", title="Question"),
                    alt.Tooltip("IA:N", title="Assistant"),
                    alt.Tooltip("Taux:Q", title="Taux", format=".2f")
                ]
            )
            st.altair_chart(
                configure_chart(question_chart, max(170, len(rows) * 45)),
                width="stretch"
            )

    complete_runs = [run for run in recorded_runs if is_complete_run(run)]
    chart_runs = complete_runs or recorded_runs
    history_chart_rows = []
    for run_index, run in enumerate(chart_runs, start=1):
        for provider in PROVIDERS:
            summary = provider_summary(run, provider)
            if summary:
                history_chart_rows.append({
                    "Exécution": run_index,
                    "Date": run.get("run_at", "Date inconnue"),
                    "IA": provider,
                    "Taux": summary["rate"]
                })
    if history_chart_rows:
        st.subheader("Évolution des dernières exécutions")
        history_chart = alt.Chart(pd.DataFrame(history_chart_rows)).mark_line(
            point=True,
            strokeWidth=2.5
        ).encode(
            x=alt.X("Exécution:O", axis=alt.Axis(title="Exécution", labelAngle=0)),
            y=alt.Y("Taux:Q", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(title="Citation (%)")),
            color=alt.Color("IA:N", scale=provider_color_scale(), legend=alt.Legend(title=None)),
            tooltip=[
                alt.Tooltip("Date:N", title="Date"),
                alt.Tooltip("IA:N", title="Assistant"),
                alt.Tooltip("Taux:Q", title="Taux", format=".2f")
            ]
        )
        st.altair_chart(configure_chart(history_chart, 270), width="stretch")
        if complete_runs:
            st.caption("Le graphique suit les executions completes. Les essais partiels restent dans l'historique detaille.")
        else:
            st.caption("Aucune execution complete : le graphique montre les mesures enregistrees.")

    render_full_answers(latest)

    history_rows = []
    for run in reversed(history):
        if not isinstance(run, dict):
            continue
        row = {"Date": run.get("run_at", "Date inconnue")}
        for provider in PROVIDERS:
            summary = provider_summary(run, provider)
            row[provider] = f"{summary['rate']:.2f}%" if summary else "—"
            if provider == "Groq":
                if summary and is_complete_run(run, provider):
                    row["Etat"] = "Complete"
                elif summary:
                    row["Etat"] = f"Partielle - {summary['successful']}/{summary['attempts']} reponses"
                else:
                    row["Etat"] = "Donnees indisponibles"
        history_rows.append(row)
    with st.expander("Historique détaillé"):
        if history_rows:
            st.dataframe(
                history_rows,
                hide_index=True,
                width="stretch",
                column_config={
                    "Date": st.column_config.TextColumn(width="medium"),
                    "Groq": st.column_config.TextColumn(width="small"),
                    "Etat": st.column_config.TextColumn(width="medium")
                }
            )
        else:
            st.write("Aucun historique disponible.")


def render_evolution(comparisons, alerts, competitor_history):
    st.header("Évolution et alertes")
    if comparisons:
        rows = []
        for item in reversed(comparisons[-10:]):
            difference = item.get("difference_points")
            status = item.get("status", "Non disponible")
            rows.append({
                "IA": item.get("provider") or "Groq",
                "Exécution précédente": item.get("previous_run", "—"),
                "Dernière exécution": item.get("latest_run", "—"),
                "Écart": f"{difference:+.2f} points" if difference is not None else "—",
                "Taux précédent": (
                    f"{item['previous_visibility']:.2f}%"
                    if item.get("previous_visibility") is not None else "—"
                ),
                "Dernier taux": (
                    f"{item['latest_visibility']:.2f}%"
                    if item.get("latest_visibility") is not None else "—"
                ),
                "Tendance": status
            })
        st.subheader("Comparaisons récentes")
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            column_config={
                "IA": st.column_config.TextColumn(width="small"),
                "Exécution précédente": st.column_config.TextColumn(width="medium"),
                "Dernière exécution": st.column_config.TextColumn(width="medium"),
                "Écart": st.column_config.TextColumn(width="small"),
                "Taux précédent": st.column_config.TextColumn(width="small"),
                "Dernier taux": st.column_config.TextColumn(width="small"),
                "Tendance": st.column_config.TextColumn(width="medium")
            }
        )
    else:
        st.info("Aucune comparaison n'est enregistrée.")

    st.subheader(f"Alertes enregistrées · {len(alerts)}")
    if not alerts:
        st.success("Aucune alerte enregistrée.")
    else:
        for alert in reversed(alerts[-10:]):
            provider = alert.get("provider") or "Groq"
            date = alert.get("latest_run") or alert.get("date", "Date inconnue")
            message = alert.get("message", "Alerte enregistrée")
            question = alert.get("question")
            if alert.get("difference_points") is not None:
                message += f" ({alert['difference_points']:+.2f} points)"
            if question:
                message += f" · {question}"
            elif alert.get("questions"):
                message += " · " + "; ".join(alert["questions"])
            st.warning(f"**{provider} · {date}**  \n{message}")

    if competitor_history:
        st.subheader("Historique des analyses concurrentielles")
        history_rows = [
            {
                "Date": run.get("run_at", "Date inconnue"),
                "Concurrents analysés": len(run.get("analyses", []))
            }
            for run in reversed(competitor_history[-10:])
            if isinstance(run, dict)
        ]
        st.dataframe(
            history_rows,
            hide_index=True,
            width="stretch",
            column_config={
                "Date": st.column_config.TextColumn(width="medium"),
                "Concurrents analysés": st.column_config.TextColumn(width="medium")
            }
        )


def render_recommendations(data):
    st.header("Recommandations")
    if not isinstance(data, dict):
        st.info("Aucun fichier de recommandations disponible.")
        data = {}

    if data.get("diagnostic"):
        diagnostic = html.escape(str(data["diagnostic"])).replace("\n", "<br>")
        st.markdown(
            f'<div class="diagnostic-card">{diagnostic}</div>',
            unsafe_allow_html=True
        )
    recommendations = data.get("recommendations", [])
    if recommendations:
        render_recommendations_table(recommendations)
        with st.expander("Étapes de mise en œuvre"):
            for number, item in enumerate(recommendations, start=1):
                st.markdown(f"**{number}. {item.get('action', 'Action')}**")
                steps = item.get("implementation_steps", [])
                if isinstance(steps, list):
                    for step in steps:
                        st.markdown(f"- {step}")
                elif steps:
                    st.write(steps)
    else:
        st.info("Aucune recommandation n'est enregistrée.")

    st.subheader("Solutions automatisables")
    solutions = data.get("automatable_solutions", [])
    if solutions:
        render_solutions_table(solutions)
    else:
        st.write("Aucune solution automatisable enregistrée pour le moment.")

st.set_page_config(
    page_title="Studio des Parfums AI · Tableau de bord",
    page_icon=str(LOGO_PATH),
    layout="wide"
)

# Palette demandée : blanc, noir, doré champagne, gris, brun et rose poudré.
st.markdown(
    """
    <style>
    :root {
        color-scheme: light !important;
        --primary-color: #D8B280 !important;
        --background-color: #FFFFFF !important;
        --secondary-background-color: #FFFFFF !important;
        --text-color: #1A1A1A !important;
    }
    html, body, .stApp, [data-testid="stAppViewContainer"] {
        background-color: #FFFFFF !important;
        color: #1A1A1A !important;
    }
    [data-testid="stHeader"] { background: #FFFFFF !important; }
    .block-container { max-width: 1500px; padding-top: 1.4rem; padding-bottom: 3rem; }
    [data-testid="stImage"] { display: flex; justify-content: center; }
    [data-testid="stImage"] img { object-fit: contain; }
    h1, h2 { color: #1A1A1A !important; }
    h2 { border-bottom: 1px solid #E0E0E0; padding-bottom: 0.45rem; }
    h3 { color: #8F654D !important; }
    p, label, li { color: #1A1A1A !important; }
    a { color: #8F654D !important; }
    hr { border-color: #E0E0E0 !important; }
    .studio-hero {
        background: #FFFFFF;
        color: #1A1A1A;
        border-left: 4px solid #D8B280;
        border-radius: 0 0.65rem 0.65rem 0;
        padding: 0.75rem 1rem;
        margin: 0.3rem 0 1rem 0;
    }
    [data-testid="stMetric"] {
        background: #FFFFFF !important;
        color: #1A1A1A !important;
        border: 1px solid #E0E0E0;
        border-top: 3px solid #D8B280;
        border-radius: 0.7rem;
        padding: 0.8rem 0.95rem;
    }
    [data-testid="stMetricLabel"] p { color: #8F654D !important; }
    [data-testid="stMetricValue"] { color: #1A1A1A !important; }
    [data-testid="stAlert"] {
        background: #29241B !important;
        color: #FFFFFF !important;
        border-color: #514534 !important;
        border-left: 4px solid #A66F72 !important;
    }
    [data-testid="stAlert"] > div { background: #29241B !important; }
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] strong,
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
        background: transparent !important;
        color: #FFFFFF !important;
    }
    button[kind="primary"] {
        background: #D8B280 !important;
        border-color: #D8B280 !important;
        color: #1A1A1A !important;
    }
    .stTabs [aria-selected="true"] { color: #8F654D !important; }
    [data-testid="stDataFrame"] {
        background: #FFFFFF !important;
        border: 1px solid #E0E0E0;
        border-radius: 0.65rem;
    }
    .diagnostic-card {
        background: #F8F5F0;
        color: #1A1A1A;
        border: 1px solid #E0E0E0;
        border-left: 4px solid #D8B280;
        border-radius: 0.65rem;
        padding: 1rem 1.15rem;
        margin: 0.5rem 0 1rem;
        line-height: 1.65;
        overflow-wrap: anywhere;
    }
    .observation-table-wrap {
        width: 100%;
        overflow-x: auto;
        margin: 0.4rem 0 1rem;
        border: 1px solid #3B3936;
        border-radius: 0.65rem;
    }
    table.observation-table {
        width: 100%;
        table-layout: fixed;
        border-collapse: collapse;
        background: #1E1C1A;
        color: #F4F4F4;
        font-size: 0.95rem;
    }
    .observation-table .competitor-col { width: 14%; }
    .observation-table .observation-col { width: 76%; }
    .observation-table .source-col { width: 10%; }
    .observation-table th, .observation-table td {
        padding: 0.75rem 0.85rem;
        text-align: left;
        vertical-align: top;
        border-bottom: 1px solid #3B3936;
        overflow-wrap: anywhere;
        white-space: normal;
        line-height: 1.5;
    }
    .observation-table th {
        background: #302D29;
        color: #D0D0D0;
        font-weight: 600;
    }
    .observation-table td { background: #1E1C1A; color: #F4F4F4; }
    .observation-table tbody tr:nth-child(even) td { background: #242220; }
    .observation-table tbody tr:last-child td { border-bottom: 0; }
    .observation-source-link {
        display: inline-block;
        padding: 0.12rem 0.4rem;
        border-radius: 0.3rem;
        background: #D8B280;
        color: #1A1A1A !important;
        text-decoration: none !important;
        white-space: nowrap;
        font-size: 0.86rem;
    }
    .observation-source-link:hover { background: #E4C79F; }
    .recommendation-table-wrap {
        width: 100%;
        overflow-x: auto;
        margin: 0.4rem 0 1rem;
        border: 1px solid #3B3936;
        border-radius: 0.65rem;
    }
    table.recommendation-table {
        width: 100%;
        table-layout: fixed;
        border-collapse: collapse;
        background: #1E1C1A;
        color: #F4F4F4;
        font-size: 0.95rem;
    }
    .recommendation-table .problem-col { width: 23%; }
    .recommendation-table .priority-col { width: 8%; }
    .recommendation-table .action-col { width: 35%; }
    .recommendation-table .result-col { width: 34%; }
    .recommendation-table .solution-col { width: 24%; }
    .recommendation-table .description-col { width: 52%; }
    .recommendation-table .trigger-col { width: 24%; }
    .recommendation-table th, .recommendation-table td {
        padding: 0.75rem 0.85rem;
        text-align: left;
        vertical-align: top;
        border-bottom: 1px solid #3B3936;
        overflow-wrap: anywhere;
        white-space: normal;
        line-height: 1.5;
    }
    .recommendation-table th {
        background: #302D29;
        color: #D0D0D0;
        font-weight: 600;
    }
    .recommendation-table td { background: #1E1C1A; color: #F4F4F4; }
    .recommendation-table tbody tr:nth-child(even) td { background: #242220; }
    .recommendation-table tbody tr:last-child td { border-bottom: 0; }
    </style>
    """,
    unsafe_allow_html=True
)

logo_column, heading_column = st.columns([1.8, 4.2], vertical_alignment="center")
with logo_column:
    if LOGO_PATH.is_file():
        st.image(str(LOGO_PATH), width=200)
with heading_column:
    st.title("Tableau de bord")
    st.markdown(
        """
        <div class="studio-hero">
            Veille concurrentielle et visibilité IA<br>
            <span style="color:#8F654D">Données réelles · affichage en lecture seule</span>
        </div>
        """,
        unsafe_allow_html=True
    )

competitors_data = read_json("competitors.json") or {}
analysis_data = read_json("competitors_analysis.json") or {}
visibility_data = read_json("visibility_history.json") or {}
competitor_history_data = read_json("history.json") or {}
recommendations_data = read_json("recommendations.json")
comparisons = [
    item for item in read_json_lines("comparisons.json")
    if (item.get("provider") or "Groq") == "Groq"
]
alerts = [
    item for item in read_json_lines("alerts.json")
    if (item.get("provider") or "Groq") == "Groq"
]

competitors = competitors_data.get("competitors", [])
analyses = analysis_data.get("analyses", [])
history = visibility_data.get("history", [])
competitor_history = competitor_history_data.get("history", [])
if not isinstance(competitors, list):
    competitors = []
if not isinstance(analyses, list):
    analyses = []
if not isinstance(history, list):
    history = []
if not isinstance(competitor_history, list):
    competitor_history = []

using_historical_analyses = False
if not analyses:
    for historical_run in reversed(competitor_history):
        previous_analyses = historical_run.get("analyses", []) if isinstance(historical_run, dict) else []
        if isinstance(previous_analyses, list) and previous_analyses:
            analyses = previous_analyses
            using_historical_analyses = True
            break

latest = latest_complete_run(history) or (history[-1] if history and isinstance(history[-1], dict) else {})
latest_results = latest.get("results", [])
if not isinstance(latest_results, list):
    latest_results = []
latest_results = [
    row for row in latest_results
    if isinstance(row, dict) and get_provider_name(row) == "Groq"
]
successful_tests = sum(
    row.get("status", "success") == "success"
    for row in latest_results
)

st.header("Vue d'ensemble")
overview = st.columns(3)
overview[0].metric("Concurrents analysés", len(analyses))
overview[1].metric("Tests IA - derniere mesure complete", len(latest_results))
overview[1].caption(f"{successful_tests} réponses réussies")
overview[2].metric("Alertes enregistrées", len(alerts))

render_visibility(history)
render_competitors(competitors, analyses, using_historical_analyses)
render_evolution(comparisons, alerts, competitor_history)
render_recommendations(recommendations_data)

missing_files = [
    filename
    for filename, value in (
        ("competitors.json", competitors_data),
        ("competitors_analysis.json", analysis_data),
        ("visibility_history.json", visibility_data),
        ("history.json", competitor_history_data),
        ("recommendations.json", recommendations_data)
    )
    if value is None
]
if missing_files:
    st.caption("Résultats absents ou illisibles : " + ", ".join(missing_files))
