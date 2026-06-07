import ast
import subprocess
from pathlib import Path


def test_source_modules_do_not_define_duplicate_top_level_symbols():
    root = Path(__file__).resolve().parents[1]
    paths = [root / "app.py", *sorted((root / "src" / "quant_assistant").glob("*.py"))]
    duplicates = []

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        seen: dict[tuple[str, str], int] = {}
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            key = (type(node).__name__, node.name)
            if key in seen:
                duplicates.append(f"{path.relative_to(root)}:{node.lineno} duplicates line {seen[key]}: {node.name}")
            else:
                seen[key] = node.lineno

    assert duplicates == []


def test_verification_script_remains_read_only():
    root = Path(__file__).resolve().parents[1]
    script_text = (root / "scripts" / "verify_quant_assistant.ps1").read_text(encoding="utf-8").lower()

    required_checks = [
        "git status --short",
        "py -m py_compile app.py",
        "py -m pytest",
        "py -m quant_assistant.cli --config config.json --portfolio portfolio.json --no-live",
        "get-filehash",
        "cli no-write guard",
        "git diff --check",
    ]
    for check in required_checks:
        assert check in script_text

    forbidden_mutations = [
        "git add",
        "git commit",
        "git push",
        "--save-log",
        "save_portfolio",
        "set-content",
        "out-file",
        "new-item",
        "remove-item",
        "move-item",
        "copy-item",
    ]
    for forbidden in forbidden_mutations:
        assert forbidden not in script_text


def test_gitignore_keeps_generated_reports_ignored_and_handoff_audits_trackable():
    root = Path(__file__).resolve().parents[1]

    generated_report = subprocess.run(
        ["git", "check-ignore", "reports/report_2026-06-06.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert generated_report.returncode == 0, generated_report.stderr
    assert "reports/report_2026-06-06.md" in generated_report.stdout

    handoff_audit = subprocess.run(
        ["git", "check-ignore", "reports/final_verification_audit_2026-06-05.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert handoff_audit.returncode == 1, handoff_audit.stdout


def test_primary_runbooks_prefer_verified_windows_commands():
    root = Path(__file__).resolve().parents[1]
    claude_text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    readme_text = (root / "README.md").read_text(encoding="utf-8")

    runbook = claude_text.split("## Runbook", 1)[1].split("Deployment:", 1)[0]
    assert "py -m pip install -r requirements.txt" in runbook
    assert ".\\scripts\\verify_quant_assistant.ps1" in runbook
    assert "py -m streamlit run app.py" in runbook
    assert "python -m pytest" not in runbook
    assert "\nstreamlit run app.py" not in runbook

    assert "py -m streamlit run app.py" in readme_text
    assert ".\\scripts\\verify_quant_assistant.ps1" in readme_text


def test_change_set_selective_add_block_avoids_unrelated_artifacts():
    root = Path(__file__).resolve().parents[1]
    audit_text = (root / "reports" / "change_set_audit_2026-06-05.md").read_text(encoding="utf-8")
    suggested_add = audit_text.split("## Suggested Selective Add", 1)[1].split("## Verification", 1)[0]

    required_paths = [
        ".gitignore",
        "CLAUDE.md",
        "README.md",
        "app.py",
        "src/quant_assistant/analytics_panel.py",
        "src/quant_assistant/config.py",
        "src/quant_assistant/data_source_health.py",
        "src/quant_assistant/disk_cache.py",
        "src/quant_assistant/recommendation_view.py",
        "src/quant_assistant/schema.py",
        "src/quant_assistant/strategy.py",
        "src/quant_assistant/daily_report.py",
        "src/quant_assistant/history.py",
        "src/quant_assistant/import_review.py",
        "src/quant_assistant/importer.py",
        "src/quant_assistant/journal.py",
        "src/quant_assistant/llm_advisor.py",
        "src/quant_assistant/multi_agent.py",
        "src/quant_assistant/user_data.py",
        "tests/test_analytics_panel.py",
        "tests/test_cli.py",
        "tests/test_config.py",
        "tests/test_history.py",
        "tests/test_import_review.py",
        "tests/test_importer.py",
        "tests/test_journal.py",
        "tests/test_llm_advisor.py",
        "tests/test_multi_agent.py",
        "tests/test_recommendation_view.py",
        "tests/test_schema.py",
        "tests/test_strategy.py",
        "tests/test_code_health.py",
        "tests/test_daily_report.py",
        "tests/test_data_source_health.py",
        "tests/test_disk_cache.py",
        "tests/test_user_data.py",
        "scripts/verify_quant_assistant.ps1",
        "LAST_DAY_HANDOFF_2026-06-05.md",
        "reports/portfolio_snapshot_audit_2026-06-05.md",
        "reports/strategy_coverage_audit_2026-06-05.md",
        "reports/code_health_audit_2026-06-05.md",
        "reports/change_set_audit_2026-06-05.md",
        "reports/final_verification_audit_2026-06-05.md",
    ]
    for path in required_paths:
        assert path in suggested_add

    broad_add_patterns = [
        "git add .\n",
        "git add . ",
        "git add .`",
    ]
    for pattern in broad_add_patterns:
        assert pattern not in suggested_add

    forbidden_paths = [
        "portfolio.json",
        "config.json",
        "data/journal.csv",
        "codex_comfy_video_pipeline",
        "scripts/configure_idm_browser_integration.ps1",
        "idm-",
        "idm_",
        "main/",
        "pikachu_",
    ]
    for path in forbidden_paths:
        assert path not in suggested_add
