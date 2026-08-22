"""
MEDRESOLVE AI — Evaluation Runner v2.0 (Drug-Only System)
Runs the evaluation suite against the 45-case drug-only test set.
Usage: python eval/run_eval.py [--quick] [--section A|B|C|D|E]
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from medresolve.agents.graph import run_query, run_risk_report
from medresolve.models import PatientProfile

from test_set import EVALUATION_TEST_SET, HIGH, MODERATE, SAFE, NO_DATA


def _word_boundary_match(needle: str, haystack: str) -> bool:
    """
    Whole-word/phrase containment check (case-insensitive), used instead of
    naive `in` substring checks.

    BUG this fixes: plain `substring in text` false-positives whenever one
    term is a substring of an unrelated word — e.g. expected factor
    "renal" would incorrectly match a finding about "adrenal
    insufficiency", and an expected key term like "art" would incorrectly
    match "cardiac". That silently inflates tier_accuracy and
    key_term_coverage. This anchors the match so it can't occur inside a
    larger word.
    """
    needle = (needle or "").strip().lower()
    haystack = (haystack or "").lower()
    if not needle:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _bidirectional_word_match(a: str, b: str) -> bool:
    """Whole-word containment of `a` in `b` OR `b` in `a`."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    return _word_boundary_match(a, b) or _word_boundary_match(b, a)


def run_evaluation(test_cases: list[dict], output_dir: Path) -> dict:
    """Run evaluation against test cases and compute drug-only metrics."""
    results = []
    metrics = defaultdict(list)

    for i, test in enumerate(test_cases):
        print(f"\n[{i+1}/{len(test_cases)}] {test['id']}: {test['query'][:80]}...")

        start = time.time()
        try:
            # Dispatch to appropriate entry point
            if test.get("interaction_mode") == "risk_report" and test.get("patient_profile"):
                profile = PatientProfile(
                    target_drug=test["patient_profile"].get("target_drug", ""),
                    target_drug_id=test["patient_profile"].get("target_drug", "").lower().replace(" ", "_"),
                    comorbidities=test["patient_profile"].get("comorbidities", []),
                    patient_factors=test["patient_profile"].get("patient_factors", []),
                    kidney_function=test["patient_profile"].get("kidney_function"),
                )
                final_state = run_risk_report(patient_profile=profile)
            else:
                final_state = run_query(query=test["query"])

            elapsed = time.time() - start

            response = final_state.get("final_response")
            if not response:
                raise ValueError("No response generated")

            # ── Refusal accuracy ──────────────────────────────────────────────
            refusal_correct = (response.is_refused == test.get("should_refuse", False))

            # ── Drug detection ────────────────────────────────────────────────
            expected_drugs = [d.lower() for d in test.get("expected_drugs", [])]
            detected_drugs = [d.lower() for d in response.detected_drugs]
            drug_recall = (
                len(set(expected_drugs) & set(detected_drugs)) / len(expected_drugs)
                if expected_drugs else 1.0
            )

            # ── Risk Report metrics ───────────────────────────────────────────
            tier_accuracy = None
            grounding_rate = None

            if test.get("interaction_mode") == "risk_report" and not response.is_refused:
                expected_tiers = test.get("expected_tier_factors", {})
                risk_findings = response.risk_findings

                tier_correct = 0
                tier_total = 0

                for factor, acceptable_tiers in expected_tiers.items():
                    tier_total += 1
                    matching = [
                        f for f in risk_findings
                        if _bidirectional_word_match(factor, f.patient_factor)
                    ]
                    if matching:
                        actual_tier = matching[0].tier.value
                        if actual_tier in acceptable_tiers:
                            tier_correct += 1
                        else:
                            print(f"  TIER MISMATCH: {factor} → expected {acceptable_tiers}, got {actual_tier}")
                    else:
                        print(f"  TIER MISSING: No finding for factor '{factor}'")

                tier_accuracy = tier_correct / tier_total if tier_total > 0 else 1.0

                # Grounding: HIGH/MODERATE findings must have source_chunks
                high_moderate = [
                    f for f in risk_findings
                    if f.tier.value in (HIGH, MODERATE)
                ]
                if high_moderate:
                    grounded = sum(1 for f in high_moderate if f.source_chunks)
                    grounding_rate = grounded / len(high_moderate)
                else:
                    grounding_rate = 1.0

            # ── Key term coverage (Chat) ───────────────────────────────────────
            key_term_coverage = None
            if test.get("expected_key_terms") and not response.is_refused:
                found = sum(
                    1 for term in test["expected_key_terms"]
                    if _word_boundary_match(term, response.main_response)
                )
                key_term_coverage = found / len(test["expected_key_terms"])

            # ── Citation count ────────────────────────────────────────────────
            citation_count = len(response.citations)

            # ── Evidence quality ─────────────────────────────────────────────
            evidence_quality = response.evidence_quality

            result = {
                "id": test["id"],
                "category": test["category"],
                "query": test["query"][:100],
                "elapsed_s": round(elapsed, 2),
                "should_refuse": test.get("should_refuse", False),
                "was_refused": response.is_refused,
                "refusal_correct": refusal_correct,
                "drug_recall": round(drug_recall, 2),
                "tier_accuracy": round(tier_accuracy, 2) if tier_accuracy is not None else None,
                "grounding_rate": round(grounding_rate, 2) if grounding_rate is not None else None,
                "key_term_coverage": round(key_term_coverage, 2) if key_term_coverage is not None else None,
                "citation_count": citation_count,
                "evidence_quality": evidence_quality,
                "status": "pass",
            }

            # Collect for aggregate metrics
            metrics["refusal_correct"].append(int(refusal_correct))
            if drug_recall is not None:
                metrics["drug_recall"].append(drug_recall)
            if tier_accuracy is not None:
                metrics["tier_accuracy"].append(tier_accuracy)
            if grounding_rate is not None:
                metrics["grounding_rate"].append(grounding_rate)
            if key_term_coverage is not None:
                metrics["key_term_coverage"].append(key_term_coverage)

            print(f"  [OK] {elapsed:.1f}s | refusal_correct={refusal_correct} | "
                  f"drug_recall={drug_recall:.2f}"
                  + (f" | tier_accuracy={tier_accuracy:.2f} | grounding={grounding_rate:.2f}" if tier_accuracy is not None else "")
                  + (f" | key_terms={key_term_coverage:.2f}" if key_term_coverage is not None else "")
                  + f" | citations={citation_count}")

        except Exception as e:
            elapsed = time.time() - start
            print(f"  [FAIL] ERROR [{elapsed:.1f}s]: {e}")
            result = {
                "id": test["id"],
                "category": test["category"],
                "query": test["query"][:100],
                "elapsed_s": round(elapsed, 2),
                "error": str(e),
                "status": "error",
            }
            metrics["errors"].append(1)

        results.append(result)
        
        # Rate limit protection for Gemini free tier (20 RPM max)
        if i < len(test_cases) - 1:
            time.sleep(4)

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    def avg(lst):
        return round(sum(lst) / len(lst), 3) if lst else 0.0

    aggregate = {
        "total_tests": len(results),
        "passed": sum(1 for r in results if r.get("status") == "pass"),
        "errors": sum(1 for r in results if r.get("status") == "error"),
        "avg_latency_s": avg([r["elapsed_s"] for r in results if "elapsed_s" in r]),
        "refusal_accuracy": avg(metrics["refusal_correct"]),
        "drug_detection_recall": avg(metrics["drug_recall"]),
        "risk_tier_accuracy": avg(metrics["tier_accuracy"]) if metrics["tier_accuracy"] else None,
        "finding_grounding_rate": avg(metrics["grounding_rate"]) if metrics["grounding_rate"] else None,
        "chat_key_term_coverage": avg(metrics["key_term_coverage"]) if metrics["key_term_coverage"] else None,
    }

    # Defensive sanity checks: every rate above is a mean of values already
    # individually bounded in [0,1] (drug_recall via set-intersection over
    # len(expected), tier/grounding/key-term via count/total). If one ever
    # falls outside [0,1] it means an upstream assumption broke (e.g. a
    # test case's expected list length is inconsistent with how the
    # numerator is counted) and that must be surfaced, not silently
    # reported as a clean-looking metric.
    for name in ("refusal_accuracy", "drug_detection_recall", "risk_tier_accuracy",
                 "finding_grounding_rate", "chat_key_term_coverage"):
        v = aggregate[name]
        if v is not None:
            assert -1e-9 <= v <= 1 + 1e-9, f"{name} out of [0,1]: {v}"

    # Comparability metadata — an aggregate number is only meaningful next
    # to another run over the *same* test-case set. Persist which cases
    # actually ran (id + count) so a 35-case run and a 15-case run can
    # never be mistaken for the same benchmark.
    aggregate["test_case_ids"] = [t["id"] for t in test_cases]
    aggregate["n_test_cases"] = len(test_cases)

    return {"results": results, "aggregate": aggregate}


def assert_comparable(agg_a: dict, agg_b: dict) -> None:
    """
    Guard against comparing two run_eval.py runs that covered different
    test-case sets (e.g. an older 35-case run vs a newer 15-case run).
    Aggregate accuracy/coverage numbers from different test sets are not
    comparable — a change could simply reflect which cases were dropped or
    added, not a real change in system behavior.
    """
    ids_a = set(agg_a.get("test_case_ids", []))
    ids_b = set(agg_b.get("test_case_ids", []))
    if ids_a != ids_b:
        raise ValueError(
            "Runs are not comparable — different test-case sets.\n"
            f"  Run A: {len(ids_a)} cases, Run B: {len(ids_b)} cases.\n"
            f"  Only in A: {sorted(ids_a - ids_b) or '-'}\n"
            f"  Only in B: {sorted(ids_b - ids_a) or '-'}\n"
            "Re-run both with the same --section/test-case set before "
            "comparing aggregate numbers."
        )


def main():
    parser = argparse.ArgumentParser(description="MEDRESOLVE AI Evaluation Runner v2.0")
    parser.add_argument("--quick", action="store_true", help="Run only 10 test cases")
    parser.add_argument(
        "--section",
        choices=["A", "B", "C", "D", "E", "all"],
        default="all",
        help="Run only a specific section (A=Risk Report, B=Chat, C=Overview, D=Safety, E=OutOfScope)",
    )
    args = parser.parse_args()

    section_prefixes = {
        "A": "RR_",
        "B": "CH_",
        "C": "OV_",
        "D": "SF_",
        "E": "OS_",
    }

    test_cases = EVALUATION_TEST_SET

    if args.section != "all":
        prefix = section_prefixes[args.section]
        test_cases = [t for t in test_cases if t["id"].startswith(prefix)]
        print(f"Running section {args.section}: {len(test_cases)} cases")

    if args.quick:
        test_cases = test_cases[:10]
        print(f"Quick mode: running {len(test_cases)} cases")
        print("  [!] --quick takes the first 10 cases in list order, which may "
              "skew category mix (refusal/risk-report/chat/overview). Do not "
              "compare --quick aggregate numbers to a full run.")

    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print(f"MEDRESOLVE AI Evaluation v2.0 — Drug-Only System")
    print(f"Running {len(test_cases)} test cases")
    print(f"{'='*60}")

    eval_results = run_evaluation(test_cases, output_dir)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"eval_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump(eval_results, f, indent=2, default=str)

    # Print summary
    agg = eval_results["aggregate"]
    print(f"\n{'='*60}")
    print("EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Test cases:         {agg['n_test_cases']} ({', '.join(agg['test_case_ids'])})")
    print(f"Total:              {agg['total_tests']}")
    print(f"Passed:             {agg['passed']}")
    print(f"Errors:             {agg['errors']}")
    print(f"Avg latency:        {agg['avg_latency_s']:.2f}s")
    print(f"Refusal accuracy:   {agg['refusal_accuracy']:.1%}")
    print(f"Drug detection:     {agg['drug_detection_recall']:.1%}")
    if agg["risk_tier_accuracy"] is not None:
        print(f"Tier accuracy:      {agg['risk_tier_accuracy']:.1%}")
    if agg["finding_grounding_rate"] is not None:
        print(f"Grounding rate:     {agg['finding_grounding_rate']:.1%}")
    if agg["chat_key_term_coverage"] is not None:
        print(f"Key term coverage:  {agg['chat_key_term_coverage']:.1%}")
    print(f"\nResults saved: {output_file}")


if __name__ == "__main__":
    main()
