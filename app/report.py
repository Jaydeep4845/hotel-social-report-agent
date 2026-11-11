"""Builds a report for ONE client: metrics -> findings -> (optional) LLM wording."""

from app import db, insights, llm
from app.metrics import build_metrics


def generate(client_id):
    client = db.get_client(client_id)
    if not client:
        raise LookupError(client_id)

    metrics = build_metrics(db.get_posts(client_id))
    findings = insights.build_findings(metrics)
    summary, rewritten, llm_info = llm.phrase_findings(client["name"], metrics, findings)

    items = []
    for f in findings:
        item = dict(f)
        item["template_text"] = f["text"]
        if f["id"] in rewritten:
            item.update(rewritten[f["id"]])
            item["source"] = "llm"
        else:
            item["source"] = "template"
        items.append(item)

    payload = {
        "client": {"id": client["id"], "name": client["name"], "city": client["city"]},
        "period": metrics["period"],
        "period_label": insights.month_name(metrics["period"]),
        "previous_period": metrics["previous_period"],
        "summary": summary or insights.template_summary(client["name"], metrics, findings),
        "summary_source": "llm" if summary else "template",
        "metrics": metrics,
        "insights": items,
        "generation": llm_info,
    }
    report_id = db.create_report(client_id, metrics["period"], payload)
    source = f"LLM ({llm_info['model']})" if llm_info.get("used") else "templates"
    db.log(client_id, "report_generated", report_id, note=f"{len(items)} insights, wording: {source}")
    return report_id
