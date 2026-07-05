"""Tests for the release wrapper contract."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SHIP = ROOT / "scripts" / "ship"
HOOK = ROOT / "scripts" / "ship.d" / "before-release-commit"


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    pipeline_root = tmp_path / "pipeline"
    component = repo / "custom_components" / "btoddb_ha_music"
    scripts = repo / "scripts"
    repo.mkdir()
    component.mkdir(parents=True)
    scripts.mkdir()
    pipeline_scripts = pipeline_root / "scripts"
    pipeline_scripts.mkdir(parents=True)

    shutil.copy2(SHIP, scripts / "ship")
    (component / "manifest.json").write_text(
        json.dumps({"version": "v0.0.16"}, indent=2) + "\n"
    )
    write_executable(
        pipeline_scripts / "btb-ship-base",
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > "$BTB_BASE_ARGS_FILE"\n',
    )
    return repo, pipeline_root, component / "manifest.json"


def test_ship_translates_bump_from_manifest_to_base_set_version(tmp_path: Path) -> None:
    repo, pipeline_root, _manifest = make_repo(tmp_path)
    args_file = tmp_path / "args.txt"
    env = os.environ.copy()
    env["BTB_PIPELINE_ROOT"] = str(pipeline_root)
    env["BTB_BASE_ARGS_FILE"] = str(args_file)

    result = run(
        [str(repo / "scripts" / "ship"), "--dry-run", "--bump-minor"], repo, env
    )

    assert result.returncode == 0, result.stderr
    assert "Using next minor version from manifest.json: v0.1.0" in result.stdout
    assert args_file.read_text().splitlines() == [
        "--repo-root",
        str(repo),
        "--set-version",
        "v0.1.0",
        "--dry-run",
    ]


def test_ship_keeps_version_alias_for_explicit_releases(tmp_path: Path) -> None:
    repo, pipeline_root, _manifest = make_repo(tmp_path)
    args_file = tmp_path / "args.txt"
    env = os.environ.copy()
    env["BTB_PIPELINE_ROOT"] = str(pipeline_root)
    env["BTB_BASE_ARGS_FILE"] = str(args_file)

    result = run([str(repo / "scripts" / "ship"), "--version=v2.3.4"], repo, env)

    assert result.returncode == 0, result.stderr
    assert args_file.read_text().splitlines() == [
        "--repo-root",
        str(repo),
        "--set-version",
        "v2.3.4",
    ]


def test_ship_rejects_multiple_version_options(tmp_path: Path) -> None:
    repo, pipeline_root, _manifest = make_repo(tmp_path)
    env = os.environ.copy()
    env["BTB_PIPELINE_ROOT"] = str(pipeline_root)

    result = run(
        [str(repo / "scripts" / "ship"), "--bump-patch", "--set-version", "v1.2.3"],
        repo,
        env,
    )

    assert result.returncode == 2
    assert "choose only one version option" in result.stderr


def test_before_release_hook_builds_card_and_updates_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    manifest = repo / "custom_components" / "btoddb_ha_music" / "manifest.json"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"version": "v0.0.16"}, indent=2) + "\n")
    deploy_log = tmp_path / "deploy.log"
    write_executable(
        scripts / "deploy-card",
        f"#!/usr/bin/env bash\nprintf 'deployed\\n' > {deploy_log}\n",
    )
    hook = scripts / "ship.d" / "before-release-commit"
    hook.parent.mkdir()
    shutil.copy2(HOOK, hook)

    env = os.environ.copy()
    env["BTB_REPO_ROOT"] = str(repo)
    env["BTB_VERSION_TAG"] = "v0.0.17"
    env["BTB_DRY_RUN"] = "false"

    result = run([str(hook)], repo, env)

    assert result.returncode == 0, result.stderr
    assert deploy_log.read_text() == "deployed\n"
    assert json.loads(manifest.read_text())["version"] == "v0.0.17"


def test_before_release_hook_dry_run_leaves_tree_unchanged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    manifest = repo / "custom_components" / "btoddb_ha_music" / "manifest.json"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"version": "v0.0.16"}, indent=2) + "\n")
    write_executable(
        scripts / "deploy-card",
        "#!/usr/bin/env bash\nprintf 'should not run\\n' > deploy.log\n",
    )
    hook = scripts / "ship.d" / "before-release-commit"
    hook.parent.mkdir()
    shutil.copy2(HOOK, hook)

    env = os.environ.copy()
    env["BTB_REPO_ROOT"] = str(repo)
    env["BTB_VERSION_TAG"] = "v0.0.17"
    env["BTB_DRY_RUN"] = "true"

    result = run([str(hook)], repo, env)

    assert result.returncode == 0, result.stderr
    assert "DRY-RUN:" in result.stdout
    assert json.loads(manifest.read_text())["version"] == "v0.0.16"
    assert not (repo / "deploy.log").exists()
