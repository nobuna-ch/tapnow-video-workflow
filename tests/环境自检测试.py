from __future__ import annotations

from contextlib import contextmanager
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "环境自检.py"


def run_check(
    *arguments: str,
    no_site: bool = False,
    no_bytecode: bool = True,
    working_directory: Path = ROOT,
    script: Path = SCRIPT,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable]
    if no_bytecode:
        command.append("-B")
    if no_site:
        command.append("-S")
    command.extend(["-X", "utf8", str(script), *arguments])
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=working_directory,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@contextmanager
def temporary_test_directory():
    configured_root = os.environ.get("VIDEO_WORKFLOW_TEST_ROOT")
    boundary = Path(configured_root).resolve() if configured_root else Path(tempfile.gettempdir()).resolve()
    boundary.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="video-workflow-", dir=boundary)).resolve()
    if not temporary.is_relative_to(boundary):
        raise RuntimeError(f"隔离测试目录越界：{temporary}")
    try:
        yield temporary
    finally:
        resolved = temporary.resolve()
        if not resolved.is_relative_to(boundary):
            raise RuntimeError(f"拒绝清理边界外路径：{resolved}")
        shutil.rmtree(resolved)


@contextmanager
def isolated_skill_copy():
    required = (
        Path("scripts/环境自检.py"),
        Path("references/编剧集成.md"),
        Path("third_party/screenwriting-skills/LICENSE"),
        Path("third_party/screenwriting-skills/NOTICE"),
        Path("third_party/screenwriting-skills/SOURCE.md"),
    )
    with temporary_test_directory() as temporary:
        isolated_root = temporary / "video-workflow"
        for relative in required:
            source = ROOT / relative
            if not source.is_file():
                raise FileNotFoundError(f"测试所需包文件尚未创建：{source}")
            destination = isolated_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        self_check = isolated_root / "scripts" / "环境自检.py"
        yield isolated_root, self_check


class EnvironmentCheckTests(unittest.TestCase):
    def test_text_succeeds_without_site_packages(self) -> None:
        result = run_check("--要求", "text", "--格式", "json", no_site=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["capabilities"]["text"]["status"], "available")
        self.assertEqual(report["requirement"]["exit_code"], 0)

    def test_word_fails_without_site_packages_but_text_remains_available(self) -> None:
        result = run_check("--要求", "word", "--格式", "json", no_site=True)
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["capabilities"]["text"]["status"], "available")
        self.assertEqual(report["capabilities"]["word"]["status"], "missing")

    def test_render_never_claims_visual_verification(self) -> None:
        result = run_check("--要求", "render", "--格式", "json")
        self.assertEqual(result.returncode, 3, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["capabilities"]["render"]["status"], "not_verified")
        self.assertIn("未实际", report["capabilities"]["render"]["detail"])

    def test_does_not_create_python_cache_in_skill(self) -> None:
        before = {path for path in ROOT.rglob("__pycache__")}
        result = run_check("--要求", "text", no_bytecode=False)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        after = {path for path in ROOT.rglob("__pycache__")}
        self.assertEqual(after, before)

    def test_does_not_create_files_in_external_working_directory(self) -> None:
        with temporary_test_directory() as working_directory:
            result = run_check(
                "--要求",
                "text",
                working_directory=working_directory,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(list(working_directory.iterdir()), [])

    def test_screenwriting_succeeds_in_isolation_without_site_packages_or_external_skills(self) -> None:
        with isolated_skill_copy() as (isolated_root, self_check):
            self.assertFalse(any(path.name.startswith("sw-") for path in isolated_root.parent.iterdir()))
            result = run_check(
                "--要求",
                "screenwriting",
                "--格式",
                "json",
                no_site=True,
                working_directory=isolated_root,
                script=self_check,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            report = json.loads(result.stdout)
            capability = report["capabilities"]["screenwriting"]
            resources = report["components"]["screenwriting_resources"]
            self.assertEqual(capability["status"], "available")
            self.assertFalse(resources["external_sw_skills_required"])
            self.assertEqual(resources["missing_sections"], [])
            self.assertEqual(resources["empty_sections"], [])
            self.assertIn("不保证创作质量", capability["detail"])

    def test_screenwriting_missing_integration_file_fails_without_breaking_text(self) -> None:
        with isolated_skill_copy() as (isolated_root, self_check):
            integration = isolated_root / "references" / "编剧集成.md"
            integration.unlink()
            result = run_check(
                "--要求",
                "screenwriting",
                "--格式",
                "json",
                no_site=True,
                working_directory=isolated_root,
                script=self_check,
            )
            self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report["capabilities"]["screenwriting"]["status"], "missing")
            text_result = run_check(
                "--要求",
                "text",
                "--格式",
                "json",
                no_site=True,
                working_directory=isolated_root,
                script=self_check,
            )
            self.assertEqual(text_result.returncode, 0, text_result.stderr or text_result.stdout)

    def test_screenwriting_missing_required_section_fails(self) -> None:
        with isolated_skill_copy() as (isolated_root, self_check):
            integration = isolated_root / "references" / "编剧集成.md"
            content = integration.read_text(encoding="utf-8")
            self.assertIn("## 改编与表达", content)
            integration.write_text(content.replace("## 改编与表达", "### 改编与表达", 1), encoding="utf-8")
            result = run_check(
                "--要求",
                "screenwriting",
                "--格式",
                "json",
                no_site=True,
                working_directory=isolated_root,
                script=self_check,
            )
            self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
            report = json.loads(result.stdout)
            resources = report["components"]["screenwriting_resources"]
            self.assertIn("改编与表达", resources["missing_sections"])

    def test_screenwriting_missing_license_fails_without_breaking_text(self) -> None:
        with isolated_skill_copy() as (isolated_root, self_check):
            license_file = isolated_root / "third_party" / "screenwriting-skills" / "LICENSE"
            license_file.unlink()
            result = run_check(
                "--要求",
                "screenwriting",
                "--格式",
                "json",
                no_site=True,
                working_directory=isolated_root,
                script=self_check,
            )
            self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
            report = json.loads(result.stdout)
            resources = report["components"]["screenwriting_resources"]
            self.assertEqual(resources["files"]["third_party/screenwriting-skills/LICENSE"]["status"], "missing")
            text_result = run_check(
                "--要求",
                "text",
                no_site=True,
                working_directory=isolated_root,
                script=self_check,
            )
            self.assertEqual(text_result.returncode, 0, text_result.stderr or text_result.stdout)


if __name__ == "__main__":
    unittest.main()
