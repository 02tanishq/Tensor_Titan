"""
Ujjwal Rail Rules & Settings Integrity Validation Script.
Validates:
1. Every setting has a source_doc that exists in rules or circulars.
2. Every circular has a valid effective_date (effective_from).
3. Every amends / modifies_rule reference points to a real document.
4. Every outdated FAQ points to an existing superseding circular or rule.
5. All required refund calculation parameters exist in the settings table.
6. Print a comprehensive pass/fail audit report for dev startup.
"""

import sys
import os
import sqlite3

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from RAG_pipeline.repository import RulesRepository, MissingSettingError


def validate_rules(db_path: str = "data/ujjwal_rail.db") -> bool:
    print("=" * 60)
    print("      UJJWAL RAIL RULES & SETTINGS INTEGRITY AUDIT      ")
    print("=" * 60)

    if not os.path.exists(db_path):
        print(f"[FAIL] Database file not found at: {db_path}")
        return False

    repo = RulesRepository(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    errors = []
    warnings = []
    passes = []

    # 1. Collect all real doc_ids
    c.execute("SELECT doc_id FROM rules;")
    rule_ids = {r[0] for r in c.fetchall()}

    c.execute("SELECT doc_id FROM circulars;")
    circ_ids = {r[0] for r in c.fetchall()}

    c.execute("SELECT faq_id FROM faqs;")
    faq_ids = {r[0] for r in c.fetchall()}

    all_doc_ids = rule_ids | circ_ids | faq_ids

    # 2. Check settings source_doc references
    c.execute("SELECT name, value, source_doc FROM settings;")
    settings = c.fetchall()

    for s in settings:
        src = s["source_doc"]
        if src in all_doc_ids:
            passes.append(f"[PASS] Setting '{s['name']}' ({s['value']}) correctly references source '{src}'")
        else:
            # Special case: RUL-SYS-01 is an internal system rule tag
            if src == "RUL-SYS-01":
                warnings.append(f"[WARN] Setting '{s['name']}' references system tag '{src}' (not in rules table)")
            else:
                errors.append(f"[FAIL] Setting '{s['name']}' references non-existent source '{src}'")

    # 3. Check every circular has valid effective_date
    c.execute("SELECT doc_id, effective_date, modifies_rule FROM circulars;")
    circulars = c.fetchall()
    for circ in circulars:
        eff = circ["effective_date"]
        if eff and len(eff) == 10 and eff[4] == '-' and eff[7] == '-':
            passes.append(f"[PASS] Circular '{circ['doc_id']}' has valid effective date '{eff}'")
        else:
            errors.append(f"[FAIL] Circular '{circ['doc_id']}' missing or malformed effective_date '{eff}'")

        # Check modifies_rule reference
        mod = circ["modifies_rule"]
        if mod is not None:
            if mod in rule_ids:
                passes.append(f"[PASS] Circular '{circ['doc_id']}' correctly amends existing rule '{mod}'")
            else:
                errors.append(f"[FAIL] Circular '{circ['doc_id']}' modifies unknown rule '{mod}'")

    # 4. Check outdated FAQs have valid superseded_by
    c.execute("SELECT faq_id, is_outdated, superseded_by FROM faqs WHERE is_outdated = 1;")
    outdated_faqs = c.fetchall()
    for f in outdated_faqs:
        sup = f["superseded_by"]
        if sup in all_doc_ids:
            passes.append(f"[PASS] Outdated FAQ '{f['faq_id']}' properly references superseding doc '{sup}'")
        else:
            errors.append(f"[FAIL] Outdated FAQ '{f['faq_id']}' references unknown superseding doc '{sup}'")

    # 5. Check all critical refund calculation parameters exist
    required_refund_settings = [
        "cancel_charge_1AC_over_48h",
        "cancel_charge_2AC_over_48h",
        "cancel_charge_3AC_over_48h",
        "cancel_charge_SL_over_48h",
        "cancel_charge_2S_over_48h",
        "cancel_charge_pct_48h_to_12h",
        "cancel_charge_pct_12h_to_4h",
        "boarding_change_cutoff_hours",
        "train_late_refund_cutoff_hours",
        "action_expiry_minutes"  # or action_ttl_minutes
    ]

    for req_setting in required_refund_settings:
        try:
            val = repo.get_setting(req_setting)
            passes.append(f"[PASS] Refund calculator setting '{req_setting}' is present: {val.value}")
        except MissingSettingError:
            errors.append(f"[FAIL] Required calculator setting '{req_setting}' is missing from settings")

    conn.close()

    # Print Report
    print("\nAUDIT SUMMARY:")
    for p in passes[:8]:  # Print first 8 passes for brevity
        print(" ", p)
    print(f"  ... and {len(passes) - 8} more verification checks passed.")

    if warnings:
        print("\nAUDIT WARNINGS:")
        for w in warnings:
            print(" ", w)

    if errors:
        print("\nAUDIT ERRORS ENCOUNTERED:")
        for e in errors:
            print(" ", e)
        print("\n" + "=" * 60)
        print("          RULES INTEGRITY CHECK: FAILED                 ")
        print("=" * 60)
        return False
    else:
        print("\n" + "=" * 60)
        print("          RULES INTEGRITY CHECK: 100% PASSED            ")
        print("=" * 60)
        return True


if __name__ == "__main__":
    success = validate_rules()
    sys.exit(0 if success else 1)
