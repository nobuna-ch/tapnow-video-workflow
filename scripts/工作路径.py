#!/usr/bin/env python3
"""视频项目路径识别与导出目标约束（仅使用标准库）。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CURRENT_KINDS = ("项目说明书", "剧本", "分镜图提示词", "视频提示词与台词", "素材与节点连接")
CURRENT_NAMES = {f"{name}.md" for name in CURRENT_KINDS}


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def infer_project_root(path: Path, explicit: Path | None = None) -> Path:
    """推断项目根；归档/临时工作里的副本不能被误认成项目。"""
    if explicit is not None:
        root = _resolved(explicit)
        if not root.is_dir():
            raise ValueError(f"项目目录不存在：{root}")
        return root

    probe = _resolved(path)
    cursor = probe if probe.is_dir() else probe.parent
    ancestors = (cursor, *cursor.parents)

    # 结构边界优先于内部测试副本里可能出现的伪项目标记。
    for folder in ancestors:
        if folder.name == "临时工作":
            if folder.parent.name == "归档":
                return folder.parent.parent
            return folder.parent
    for folder in ancestors:
        if folder.name in {"文档源稿", "历史版本", "原始资料", "方案资料"} and folder.parent.name == "归档":
            return folder.parent.parent
        if folder.name == "归档":
            return folder.parent

    for folder in ancestors:
        if (folder / "归档" / "文档源稿").is_dir() or (folder / "制作素材").is_dir():
            return folder
    raise ValueError("无法识别项目根目录；请显式提供 --项目目录")


def is_temporary_target(path: Path, root: Path) -> bool:
    path, root = _resolved(path), _resolved(root)
    return is_relative_to(path, root / "临时工作") or is_relative_to(path, root / "归档" / "临时工作")


def is_history_source(path: Path, root: Path) -> bool:
    path, root = _resolved(path), _resolved(root)
    return is_relative_to(path, root / "归档" / "历史版本") or is_relative_to(path, root / "历史版本")


def is_current_source(path: Path, root: Path) -> bool:
    path, root = _resolved(path), _resolved(root)
    return path.name in CURRENT_NAMES and path.parent in {root, root / "归档" / "文档源稿"}


@dataclass(frozen=True)
class ExportPlan:
    project: Path
    markdown: Path
    output: Path
    kind: str
    draft: bool


def plan_export(
    markdown: Path,
    *,
    project: Path | None = None,
    output: Path | None = None,
    draft: bool = False,
    repair_archive: bool = False,
) -> ExportPlan:
    markdown = _resolved(markdown)
    root = infer_project_root(markdown, project)
    if not is_relative_to(markdown, root):
        raise ValueError(f"源稿必须位于项目目录内：{markdown}")

    history = is_history_source(markdown, root)
    current = is_current_source(markdown, root)
    if history:
        if draft:
            raise ValueError("历史稿修复不能使用 --草稿")
        if not repair_archive:
            raise ValueError("历史归档保持静态；修复需显式使用 --修复归档")
        expected = markdown.with_suffix(".docx")
        if output is not None and _resolved(output) != expected:
            raise ValueError("历史归档只允许原位修复同名 Word")
        return ExportPlan(root, markdown, expected, "history", False)

    if repair_archive:
        raise ValueError("--修复归档只适用于历史版本目录中的源稿")
    if not current and not draft:
        raise ValueError("未知或非当前文档名只能作为 --草稿 导出")

    if output is not None:
        target = _resolved(output)
        if not is_temporary_target(target, root):
            raise ValueError("--输出 只允许项目/临时工作或项目/归档/临时工作内的路径")
        if target.name != markdown.with_suffix(".docx").name:
            raise ValueError("输出 Word 必须与 Markdown 同名")
    elif draft:
        target = root / "临时工作" / "导出预览" / markdown.with_suffix(".docx").name
    else:
        target = root / markdown.with_suffix(".docx").name

    return ExportPlan(root, markdown, target, "current" if current else "draft", draft)
