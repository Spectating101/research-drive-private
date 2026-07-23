#!/usr/bin/env bash
# Single research platform entrypoint (status, daily cycle, audit, query engine).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"

MODE="${1:-status}"

case "${MODE}" in
  status)
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/platform_status.py"
    ;;
  cycle)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/run_unified_platform_cycle.py" "$@"
    ;;
  audit)
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/investment_research_engine_audit.py"
    ;;
  capabilities)
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/investment_capability_audit.py"
    ;;
  repo-inventory)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/investment_repo_inventory.py" "$@"
    ;;
  data-status)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/stock_investment_data_status.py" status "$@"
    ;;
  ideas)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/alpha_idea_queue.py" "$@"
    ;;
  thesis)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/thesis_report.py" "$@"
    ;;
  thesis-gates)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/thesis_gates.py" "$@"
    ;;
  manifest-gates)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/manifest_gates.py" "$@"
    ;;
  decisions)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/frozen_decision_tracker.py" "$@"
    ;;
  reconcile)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/accounting_reconcile.py" "$@"
    ;;
  accounting-bundle)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/accounting_bundle.py" "$@"
    ;;
  agent-tool)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/investment_agent_tools.py" "$@"
    ;;
  alpha)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/alpha_live_cycle.py" "$@"
    ;;
  enforce)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/investment_enforcement_cycle.py" "$@"
    ;;
  operator)
    shift || true
    exec "${SR_PYTHON}" "${SR_DIR}/scripts/investment_operator_dashboard.py" "$@"
    ;;
  query-engine)
    exec bash "${SR_DIR}/scripts/run_research_query_engine.sh"
    ;;
  *)
    echo "Usage: $0 {status|cycle|audit|capabilities|repo-inventory|data-status|ideas|thesis|thesis-gates|manifest-gates|decisions|reconcile|accounting-bundle|agent-tool|alpha|enforce|operator|query-engine} [args...]"
    exit 2
    ;;
esac
