"""Research integrity tooling: fingerprinting, DSR/PBO, attribution, costs, factors."""

from src.research.fingerprint import make_fingerprint, stamp
from src.research.accounting_bundle import build_accounting_bundle
from src.research.alpha_idea_jobs import generate_idea_validation_jobs
from src.research.capability_audit import audit_capabilities
from src.research.alpha_idea_queue import idea_queue_report, upsert_idea
from src.research.execution_safety import validate_target_weights
from src.research.frozen_decisions import decision_report, evaluate_decisions, freeze_decision
from src.research.investment_enforcement import run_investment_enforcement_cycle
from src.research.investment_cockpit import (
    compute_factor_tearsheet,
    construct_portfolio_from_scores,
    register_candidate_run,
    simulate_paper_rebalance,
)
from src.research.manifest_gates import manifest_gate_report
from src.research.operator_dashboard import build_operator_dashboard
from src.research.repo_inventory import build_repo_inventory

__all__ = [
    "audit_capabilities",
    "build_accounting_bundle",
    "build_operator_dashboard",
    "build_repo_inventory",
    "compute_factor_tearsheet",
    "decision_report",
    "evaluate_decisions",
    "freeze_decision",
    "generate_idea_validation_jobs",
    "idea_queue_report",
    "construct_portfolio_from_scores",
    "manifest_gate_report",
    "make_fingerprint",
    "register_candidate_run",
    "run_investment_enforcement_cycle",
    "simulate_paper_rebalance",
    "stamp",
    "upsert_idea",
    "validate_target_weights",
]
