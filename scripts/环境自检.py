#!/usr/bin/env python3
"""只读检查 video-workflow 的本地能力，不联网或安装依赖。"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any


AVAILABLE = "available"
MISSING = "missing"
NOT_VERIFIED = "not_verified"
MINIMUM_PYTHON = (3, 10)
SCREENWRITING_SECTIONS = (
    "前提与主题",
    "结构与节奏",
    "人物与动机",
    "场景与衔接",
    "对白与潜台词",
    "改编与表达",
)
SCREENWRITING_FILES = (
    "references/编剧集成.md",
    "third_party/screenwriting-skills/LICENSE",
    "third_party/screenwriting-skills/NOTICE",
    "third_party/screenwriting-skills/SOURCE.md",
)


def _module_check(distribution: str, module: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "distribution": distribution,
        "module": module,
        "status": MISSING,
        "version": None,
        "detail": "未安装或当前 Python 环境不可见",
    }
    try:
        result["version"] = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return result
    except Exception as exc:  # pragma: no cover - unusual broken metadata
        result["status"] = NOT_VERIFIED
        result["detail"] = f"无法读取包元数据：{exc.__class__.__name__}"
        return result

    try:
        importlib.import_module(module)
    except Exception as exc:
        result["status"] = MISSING
        result["detail"] = f"已找到分发包，但导入失败：{exc.__class__.__name__}: {exc}"
    else:
        result["status"] = AVAILABLE
        result["detail"] = "版本元数据存在且模块可导入"
    return result


def _candidate_executables() -> dict[str, list[str]]:
    names = {
        "libreoffice": ("soffice", "libreoffice"),
        "word": ("WINWORD.EXE", "winword"),
        "wps": ("wps.exe", "wps"),
        "pdf_pages": ("pdftoppm", "pdftocairo"),
    }
    found: dict[str, list[str]] = {key: [] for key in names}

    for group, commands in names.items():
        for command in commands:
            resolved = shutil.which(command)
            if resolved and resolved not in found[group]:
                found[group].append(str(Path(resolved).resolve()))

    if os.name != "nt":
        return found

    fixed_candidates = {
        "libreoffice": [
            ("ProgramFiles", "LibreOffice/program/soffice.exe"),
            ("ProgramFiles(x86)", "LibreOffice/program/soffice.exe"),
        ],
        "word": [
            ("ProgramFiles", "Microsoft Office/root/Office16/WINWORD.EXE"),
            ("ProgramFiles(x86)", "Microsoft Office/root/Office16/WINWORD.EXE"),
        ],
    }
    for group, candidates in fixed_candidates.items():
        for variable, relative in candidates:
            root = os.environ.get(variable)
            if not root:
                continue
            candidate = Path(root, *relative.split("/"))
            if candidate.is_file():
                value = str(candidate.resolve())
                if value not in found[group]:
                    found[group].append(value)

    try:
        import winreg

        registry_names = {
            "word": "WINWORD.EXE",
            "libreoffice": "soffice.exe",
            "wps": "wps.exe",
        }
        views = (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY)
        for group, executable in registry_names.items():
            subkey = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable}"
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for view in views:
                    try:
                        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | view) as key:
                            value = winreg.QueryValue(key, None)
                    except OSError:
                        continue
                    candidate = Path(str(value).strip('"'))
                    if candidate.is_file():
                        resolved = str(candidate.resolve())
                        if resolved not in found[group]:
                            found[group].append(resolved)
    except (ImportError, OSError):
        pass

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        wps_root = Path(local_app_data, "Kingsoft", "WPS Office")
        if wps_root.is_dir():
            for candidate in sorted(wps_root.glob("*/office6/wps.exe"))[:20]:
                resolved = str(candidate.resolve())
                if resolved not in found["wps"]:
                    found["wps"].append(resolved)
    return found


def _font_check() -> dict[str, Any]:
    wanted = (
        "microsoft yahei",
        "微软雅黑",
        "simsun",
        "宋体",
        "dengxian",
        "等线",
        "noto sans cjk",
        "noto serif cjk",
        "source han sans",
        "source han serif",
        "思源黑体",
        "思源宋体",
    )
    matches: set[str] = set()

    if os.name == "nt":
        try:
            import winreg

            subkey = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        count = winreg.QueryInfoKey(key)[1]
                        for index in range(count):
                            name, value, _ = winreg.EnumValue(key, index)
                            combined = f"{name} {value}".lower()
                            if any(token in combined for token in wanted):
                                matches.add(name)
                except OSError:
                    continue
        except (ImportError, OSError):
            return {
                "status": NOT_VERIFIED,
                "matches": [],
                "detail": "无法只读查询 Windows 字体注册表",
            }
    else:
        roots = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local/share/fonts",
            Path.home() / ".fonts",
        ]
        checked = False
        seen = 0
        for root in roots:
            if not root.is_dir():
                continue
            checked = True
            try:
                for candidate in root.rglob("*"):
                    if seen >= 5000:
                        break
                    seen += 1
                    if candidate.is_file():
                        lowered = candidate.name.lower().replace("-", " ").replace("_", " ")
                        if any(token in lowered for token in wanted):
                            matches.add(candidate.name)
            except OSError:
                continue
        if not checked:
            return {
                "status": NOT_VERIFIED,
                "matches": [],
                "detail": "未找到可只读扫描的常见字体目录",
            }

    if matches:
        return {
            "status": AVAILABLE,
            "matches": sorted(matches),
            "detail": "找到常见中文字体；实际 Word 排版仍需渲染检查",
        }
    return {
        "status": MISSING,
        "matches": [],
        "detail": "未找到已知中文字体；可仍有其他可用字体",
    }


def _screenwriting_check() -> dict[str, Any]:
    skill_root = Path(__file__).resolve().parents[1]
    files: dict[str, dict[str, Any]] = {}
    contents: dict[str, str] = {}

    for relative in SCREENWRITING_FILES:
        path = skill_root.joinpath(*relative.split("/"))
        item: dict[str, Any] = {
            "status": MISSING,
            "path": relative,
            "detail": "文件不存在",
        }
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                item["detail"] = f"无法按 UTF-8 读取：{exc.__class__.__name__}"
            else:
                if content.strip():
                    item["status"] = AVAILABLE
                    item["detail"] = "文件可读取且非空"
                    contents[relative] = content
                else:
                    item["detail"] = "文件为空"
        files[relative] = item

    integration = contents.get("references/编剧集成.md", "")
    section_matches = list(re.finditer(r"^##\s+(.+?)\s*$", integration, flags=re.MULTILINE))
    found_sections = tuple(match.group(1).strip() for match in section_matches)
    section_bodies: dict[str, str] = {}
    for index, match in enumerate(section_matches):
        title = match.group(1).strip()
        end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(integration)
        section_bodies.setdefault(title, integration[match.end() : end].strip())
    missing_sections = [section for section in SCREENWRITING_SECTIONS if section not in found_sections]
    empty_sections = [
        section
        for section in SCREENWRITING_SECTIONS
        if section in found_sections and not section_bodies.get(section)
    ]
    files_ok = all(item["status"] == AVAILABLE for item in files.values())
    status = AVAILABLE if files_ok and not missing_sections and not empty_sections else MISSING
    if status == AVAILABLE:
        detail = "内置编剧资源、六个方法模块及许可来源材料完整；仅证明资源完整，不保证创作质量"
    else:
        problems = [relative for relative, item in files.items() if item["status"] != AVAILABLE]
        parts = []
        if problems:
            parts.append("缺失或不可读文件：" + "、".join(problems))
        if missing_sections:
            parts.append("缺少二级标题：" + "、".join(missing_sections))
        if empty_sections:
            parts.append("模块正文为空：" + "、".join(empty_sections))
        detail = "；".join(parts)

    return {
        "status": status,
        "detail": detail,
        "required_sections": list(SCREENWRITING_SECTIONS),
        "found_sections": list(found_sections),
        "missing_sections": missing_sections,
        "empty_sections": empty_sections,
        "files": files,
        "external_sw_skills_required": False,
    }


def collect() -> dict[str, Any]:
    python_ok = sys.version_info >= MINIMUM_PYTHON
    python_info = {
        "status": AVAILABLE if python_ok else MISSING,
        "version": platform.python_version(),
        "executable": sys.executable,
        "minimum_required": ".".join(map(str, MINIMUM_PYTHON)),
        "detail": "满足脚本最低版本" if python_ok else "低于脚本最低版本",
    }
    docx = _module_check("python-docx", "docx")
    pillow = _module_check("Pillow", "PIL")
    screenwriting = _screenwriting_check()
    executables = _candidate_executables()
    office_candidates = executables["libreoffice"] + executables["word"] + executables["wps"]
    render_candidates = bool(office_candidates and executables["pdf_pages"])

    text_status = AVAILABLE if python_ok else MISSING
    word_status = (
        AVAILABLE
        if text_status == AVAILABLE and docx["status"] == AVAILABLE and pillow["status"] == AVAILABLE
        else MISSING
    )
    render_detail = (
        "找到 Office/PDF 页面转换候选工具，但尚未实际导出、转页和逐页检查"
        if render_candidates
        else "未形成可确认的 Office→PDF→页面图本地工具链；宿主 documents 渲染能力无法由本脚本探测"
    )

    return {
        "schema_version": 1,
        "read_only": True,
        "network_used": False,
        "capabilities": {
            "text": {
                "status": text_status,
                "detail": (
                    "随附纯文本检查工具可运行；基础创作本身无需 Python"
                    if python_ok
                    else "随附脚本需要 Python 3.10 或更高版本；基础创作本身无需 Python"
                ),
            },
            "word": {
                "status": word_status,
                "detail": (
                    "python-docx 与 Pillow 均可导入；仍需针对实际文档运行导出检查"
                    if word_status == AVAILABLE
                    else "缺少可导入的 python-docx、Pillow 或合适的 Python"
                ),
            },
            "render": {
                "status": NOT_VERIFIED,
                "detail": render_detail,
            },
            "screenwriting": {
                "status": screenwriting["status"],
                "detail": screenwriting["detail"],
            },
        },
        "components": {
            "python": python_info,
            "python_docx": docx,
            "pillow": pillow,
            "fonts": _font_check(),
            "screenwriting_resources": screenwriting,
            "executables": {
                "status": AVAILABLE if any(executables.values()) else MISSING,
                "found": executables,
                "detail": "仅检查路径与只读注册信息；未启动任何 GUI 或渲染进程",
            },
        },
        "notes": [
            "基础文字能力不需要 Python 包、API key 或 TapNow 账户。",
            "imagegen 是宿主扩展，不是 pip 依赖，本检查不绑定图像模型供应商。",
            "可执行文件存在不等于 Word 已完成视觉验收。",
            "screenwriting 通过只证明内置资源完整，不保证创作质量；外部 sw-* 技能不是依赖。",
        ],
    }


def _print_text(report: dict[str, Any], required: str) -> None:
    print("video-workflow 环境自检（只读）")
    print(f"要求能力：{required}")
    for name in ("text", "word", "render", "screenwriting"):
        item = report["capabilities"][name]
        print(f"- {name}: {item['status']} — {item['detail']}")

    components = report["components"]
    print(f"- Python: {components['python']['status']} — {components['python']['version']}")
    print(
        f"- python-docx: {components['python_docx']['status']}"
        + (f" — {components['python_docx']['version']}" if components['python_docx']['version'] else "")
    )
    print(
        f"- Pillow: {components['pillow']['status']}"
        + (f" — {components['pillow']['version']}" if components['pillow']['version'] else "")
    )
    print(f"- 中文字体：{components['fonts']['status']} — {components['fonts']['detail']}")
    found = components["executables"]["found"]
    for group in ("libreoffice", "word", "wps", "pdf_pages"):
        values = found[group]
        print(f"- {group}: {'; '.join(values) if values else '未找到'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="只读检查 video-workflow 的 text、word、render、screenwriting 能力；不联网、不安装、不创建缓存。"
    )
    parser.add_argument("--要求", choices=("text", "word", "render", "screenwriting"), default="text")
    parser.add_argument("--格式", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = collect()
    required_status = report["capabilities"][args.要求]["status"]
    exit_code = 0 if required_status == AVAILABLE else (3 if required_status == NOT_VERIFIED else 2)
    report["requirement"] = {
        "name": args.要求,
        "status": required_status,
        "exit_code": exit_code,
        "semantics": "0=要求能力可用，2=要求能力缺失，3=要求能力尚未验证",
    }

    if args.格式 == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report, args.要求)
        print(f"结果：{required_status}（退出码 {exit_code}）")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
