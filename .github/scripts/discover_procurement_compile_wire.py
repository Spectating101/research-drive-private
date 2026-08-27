from pathlib import Path


path = Path("drive/scripts/research_data_mcp/craft_collect.py")
text = path.read_text(encoding="utf-8")
old = """    plan = validate_generic_plan(plan)\n\n    return {\n"""
new = """    plan = validate_generic_plan(plan)\n    # Compile semantic acquisition intent into a runtime-owned execution contract.\n    # Composer may specify requirements; fresh cluster state remains authoritative\n    # for worker placement, reservations, leases, and retries.\n    from scripts.research_data_mcp.procurement_execution_contract import (\n        compile_procurement_execution_plan,\n    )\n\n    plan = compile_procurement_execution_plan(plan)\n\n    return {\n"""
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one craft validation seam, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("wired procurement execution compiler into craft_collect_plan")
