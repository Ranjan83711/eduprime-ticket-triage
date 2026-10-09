"""Run the labelled test set through the pipeline and write eval/report.json.

    python -m eval.run_eval              # uses cached results where available
    python -m eval.run_eval --no-cache   # force fresh LLM calls
    python -m eval.run_eval --delay 4    # seconds between tickets (free-tier rate limits)

Metrics: category accuracy / F1, escalation precision & recall, unsafe auto-replies, sentiment,
citation validity, latency, cost, and a sweep of the auto-reply confidence threshold. The sweep
reuses stored outputs and only re-runs the (deterministic) escalation rule, so it costs nothing.
"""
import argparse
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.preprocessing import MultiLabelBinarizer

from app.config import (
    AUTO_REPLY_CONFIDENCE, BACKEND_DIR, CLASSIFIER_MODEL, DATA_DIR, DRAFTER_MODEL, FALLBACK_MODEL, TEST_SET_PATH,
)
from app.escalation import decide
from app.schemas import TriageResult
from app.triage import CACHE_DIR, _cache_key, triage

CATEGORIES = ["refund", "payment", "batch_access", "technical", "academic_doubt", "other"]
REPORT_PATH = BACKEND_DIR / "eval" / "report.json"
HOLDOUT_PATH = DATA_DIR / "tickets" / "holdout_set.json"
SEED_IDS = ["T01", "T08", "T12", "T19", "T28", "T29", "T36", "T38", "T51", "T57", "T58", "T60"]


def escalation_metrics(gold: list[str], pred: list[str]) -> dict:
    tp = sum(g == p == "escalate" for g, p in zip(gold, pred))
    fp = sum(g == "auto_reply" and p == "escalate" for g, p in zip(gold, pred))
    fn = sum(g == "escalate" and p == "auto_reply" for g, p in zip(gold, pred))
    n = len(gold)
    return {
        "accuracy": round(sum(g == p for g, p in zip(gold, pred)) / n, 3),
        "escalation_precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
        "escalation_recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
        # The costly error: a ticket that needed a human got an automatic reply.
        "unsafe_auto_replies": fn,
        # The other error: a human handled something the bot could have answered.
        "unnecessary_escalations": fp,
        "auto_reply_rate": round(sum(p == "auto_reply" for p in pred) / n, 3),
    }


def threshold_sweep(tickets: list[dict], results: list[TriageResult]) -> list[dict]:
    rows = []
    gold = [t["gold_decision"] for t in tickets]
    for i in range(0, 21):
        th = round(i * 0.05, 2)
        pred = [decide(r.precheck, r.classification, r.draft if r.classification else None,
                       r.citation_checks, threshold=th).decision for r in results]
        rows.append({"threshold": th, **escalation_metrics(gold, pred)})
    return rows


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def run(use_cache: bool, delay: float, limit: int | None, path=TEST_SET_PATH, write: bool = True) -> dict:
    tickets = json.loads(path.read_text(encoding="utf-8"))[:limit]
    results: list[TriageResult] = []
    fresh_latencies = []
    for i, t in enumerate(tickets, 1):
        cached = use_cache and (CACHE_DIR / f"{_cache_key(t['text'], t['channel'])}.json").exists()
        r = triage(t["text"], t["channel"], use_cache=use_cache)
        results.append(r)
        if not cached and r.llm_calls:
            fresh_latencies.append(r.total_latency_ms)
        status = "cache" if cached else f"{r.total_latency_ms}ms"
        print(f"[{i:2}/{len(tickets)}] {t['id']} {r.decision.decision:10} gold={t['gold_decision']:10} "
              f"{status}{'  ERROR: ' + r.error[:80] if r.error else ''}", flush=True)
        if not cached and r.llm_calls and i < len(tickets):
            time.sleep(delay)

    # ---- classification ----
    classified = [(t, r) for t, r in zip(tickets, results) if r.classification]
    gold_sets = [t["gold_categories"] for t, _ in classified]
    pred_sets = [r.classification.categories for _, r in classified]
    mlb = MultiLabelBinarizer(classes=CATEGORIES)
    yg, yp = mlb.fit_transform(gold_sets), mlb.transform(pred_sets)
    p, rc, f1, sup = precision_recall_fscore_support(yg, yp, zero_division=0)
    micro = precision_recall_fscore_support(yg, yp, average="micro", zero_division=0)
    primary_gold = [g[0] for g in gold_sets]
    primary_pred = [pr[0] for pr in pred_sets]
    cm = confusion_matrix(primary_gold, primary_pred, labels=CATEGORIES).tolist()

    # ---- escalation ----
    gold_dec = [t["gold_decision"] for t in tickets]
    pred_dec = [r.decision.decision for r in results]

    # ---- sentiment ----
    sent_pairs = [(t["gold_sentiment"], r.classification.sentiment) for t, r in classified]
    angry_gold = [i for i, (g, _) in enumerate(sent_pairs) if g == "angry"]

    # ---- citations ----
    drafts_with_cites = [r for r in results if r.draft and r.draft.citations]
    all_checks = [c for r in results for c in r.citation_checks]

    # ---- cost / latency ----
    calls = [c for r in results for c in r.llm_calls]
    models_used = Counter(c.model for c in calls)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {"classifier": CLASSIFIER_MODEL, "drafter": DRAFTER_MODEL, "fallback": FALLBACK_MODEL,
                   "auto_reply_threshold": AUTO_REPLY_CONFIDENCE},
        "n_tickets": len(tickets),
        "n_errors": sum(1 for r in results if r.error),
        "classification": {
            "n_classified": len(classified),
            "primary_accuracy": round(sum(g == pr for g, pr in zip(primary_gold, primary_pred)) / len(classified), 3)
            if classified else 0,
            "primary_in_gold": round(sum(pr[0] in g for g, pr in zip(gold_sets, pred_sets)) / len(classified), 3)
            if classified else 0,
            "exact_set_match": round(sum(set(g) == set(pr) for g, pr in zip(gold_sets, pred_sets)) / len(classified), 3)
            if classified else 0,
            "micro_precision": round(micro[0], 3), "micro_recall": round(micro[1], 3), "micro_f1": round(micro[2], 3),
            "per_class": [{"category": c, "precision": round(p[i], 3), "recall": round(rc[i], 3),
                           "f1": round(f1[i], 3), "support": int(sup[i])} for i, c in enumerate(CATEGORIES)],
            "confusion_matrix": {"labels": CATEGORIES, "matrix": cm},
        },
        "escalation": escalation_metrics(gold_dec, pred_dec),
        "sentiment": {
            "accuracy": round(sum(g == pr for g, pr in sent_pairs) / len(sent_pairs), 3) if sent_pairs else 0,
            "angry_recall": round(sum(sent_pairs[i][1] == "angry" for i in angry_gold) / len(angry_gold), 3)
            if angry_gold else 0,
        },
        "citations": {
            "drafts_with_citations": len(drafts_with_cites),
            "citations_total": len(all_checks),
            "citations_valid": sum(c.valid for c in all_checks),
            "validity_rate": round(sum(c.valid for c in all_checks) / len(all_checks), 3) if all_checks else 0,
            "drafts_all_valid": sum(all(c.valid for c in r.citation_checks) for r in drafts_with_cites),
        },
        "performance": {
            "llm_calls": len(calls),
            "fallback_calls": sum(c.fallback_used for c in calls),
            "models_used": dict(models_used),
            "latency_ms_p50": pct(fresh_latencies, 0.5),
            "latency_ms_p95": pct(fresh_latencies, 0.95),
            "latency_samples": len(fresh_latencies),
            "avg_tokens_per_ticket": round(sum(c.input_tokens + c.output_tokens for c in calls) / len(tickets)),
            "avg_cost_usd_per_ticket_paid_tier": round(sum(r.total_cost_usd for r in results) / len(tickets), 6),
            "cost_per_1000_tickets_usd_paid_tier": round(1000 * sum(r.total_cost_usd for r in results) / len(tickets), 3),
        },
        "threshold_sweep": threshold_sweep(tickets, results),
        "tickets": [
            {
                "id": t["id"], "text": t["text"], "language": t["language"], "notes": t["notes"],
                "gold_categories": t["gold_categories"], "gold_decision": t["gold_decision"],
                "gold_sentiment": t["gold_sentiment"],
                "pred_categories": r.classification.categories if r.classification else [],
                "pred_decision": r.decision.decision, "pred_sentiment": r.classification.sentiment if r.classification else None,
                "confidence": r.classification.confidence if r.classification else None,
                "team": r.decision.team, "reasons": r.decision.reasons,
                "citations_valid": all(c.valid for c in r.citation_checks),
                "latency_ms": r.total_latency_ms, "error": r.error,
            }
            for t, r in zip(tickets, results)
        ],
    }
    if not write:
        return report
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    seed = [r.model_dump(mode="json") for t, r in zip(tickets, results) if t["id"] in SEED_IDS and not r.error]
    (DATA_DIR / "seed_results.json").write_text(json.dumps(seed, indent=1), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--delay", type=float, default=6.0)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    rep = run(use_cache=not args.no_cache, delay=args.delay, limit=args.limit)
    # Held-out tickets were written after prompt tuning on the main set and never used to tune it,
    # so they show whether the numbers above generalise.
    print("\n--- held-out set ---")
    ho = run(use_cache=not args.no_cache, delay=args.delay, limit=None, path=HOLDOUT_PATH, write=False)
    rep["holdout"] = {"n_tickets": ho["n_tickets"], "n_errors": ho["n_errors"],
                      "classification": {k: ho["classification"][k] for k in ("primary_accuracy", "micro_f1", "exact_set_match")},
                      "escalation": ho["escalation"], "citations": ho["citations"], "sentiment": ho["sentiment"],
                      "tickets": ho["tickets"]}
    REPORT_PATH.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    rep["n_errors"] += ho["n_errors"]
    c, e = rep["classification"], rep["escalation"]
    print("\n=== Summary ===")
    print(f"tickets={rep['n_tickets']} errors={rep['n_errors']}")
    print(f"category: primary_acc={c['primary_accuracy']} micro_f1={c['micro_f1']} exact_set={c['exact_set_match']}")
    print(f"escalation: acc={e['accuracy']} precision={e['escalation_precision']} recall={e['escalation_recall']} "
          f"unsafe_auto={e['unsafe_auto_replies']} unnecessary_esc={e['unnecessary_escalations']}")
    print(f"sentiment: {rep['sentiment']}  citations: {rep['citations']}")
    print(f"performance: {rep['performance']}")
    h = rep["holdout"]
    print(f"held-out: category={h['classification']['primary_accuracy']} escalation={h['escalation']}")
    print(f"report -> {REPORT_PATH}")
    sys.exit(1 if rep["n_errors"] else 0)


if __name__ == "__main__":
    main()
