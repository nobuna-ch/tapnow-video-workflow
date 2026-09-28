#!/usr/bin/env python3
"""video-workflow 执行脚本回归；所有临时产物必须放在 --工作目录。"""
from __future__ import annotations

import argparse
import base64
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
from pathlib import Path
import os
import shutil
import subprocess
import sys
import unittest
from zipfile import ZIP_DEFLATED, ZipFile
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
from 工作路径 import infer_project_root, plan_export
from 内容检查 import (check_assets, check_current_content, check_people_notes, check_script,
                    check_source_content, check_storyboard, check_video)
from 检查项目 import check_document_pair, check_project


IMAGE_VALID = """# 测试 分镜图提示词

## 镜头01 开始
全片 0—2 秒｜成片时长 2 秒
地点：卧室。
主要环境锚点：卧室_E01。
连接素材：卧室_E01、人物甲。
起始状态：人物甲坐在桌边。
### 分镜图 prompt
卧室中景，人物甲坐在桌边。画面无字幕。
衔接：人物甲坐着 → 抬头 → 保持抬头。
"""

VIDEO_VALID = """# 测试 视频提示词与台词

## 镜头01 开始
全片 0—2 秒｜成片时长 2 秒
画面输入：分镜_01 → 视频_01。
起始状态：人物甲坐在桌边。
### 视频 prompt 与对应台词
以@分镜_01为首帧。人物甲抬头，镜头固定。
动作记录：坐着 → 抬头 → 保持抬头。
台词：无。
音效：无。
衔接：保持抬头进入下一镜。

## 镜头02 跨切
全片 2—4 秒｜成片时长 2 秒
画面输入：分镜_02 → 视频_02。
起始状态：人物甲保持抬头。
### 视频 prompt 与对应台词
以@分镜_02为首帧。人物甲倾听。
动作记录：抬头 → 倾听 → 视线保持。
跨镜对白：复用镜01尾段，只播放一次。
音效：无新增，沿用室内底噪。
衔接：视线保持。
"""

COMPOSITE_VALID = """# 测试 视频提示词与台词
## 镜头27 合成
全片 0—2 秒｜成片时长 2 秒
画面输入：分镜_27L与分镜_27R分别生成后合成。
起始状态：左右两边人物都已坐定。
### 左半屏 视频 prompt
以@分镜_27L为首帧，人物保持安静。
### 右半屏 视频 prompt
以@分镜_27R为首帧，人物轻轻点头。
动作记录：两边坐定 → 右边点头 → 两边保持。
台词：无。
音效：无新增动作音，沿用两地底噪。
合成：左右同时起播并保持到末帧。
"""

TEMPLATE_DIALOGUE_VALID = """# 测试 视频提示词与台词
## 镜头01 对话
全片 0—2 秒｜成片时长 2 秒
画面输入：分镜_01 → 视频_01。
起始状态：人物甲站定。
### 视频 prompt 与对应台词
以@分镜_01为首帧。人物甲说：“你好。”
动作记录：站定 → 说话 → 保持站定。
说话人：人物甲。台词文本：
你好。
固定音色：成年女性，自然普通话。
本句情绪：平静。语速：约3字/秒。
发言时机：镜内0.2—1秒。
音效：无。
衔接：保持站定。
"""

SCRIPT_VALID = """# 测试 剧本
目标时长：4秒。画幅：16:9。视觉风格：写实、自然。
一句话故事：人物甲说完一句话后抬头。
## 场次01 室内
预计时长：4秒。
动作：人物甲坐着说话，随后抬头。
人物甲：你好。
"""

IMAGE_TWO = IMAGE_VALID + """
## 镜头02 结束
全片 2—4 秒｜成片时长 2 秒
地点：卧室。
主要环境锚点：卧室_E01。
连接素材：卧室_E01、人物甲。
起始状态：人物甲保持抬头。
### 分镜图 prompt
卧室中景，人物甲保持抬头。画面无字幕。
衔接：人物甲抬头 → 保持 → 结束。
"""

STORYBOARD_COMPOSITE_VALID = """# 测试 分镜图提示词
## 镜头27 两地分屏
全片 0—2 秒｜成片时长 2 秒
这是左右分屏合成，两侧分别生成。
起始状态：两边人物均已坐定。
### 左半屏 分镜_27L
连接客厅_E01、人物甲。
分镜图 prompt：客厅中景，人物甲坐定。
### 右半屏 分镜_27R
连接书房_E02、人物乙。
分镜图 prompt：书房中景，人物乙坐定。
### 合成 分镜_27
左右各占一半。
合成：两侧保持各自空间后并排合成。
"""

PNG_RED = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2n0AAAAAASUVORK5CYII=")
PNG_BLUE = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAusB9Y9Z45sAAAAASUVORK5CYII=")

MODERN_VIDEO = """# 测试 视频提示词
## 镜头01（抬头）
模式：首帧
输入素材：首帧=分镜01
建议时长：2秒
```text
人物甲从坐定开始轻轻抬头，保持视线，镜头固定。
音效：抬头时衣料轻响，安静室内底噪。
对白：人物甲：“你好。”
音色：成年女性，自然普通话，轻声平静。
```
"""

MODERN_IMAGE = IMAGE_VALID.replace("分镜图提示词", "分镜").replace(
    "卧室中景，人物甲坐在桌边。画面无字幕。", "```text\n卧室中景，人物甲坐在桌边。画面无字幕。\n```"
)

ASSETS_VALID = """# 测试 资产设定
仅文字设定，图片待生成，音色未验证。
## 人物：人物甲
主体描述：成年女性，灰色上衣，短发。
参考图片：人物甲.png（待生成）
固定音色：成年女性，自然普通话。
## 环境：卧室正面
设定：窗在画面左侧，一张桌子。
参考图片：待生成
"""


def load_exporter():
    name = "_video_workflow_test_exporter"
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "导出说明书.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def rewrite_docx(path: Path, transform) -> None:
    with ZipFile(path, "r") as archive:
        members = [(info, archive.read(info.filename)) for info in archive.infolist()]
    replacement = path.with_name(path.stem + ".rewrite.docx")
    with ZipFile(replacement, "w", ZIP_DEFLATED) as archive:
        for info, data in members:
            archive.writestr(info, transform(info.filename, data))
    replacement.replace(path)


class ExecutionTests(unittest.TestCase):
    work: Path

    def setUp(self):
        self.case = self.work / self._testMethodName
        if self.case.resolve() == self.work.resolve() or not self.case.resolve().is_relative_to(self.work.resolve()):
            raise RuntimeError("拒绝清理测试工作目录之外的路径")
        if self.case.exists():
            shutil.rmtree(self.case)
        self.case.mkdir(parents=True)

    def project(self) -> Path:
        root = self.case / "项目"
        (root / "归档" / "文档源稿").mkdir(parents=True)
        return root

    def test_path_current_archive_temp_and_escape(self):
        root = self.project()
        current = root / "归档" / "文档源稿" / "分镜图提示词.md"
        current.write_text(IMAGE_VALID, encoding="utf-8")
        nested = self.case / "归档路径探针" / "伪项目" / "归档" / "文档源稿"
        nested.mkdir(parents=True)
        nested_md = nested / "分镜图提示词.md"
        nested_md.write_text(IMAGE_VALID, encoding="utf-8")
        host_root = infer_project_root(self.work)
        self.assertEqual(infer_project_root(current, root), root.resolve())
        self.assertEqual(infer_project_root(nested_md), host_root)
        self.assertEqual(plan_export(current, project=root).output, (root / "分镜图提示词.docx").resolve())
        with self.assertRaisesRegex(ValueError, "只允许"):
            plan_export(current, project=root, output=self.case / "越界" / "分镜图提示词.docx")

    def test_history_requires_explicit_repair(self):
        root = self.project()
        history = root / "归档" / "历史版本"
        history.mkdir()
        md = history / "分镜图提示词_第01版.md"
        md.write_text("# 静态历史\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "修复归档"):
            plan_export(md, project=root)
        plan = plan_export(md, project=root, repair_archive=True)
        self.assertEqual(plan.output, md.with_suffix(".docx").resolve())
        with self.assertRaisesRegex(ValueError, "原位"):
            plan_export(md, project=root, repair_archive=True, output=root / "临时工作" / md.with_suffix(".docx").name)

    def test_content_missing_cross_shot_and_composite(self):
        bad = IMAGE_VALID.replace("起始状态：人物甲坐在桌边。\n", "")
        self.assertTrue(any("缺少起始状态" in item for item in check_storyboard(bad)["问题"]))
        self.assertEqual(check_video(VIDEO_VALID)["问题"], [])
        self.assertEqual(check_video(COMPOSITE_VALID)["问题"], [])
        self.assertEqual(check_video(TEMPLATE_DIALOGUE_VALID)["问题"], [])

    def test_script_duration_order_and_anchor_rules(self):
        self.assertEqual(check_script(SCRIPT_VALID)["问题"], [])
        missing_story = SCRIPT_VALID.replace("一句话故事：人物甲说完一句话后抬头。\n", "")
        self.assertIn("剧本：缺少一句话故事/表达目标字段", check_script(missing_story)["问题"])

        mismatch = IMAGE_VALID.replace("成片时长 2 秒", "成片时长 3 秒")
        self.assertTrue(any("成片时长与全片时间区间不一致" in p for p in check_storyboard(mismatch)["问题"]))
        video_mismatch = TEMPLATE_DIALOGUE_VALID.replace("成片时长 2 秒", "成片时长 3 秒")
        self.assertTrue(any("成片时长与全片时间区间不一致" in p for p in check_video(video_mismatch)["问题"]))
        multiple = IMAGE_VALID.replace("卧室_E01。\n连接素材", "卧室_E01、卧室_E02。\n连接素材")
        self.assertTrue(any("多个 E 编号" in p for p in check_storyboard(multiple)["问题"]))
        self.assertEqual(check_storyboard(STORYBOARD_COMPOSITE_VALID)["问题"], [])
        composite_bad = STORYBOARD_COMPOSITE_VALID.replace("客厅_E01、人物甲", "客厅_E01、备用_E03、人物甲")
        self.assertTrue(any("左半屏应明确且只使用一个" in p for p in check_storyboard(composite_bad)["问题"]))

        root = self.project()
        source = root / "归档" / "文档源稿"
        (source / "分镜图提示词.md").write_text(IMAGE_TWO, encoding="utf-8")
        reversed_video = VIDEO_VALID.split("\n## 镜头02", 1)[1]
        reversed_video = "# 测试 视频提示词与台词\n## 镜头02" + reversed_video + VIDEO_VALID.split("\n## 镜头02", 1)[0].split("# 测试 视频提示词与台词", 1)[1]
        (source / "视频提示词与台词.md").write_text(reversed_video, encoding="utf-8")
        self.assertIn("分镜图与视频文档的镜号顺序不一致", check_current_content(root)["问题"])

    def test_nonempty_dialogue_and_audio_rules(self):
        blank = IMAGE_VALID.replace("起始状态：人物甲坐在桌边。", "起始状态：")
        self.assertTrue(any("缺少起始状态" in p for p in check_storyboard(blank)["问题"]))

        no_spoken_prompt = TEMPLATE_DIALOGUE_VALID.replace("人物甲说：“你好。”", "人物甲张嘴说话")
        self.assertTrue(any("prompt 未包含实际台词" in p for p in check_video(no_spoken_prompt)["问题"]))
        same_voice = TEMPLATE_DIALOGUE_VALID.replace("固定音色：成年女性，自然普通话。", "固定音色：同上。")
        self.assertTrue(any("固定音色不能写" in p for p in check_video(same_voice)["问题"]))
        offscreen = no_spoken_prompt.replace("人物甲张嘴说话", "人物甲在画外说话，画面人物倾听")
        self.assertFalse(any("prompt 未包含实际台词" in p for p in check_video(offscreen)["问题"]))

        audio_missing = TEMPLATE_DIALOGUE_VALID.replace("音效：无。", "音效：硬壳书合拢声。")
        audio_problems = check_video(audio_missing)["问题"]
        self.assertTrue(any("prompt 描述" in p for p in audio_problems))
        self.assertTrue(any("素材时长" in p for p in audio_problems))
        self.assertTrue(any("出现时机" in p for p in audio_problems))
        blank_audio_prompt = TEMPLATE_DIALOGUE_VALID.replace(
            "音效：无。",
            "音效：合书轻响。\n音效 prompt：\n建议素材时长：1秒。\n出现时机：动作结束时。",
        )
        self.assertTrue(any("prompt 未填写" in p for p in check_video(blank_audio_prompt)["问题"]))

    def test_people_fields_require_values_and_examples_pass(self):
        root = self.project()
        people = root / "制作素材" / "人物"
        people.mkdir(parents=True)
        (people / "人物甲.png").write_bytes(PNG_RED)
        (people / "人物甲.txt").write_text("""人物甲 资产说明
参考图片：人物甲.png
人物名称：人物甲
【主体描述】

【外形复用提示词】
人物甲正面、侧面和背面。
【固定音色】
成年女性，自然普通话。
【试听台词与表演】
“你好。”平静说出。
声音状态：仅文字设定。
""", encoding="utf-8")
        (people / "人物乙.png").write_bytes(PNG_RED)
        (people / "人物乙.md").write_text("""人物乙 资产说明
参考图片：人物乙.png
人物名称：人物乙
【主体描述】
成年男性。
【外形复用提示词】
人物乙正面、侧面和背面。
【固定音色】
成年男性，自然普通话。
【试听台词与表演】
“你好。”平静说出。
声音状态：仅文字设定。
""", encoding="utf-8")
        problems, manual = check_people_notes(root)
        self.assertTrue(any("主体描述" in p for p in problems))
        self.assertTrue(any("仅有 Markdown" in p for p in manual))

        example = SKILL / "examples" / "最小示例" / "归档" / "文档源稿"
        self.assertEqual(check_script((example / "剧本.md").read_text(encoding="utf-8"))["问题"], [])
        for name in ("资产设定.md", "分镜.md", "视频提示词.md"):
            self.assertEqual(check_source_content(example / name, formal=True)["问题"], [], name)

    def test_modern_video_frame_modes_and_single_copy_body(self):
        self.assertEqual(check_video(MODERN_VIDEO)["问题"], [])
        tail = MODERN_VIDEO.replace("模式：首帧", "模式：首尾帧").replace("首帧=分镜01", "首帧=分镜01；尾帧=分镜02")
        self.assertEqual(check_video(tail)["问题"], [])
        self.assertTrue(any("缺少尾帧" in p for p in check_video(tail.replace("；尾帧=分镜02", ""))["问题"]))
        redundant = MODERN_VIDEO.replace("人物甲从坐定", "以@分镜01为首帧。人物甲从坐定")
        self.assertTrue(any("不要机械写" in p for p in check_video(redundant)["问题"]))
        split_audio = MODERN_VIDEO.replace("音效：抬头时衣料轻响，安静室内底噪。\n", "") + "音效：无\n"
        self.assertTrue(any("同一提示词块" in p for p in check_video(split_audio)["问题"]))
        two_blocks = MODERN_VIDEO + "```text\n第二块\n```\n"
        self.assertTrue(any("只提供一个" in p for p in check_video(two_blocks)["问题"]))
        unclosed = MODERN_VIDEO.rsplit("```", 1)[0]
        self.assertTrue(any("闭合" in p for p in check_video(unclosed)["问题"]))
        blank_speech = MODERN_VIDEO.replace("人物甲：“你好。”", "人物甲说一句话。")
        self.assertTrue(any("实际句子" in p for p in check_video(blank_speech)["问题"]))
        sound_last = MODERN_VIDEO.replace("音色：成年女性，自然普通话，轻声平静。", "镜头再次后退。")
        self.assertTrue(any("正文末尾" in p for p in check_video(sound_last)["问题"]))

    def test_modern_reference_checks_only_actual_input_materials(self):
        reference = MODERN_VIDEO.replace("模式：首帧", "模式：全能参考").replace("首帧=分镜01", "分镜01、人物乙（音色参考）").replace(
            "人物甲从坐定", "沿用 @分镜01 的构图和人物身份。人物甲从坐定")
        # 可见人物甲未独立连接；输入人物乙也不要求机械引用全部清单。
        self.assertEqual(check_video(reference)["问题"], [])
        missing = reference.replace("@分镜01", "@人物甲")
        self.assertTrue(any("@人物甲 不在输入素材清单" in p for p in check_video(missing)["问题"]))
        substring = reference.replace("分镜01、人物乙", "分镜01、人物甲手机").replace("@分镜01", "@人物甲")
        self.assertTrue(any("@人物甲 不在输入素材清单" in p for p in check_video(substring)["问题"]))
        unclear_boundary = reference.replace("@分镜01 的构图和人物身份", "@分镜01保持构图和人物身份")
        self.assertTrue(any("引用与正文边界不清" in p for p in check_video(unclear_boundary)["问题"]))
        text_mode = MODERN_VIDEO.replace("模式：首帧", "模式：文本").replace("首帧=分镜01", "无").replace("## 镜头01", "## 节点01")
        self.assertEqual(check_video(text_mode)["问题"], [])

    def test_multiline_dialogue_and_bold_metadata_in_legacy_name(self):
        multiline = MODERN_VIDEO.replace("对白：人物甲：“你好。”", "对白：\n妈妈（温和）：“你好。”\n（儿子先倾听，再开口。）\n儿子：“我回来了。”")
        self.assertEqual(check_video(multiline)["问题"], [])
        mixed = multiline.replace("对白：\n妈妈（温和）：“你好。”", "对白：妈妈（温和）：“你好。”")
        self.assertEqual(check_video(mixed)["问题"], [])
        blank = multiline.replace("儿子：“我回来了。”", "儿子：")
        self.assertTrue(any("实际句子" in p for p in check_video(blank)["问题"]))
        action = multiline.replace("儿子：“我回来了。”", "镜头：随后后退到门外。")
        self.assertTrue(any("正文末尾" in p for p in check_video(action)["问题"]))
        silent_with_extra_dialogue = multiline.replace("妈妈（温和）：“你好。”", "无")
        self.assertTrue(any("实际句子" in p for p in check_video(silent_with_extra_dialogue)["问题"]))
        unnamed = multiline.replace("儿子：“我回来了。”", "“我回来了。”")
        self.assertTrue(any("实际句子" in p for p in check_video(unnamed)["问题"]))
        root = self.project()
        legacy = root / "归档" / "文档源稿" / "视频提示词与台词.md"
        bold = multiline.replace("模式：", "**模式**：").replace("输入素材：", "**输入素材**：").replace("建议时长：", "**建议时长**：")
        legacy.write_text(bold, encoding="utf-8")
        self.assertEqual(check_source_content(legacy, formal=True)["问题"], [])
        colon_inside_bold = bold.replace("**：", "：**")
        legacy.write_text(colon_inside_bold, encoding="utf-8")
        self.assertEqual(check_source_content(legacy, formal=True)["问题"], [])

    def test_modern_storyboard_keeps_execution_fields(self):
        self.assertEqual(check_storyboard(MODERN_IMAGE, modern=True)["问题"], [])
        no_location = MODERN_IMAGE.replace("地点：卧室。\n", "")
        self.assertTrue(any("缺少地点" in p for p in check_storyboard(no_location, modern=True)["问题"]))
        empty = MODERN_IMAGE.replace("卧室中景，人物甲坐在桌边。画面无字幕。", "")
        self.assertTrue(any("非空且闭合" in p for p in check_storyboard(empty, modern=True)["问题"]))
        multiple = MODERN_IMAGE.replace("主要环境锚点：卧室_E01。", "主要环境锚点：卧室正面、卧室窗侧。")
        self.assertTrue(any("只能使用一个" in p for p in check_storyboard(multiple, modern=True)["问题"]))

    def test_legacy_fenced_video_and_static_history_are_not_migrated(self):
        fenced = TEMPLATE_DIALOGUE_VALID.replace("以@分镜_01为首帧。人物甲说：“你好。”", "```text\n以@分镜_01为首帧。人物甲说：“你好。”\n```")
        self.assertEqual(check_video(fenced)["问题"], [])
        root = self.project()
        source = root / "归档" / "文档源稿"
        (source / "剧本.md").write_text(SCRIPT_VALID, encoding="utf-8")
        history = root / "归档" / "历史版本"
        history.mkdir()
        legacy = history / "视频提示词与台词_第01版.md"
        original = "# 静态历史\n\n旧有结构，不套新字段。\n".encode("utf-8")
        legacy.write_bytes(original)
        self.assertEqual(check_project(root, mode="text")["问题"], [])
        self.assertEqual(legacy.read_bytes(), original)

    def test_asset_summary_replaces_per_person_notes(self):
        root = self.project()
        people = root / "制作素材" / "人物"
        people.mkdir(parents=True)
        (people / "人物甲.png").write_bytes(PNG_RED)
        (root / "归档" / "文档源稿" / "资产设定.md").write_text(ASSETS_VALID, encoding="utf-8")
        self.assertEqual(check_assets(ASSETS_VALID)["问题"], [])
        self.assertEqual(check_people_notes(root)[0], [])
        (people / "人物乙.png").write_bytes(PNG_RED)
        self.assertTrue(any("人物乙" in p for p in check_people_notes(root)[0]))
        self.assertTrue(any("缺少固定音色" in p for p in check_assets(ASSETS_VALID.replace("固定音色：成年女性，自然普通话。", ""))["问题"]))

    def test_new_names_require_new_structure_and_aliases_are_unique(self):
        root = self.project()
        source = root / "归档" / "文档源稿"
        video = source / "视频提示词.md"
        video.write_text(VIDEO_VALID, encoding="utf-8")
        self.assertTrue(any("模式须为" in p for p in check_source_content(video, formal=True)["问题"]))
        video.write_text(MODERN_VIDEO, encoding="utf-8")
        legacy = source / "视频提示词与台词.md"
        legacy.write_text(MODERN_VIDEO.replace("# 测试 视频提示词", "# 测试 视频提示词与台词"), encoding="utf-8")
        self.assertEqual(check_source_content(legacy, formal=True)["问题"], [])
        self.assertTrue(any("同类新旧名称不能并存" in p for p in check_project(root, mode="text")["问题"]))
        with self.assertRaisesRegex(ValueError, "新旧名称不能同时导出"):
            plan_export(video, project=root)

    def test_modern_four_documents_export_and_text_mode_no_dependencies(self):
        root = self.project()
        source = root / "归档" / "文档源稿"
        documents = {"剧本": SCRIPT_VALID, "资产设定": ASSETS_VALID, "分镜": MODERN_IMAGE, "视频提示词": MODERN_VIDEO}
        exporter = load_exporter()
        for name, value in documents.items():
            md = source / f"{name}.md"
            md.write_text(value, encoding="utf-8")
            self.assertEqual(plan_export(md, project=root).output, (root / f"{name}.docx").resolve())
            stderr = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                self.assertEqual(exporter.main([str(md), "--项目目录", str(root)]), 0, stderr.getvalue())
        self.assertEqual(check_project(root, mode="word")["问题"], [])
        run = subprocess.run([sys.executable, "-S", "-B", "-X", "utf8", str(SCRIPTS / "检查项目.py"), str(root), "--模式", "text"],
                             cwd=self.case, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_atomic_replace_permission_failure_keeps_existing_word(self):
        root = self.project()
        md = root / "归档" / "文档源稿" / "视频提示词.md"
        md.write_text(MODERN_VIDEO, encoding="utf-8")
        old = root / "视频提示词.docx"
        old.write_bytes(b"KEEP-EXISTING-WORD")
        exporter = load_exporter()
        with patch.object(exporter.os, "replace", side_effect=PermissionError("模拟文件占用")):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = exporter.main([str(md), "--项目目录", str(root), "--更新"])
        self.assertEqual(code, 1)
        self.assertEqual(old.read_bytes(), b"KEEP-EXISTING-WORD")
        self.assertEqual(list(root.glob(".视频提示词.*.docx")), [])

    def test_orphan_word_and_valueerror_are_reported(self):
        root = self.project()
        empty_result = check_project(root, mode="text")
        self.assertIn("未找到可检查的当前 Markdown 源稿", empty_result["问题"])
        (root / "剧本.docx").write_bytes(b"orphan")
        result = check_project(root, mode="text")
        self.assertTrue(any("缺少唯一同名 Markdown" in p for p in result["问题"]))

        draft = root / "临时工作" / "未知.md"
        draft.parent.mkdir()
        draft.write_text("# 未知\n", encoding="utf-8")
        exporter = load_exporter()
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            code = exporter.main([str(draft), "--项目目录", str(root)])
        self.assertEqual(code, 1)
        self.assertIn("错误：", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_pair_detects_image_bytes_and_link_targets(self):
        root = self.project()
        assets = root / "制作素材" / "测试"
        assets.mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (2, 2), (255, 0, 0)).save(assets / "a.png")
        Image.new("RGB", (2, 2), (0, 0, 255)).save(assets / "b.png")
        (assets / "a.txt").write_text("a", encoding="utf-8")
        (assets / "b.txt").write_text("b", encoding="utf-8")
        md = root / "归档" / "文档源稿" / "项目说明书.md"
        md.write_text("# 测试 项目说明书\n\n![图](../../制作素材/测试/a.png)\n\n[资料](../../制作素材/测试/a.txt)\n", encoding="utf-8")
        exporter = load_exporter()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(exporter.main([str(md), "--项目目录", str(root)]), 0)
        word = root / "项目说明书.docx"
        self.assertEqual(check_document_pair(md, word, root=root), [])

        def swap_image(name, data):
            return (assets / "b.png").read_bytes() if name.startswith("word/media/") else data
        rewrite_docx(word, swap_image)
        self.assertTrue(any("图片内容不一致" in p for p in check_document_pair(md, word, root=root)))

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(exporter.main([str(md), "--项目目录", str(root), "--更新"]), 0)
        def swap_link(name, data):
            if name == "word/_rels/document.xml.rels":
                return data.replace(b"a.txt", b"b.txt")
            return data
        rewrite_docx(word, swap_link)
        self.assertTrue(any("超链接目标不一致" in p for p in check_document_pair(md, word, root=root)))

    def test_draft_default_export_and_pending_report(self):
        root = self.project()
        current = root / "归档" / "文档源稿" / "分镜图提示词.md"
        current.write_text(IMAGE_VALID.replace("起始状态：人物甲坐在桌边。\n", ""), encoding="utf-8")
        exporter = load_exporter()
        current_stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(current_stderr):
            code = exporter.main([str(current), "--项目目录", str(root), "--草稿"])
        self.assertEqual(code, 0, current_stderr.getvalue())
        self.assertIn("待补：分镜镜头01：缺少起始状态", current_stderr.getvalue())
        self.assertTrue((root / "临时工作" / "导出预览" / "分镜图提示词.docx").is_file())

        draft = root / "临时工作" / "说明草稿.md"
        draft.parent.mkdir(exist_ok=True)
        draft.write_text("# 非正式说明草稿\n\n还在整理。\n", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            code = exporter.main([str(draft), "--项目目录", str(root), "--草稿"])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertTrue((root / "临时工作" / "导出预览" / "说明草稿.docx").is_file())

    def test_formal_failure_keeps_old_word(self):
        root = self.project()
        md = root / "归档" / "文档源稿" / "分镜图提示词.md"
        md.write_text(IMAGE_VALID.replace("起始状态：人物甲坐在桌边。\n", ""), encoding="utf-8")
        old = root / "分镜图提示词.docx"
        old.write_bytes(b"OLD-WORD-CONTENT")
        before = hashlib.sha256(old.read_bytes()).hexdigest()
        exporter = load_exporter()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = exporter.main([str(md), "--项目目录", str(root), "--更新"])
        self.assertEqual(code, 1)
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(), before)

    def test_formal_current_exports_to_project_root(self):
        root = self.project()
        md = root / "归档" / "文档源稿" / "分镜图提示词.md"
        md.write_text(IMAGE_VALID, encoding="utf-8")
        exporter = load_exporter()
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            code = exporter.main([str(md), "--项目目录", str(root)])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertTrue((root / "分镜图提示词.docx").is_file())

    def test_postcheck_failure_keeps_old_word(self):
        root = self.project()
        md = root / "归档" / "文档源稿" / "分镜图提示词.md"
        md.write_text(IMAGE_VALID, encoding="utf-8")
        old = root / "分镜图提示词.docx"
        old.write_bytes(b"OLD-WORD-CONTENT")
        before = old.read_bytes()
        import 检查项目
        original = 检查项目.check_document_pair
        检查项目.check_document_pair = lambda *args, **kwargs: ["模拟配对失败"]
        try:
            exporter = load_exporter()
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = exporter.main([str(md), "--项目目录", str(root), "--更新"])
        finally:
            检查项目.check_document_pair = original
        self.assertEqual(code, 1)
        self.assertEqual(old.read_bytes(), before)

    def test_text_mode_runs_without_site_packages(self):
        root = self.project()
        (root / "归档" / "文档源稿" / "分镜图提示词.md").write_text(IMAGE_VALID, encoding="utf-8")
        one_shot_video = VIDEO_VALID.split("\n## 镜头02", 1)[0] + "\n"
        (root / "归档" / "文档源稿" / "视频提示词与台词.md").write_text(one_shot_video, encoding="utf-8")
        run = subprocess.run(
            [sys.executable, "-S", "-B", "-X", "utf8", str(SCRIPTS / "检查项目.py"), str(root), "--模式", "text"],
            cwd=self.case, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('"模式": "text"', run.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--工作目录", required=True, type=Path)
    args, unittest_args = parser.parse_known_args()
    work = args.工作目录.expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = str(work)
    ExecutionTests.work = work
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExecutionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
