"""场景测试；仅在显式指定的项目临时目录中运行，不生成 skill 缓存。"""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "流程守卫.py"
spec = importlib.util.spec_from_file_location("workflow_guard", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Guard, GuardError = module.Guard, module.GuardError
GOOD = [{"name": "锁定关系与产品事实", "passed": True, "evidence": "测试样本设定逐项一致"}]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9KsAAAAASUVORK5CYII=")


def issue(identifier="对白解释过多", severity="blocking"):
    return {"id": identifier, "severity": severity, "location": "场2，第3句",
            "evidence": "人物复述观众已经看见的动作", "impact": "停滞人物交流", "fix": "改为可见反应"}


class GuardScenarios(unittest.TestCase):
    def setUp(self):
        configured = os.environ.get("VIDEO_WORKFLOW_TEST_ROOT")
        if not configured:
            raise RuntimeError("先设置 VIDEO_WORKFLOW_TEST_ROOT 到项目临时工作目录")
        boundary = Path(configured).resolve()
        if not boundary.is_dir() or boundary.is_relative_to(SCRIPT.parents[1]):
            raise RuntimeError("先探测并建立 skill 外的测试目录")
        self.temporary = tempfile.TemporaryDirectory(prefix="guard-", dir=boundary)
        self.project = Path(self.temporary.name).resolve()
        if not self.project.is_relative_to(boundary):
            raise RuntimeError("临时目录越界")
        self.addCleanup(self.temporary.cleanup)
        self.guard = Guard(self.project)
        self.guard.init(["父亲与女儿关系保持不变"])

    def apply(self, action, **values):
        return self.guard.apply({"action": action, **values})

    def write(self, filename, content):
        path = self.project / filename
        path.write_text(content, encoding="utf-8")
        return str(path)

    def candidate(self, content="父亲递出旧相册。女儿：这张我见过。", dimensions=None, bad_hard=False):
        event = {"file": self.write("剧本.md", content), "author": "writer", "hard_checks": GOOD}
        if bad_hard:
            event["hard_checks"] = [{"name": "产品事实", "passed": False, "evidence": "加入了未经证实的功能"}]
        if dimensions is not None:
            event["scope"] = {"summary": "只替换解释性台词", "locked_facts_check": "人物关系、结尾与事实逐项无变化",
                              "changed_facts": [], "downstream": ["镜2对白"], "dimensions": dimensions}
        state = self.apply("candidate", **event)
        return state["script"]["candidates"][-1]

    def reviews(self, candidate, issue_id=None, preference=False):
        for dimension in candidate["required_reviews"]:
            self.apply("review", candidate=candidate["id"], dimension=dimension, hash=candidate["hash"],
                       reviewer="reviewer-" + dimension, independent=True, full_read=True,
                       read_evidence="完整读取当前内容与锁定设定", hard_checks=GOOD,
                       issues=[issue(issue_id, "preference" if preference else "blocking")]
                       if issue_id and dimension == candidate["required_reviews"][0] else [])

    def decide(self, candidate, comparison=None):
        args = {"candidate": candidate["id"], "rationale": "按阻塞问题、硬约束与叙事表达比较"}
        if comparison:
            args["comparison"] = comparison
        return self.apply("decide", **args)

    def approved(self):
        candidate = self.candidate()
        self.reviews(candidate)
        self.decide(candidate)
        self.apply("owner_approval", candidate=candidate["id"], hash=candidate["hash"], approved=True,
                   message_ref="测试对话-owner-1", quote="批准这份剧本，进入资产。")

    def batch(self, names, kind="storyboard", mode="images"):
        if kind == "storyboard":
            self.apply("no_assets", reason="此测试样本仅验证独立文字/图像状态，无前置资产")
        self.apply("batch", id=kind, kind=kind, mode=mode, items=names)

    def image(self, name, good=False, existing=False, batch="storyboard"):
        filename = self.project / (name + ".png")
        filename.write_bytes(PNG)
        if existing:
            self.apply("image_existing", batch=batch, item=name, author="artist", file=str(filename))
        else:
            self.apply("image_reserve", batch=batch, item=name, author="artist")
            self.apply("image_result", batch=batch, item=name, called=True, file=str(filename), reference="模拟调用返回")
        attempt = self.guard.load()["batches"][batch]["items"][name]["attempts"][-1]
        self.apply("visual_review", batch=batch, item=name, hash=attempt["artifact"]["hash"],
                   reviewer="visual-reviewer", independent=True, viewed=True, read_evidence="测试视觉记录：核对身份、物件数量和空间",
                   hard_checks=GOOD, issues=[] if good else [issue("多出物件")])

    def test_internal_pass_still_requires_actual_owner_approval_record(self):
        candidate = self.candidate()
        self.reviews(candidate)
        state = self.decide(candidate)
        self.assertEqual(state["script"]["status"], "internal_pass")
        with self.assertRaisesRegex(GuardError, "owner"):
            self.apply("gate", stage="assets")
        with self.assertRaises(GuardError):
            self.apply("owner_approval", candidate="c1", hash=candidate["hash"], approved=True, quote="批准")
        self.apply("owner_approval", candidate="c1", hash=candidate["hash"], approved=True, message_ref="owner-message", quote="批准此稿")
        self.apply("gate", stage="assets")

    def test_missing_independence_hash_and_review_cannot_pass(self):
        candidate = self.candidate()
        with self.assertRaisesRegex(GuardError, "评审缺失"):
            self.decide(candidate)
        for fields in ({"hash": "old"}, {"reviewer": "writer"}, {"independent": False}):
            event = {"candidate": "c1", "dimension": "structure", "hash": candidate["hash"],
                     "reviewer": "reviewer", "independent": True, "read_evidence": "已读", "hard_checks": GOOD, "issues": []}
            event.update(fields)
            with self.assertRaises(GuardError):
                self.apply("review", **event)
        self.assertEqual(self.guard.load()["script"]["candidates"][0]["reviews"], {})

    def test_hard_failure_not_cancelled_by_clean_reviews_or_preferences(self):
        candidate = self.candidate(bad_hard=True)
        self.reviews(candidate, "可选偏好", preference=True)
        state = self.decide(candidate)
        self.assertEqual(state["script"]["status"], "needs_revision")
        self.assertFalse(state["script"]["candidates"][0]["decision"]["pass"])

    def test_local_revision_has_new_hash_related_dimension_and_final_read(self):
        first = self.candidate()
        self.reviews(first, "对白")
        self.decide(first)
        second = self.candidate("父亲翻开相册。女儿轻笑：原来是这里。", ["character"])
        self.assertEqual(second["required_reviews"], ["character", "final"])
        with self.assertRaisesRegex(GuardError, "hash"):
            self.apply("review", candidate="c2", dimension="character", hash=first["hash"], reviewer="reviewer-character",
                       independent=True, hard_checks=GOOD, issues=[], read_evidence="试图沿用旧稿")
        self.reviews(second)
        state = self.decide(second, "improved")
        self.assertEqual(state["script"]["status"], "internal_pass")
        self.assertEqual(state["script"]["best_id"], "c2")
        self.assertIn("递出旧相册", state["script"]["candidates"][0]["content"])

    def test_three_candidates_then_stop_keep_best(self):
        for index in range(3):
            candidate = self.candidate(f"候选内容 {index}", ["character"] if index else None)
            self.reviews(candidate, "问题" + str(index))
            state = self.decide(candidate, "initial" if not index else "equivalent")
        self.assertEqual(state["script"]["stop_reason"], "candidate_limit")
        self.assertEqual(state["script"]["best_id"], "c1")
        with self.assertRaises(GuardError):
            self.candidate("第四稿", ["character"])

    def test_repeated_issue_stops_after_first_revision(self):
        for index in range(2):
            candidate = self.candidate(f"内容 {index}", ["character"] if index else None)
            self.reviews(candidate, "相同实质问题")
            state = self.decide(candidate, "initial" if not index else "equivalent")
        self.assertEqual(state["script"]["stop_reason"], "repeated_substantive_issue")
        self.assertEqual(state["script"]["best_id"], "c1")

    def test_regression_preserves_best(self):
        first = self.candidate()
        self.reviews(first, "对白")
        self.decide(first)
        second = self.candidate("失去原本人物动机的新稿", ["character"])
        self.reviews(second, "动机")
        state = self.decide(second, "regressed")
        self.assertEqual(state["script"]["stop_reason"], "regression")
        self.assertEqual(state["script"]["best_id"], "c1")

    def test_equivalent_pass_keeps_approved_best_and_owner_approval_binds_it(self):
        self.approved()
        first = self.guard.load()["script"]["candidates"][0]
        self.apply("owner_change", requested=True, message_ref="owner-equivalent-revision",
                   quote="试一版相当的局部措辞，但保留更好的版本",
                   scope={"summary": "只改一句措辞", "locked_facts_check": "人物关系、产品事实和结尾不变",
                          "changed_facts": [], "downstream": [], "dimensions": ["character"]},
                   affected_items={}, downstream_check="没有既有下游资产")
        second = self.candidate("父亲递出旧相册。女儿轻声说：这张我记得。", ["character"])
        self.reviews(second)
        state = self.decide(second, "equivalent")
        self.assertEqual(state["script"]["status"], "internal_pass")
        self.assertEqual(state["script"]["best_id"], "c1")
        with self.assertRaisesRegex(GuardError, "选定通过候选"):
            self.apply("owner_approval", candidate="c2", hash=second["hash"], approved=True,
                       message_ref="owner-equivalent-revision", quote="批准最佳稿")
        self.write("剧本.md", first["content"])
        self.apply("owner_approval", candidate="c1", hash=first["hash"], approved=True,
                   message_ref="owner-equivalent-revision", quote="批准保留的最佳稿")
        approval = self.guard.load()["script"]["owner_approval"]
        self.assertEqual(approval["candidate"], "c1")
        self.assertEqual(approval["hash"], first["hash"])

    def test_equivalent_pass_rejects_failed_best_without_mutating_reviewing_state(self):
        first = self.candidate()
        self.reviews(first, "对白仍未解决")
        self.decide(first)
        second = self.candidate("父亲翻开相册。女儿看见照片后沉默。", ["character"])
        self.reviews(second)
        original = self.guard.path.read_bytes()
        with self.assertRaisesRegex(GuardError, "当前最佳候选未通过"):
            self.decide(second, "equivalent")
        self.assertEqual(self.guard.path.read_bytes(), original)
        rejected = self.guard.load()["script"]
        self.assertEqual(rejected["status"], "reviewing")
        self.assertEqual(rejected["best_id"], "c1")
        self.assertIsNone(rejected["candidates"][1]["decision"])
        corrected = self.decide(second, "improved")
        self.assertEqual(corrected["script"]["status"], "internal_pass")
        self.assertEqual(corrected["script"]["best_id"], "c2")
        self.assertTrue(corrected["script"]["candidates"][1]["decision"]["pass"])
        self.apply("owner_approval", candidate="c2", hash=second["hash"], approved=True,
                   message_ref="owner-corrected-comparison", quote="批准核实后的改进稿")
        self.assertEqual(self.guard.load()["script"]["owner_approval"]["candidate"], "c2")

    def test_shared_image_pool_prevents_four_items_each_using_repairs(self):
        self.approved()
        self.batch(["A", "B", "C", "D"])
        self.image("A")
        self.image("A", good=True)
        self.image("B")
        self.image("B", good=True)
        self.image("C")
        with self.assertRaises(GuardError):
            self.image("C", good=True)
        self.image("D", good=True)
        state = self.guard.load()
        self.assertEqual(state["batches"]["storyboard"]["extra_limit"], 2)
        self.assertEqual(state["calls"]["image_generation"], 6)
        self.assertEqual(state["batches"]["storyboard"]["status"], "stopped")
        with self.assertRaises(GuardError):
            self.apply("batch", id="new", kind="storyboard", mode="images", items=["C-new"])

    def test_image_initial_plus_two_repairs_and_no_pass_without_view(self):
        self.approved()
        self.batch(["A", "B", "C", "D", "E"])
        for _ in range(3):
            self.image("A")
        self.assertEqual(self.guard.load()["batches"]["storyboard"]["items"]["A"]["stop_reason"], "per_image_limit")
        with self.assertRaises(GuardError):
            self.image("A")
        with self.assertRaises(GuardError):
            self.apply("visual_review", batch="storyboard", item="B", viewed=True)

    def test_existing_image_needs_independent_review_and_overwrite_invalidates_gate(self):
        self.approved()
        self.batch(["A"])
        self.image("A", good=True, existing=True)
        self.assertNotIn("image_generation", self.guard.load()["calls"])
        self.apply("gate", stage="video")
        (self.project / "A.png").write_bytes(PNG + b"changed")
        with self.assertRaisesRegex(GuardError, "覆盖"):
            self.apply("gate", stage="video")

    def test_prompt_only_can_advance_video_without_visual_pass(self):
        self.approved()
        self.batch(["S01"], mode="prompt_only")
        state = self.apply("prompt", batch="storyboard", item="S01", author="writer", file=self.write("分镜.md", "客厅，父亲把相册放在桌上。"))
        artifact = state["batches"]["storyboard"]["items"]["S01"]["attempts"][-1]["artifact"]
        self.apply("prompt_review", batch="storyboard", item="S01", hash=artifact["hash"], reviewer="reviewer", independent=True,
                   read_evidence="已读提示词并对照锁定项，未看图", hard_checks=GOOD, issues=[])
        self.apply("gate", stage="video")
        self.assertEqual(self.guard.load()["batches"]["storyboard"]["status"], "prompt_only_pass")
        with self.assertRaises(GuardError):
            self.apply("visual_review", batch="storyboard", item="S01", viewed=True)

    def test_goals_do_not_reset_calls_candidates_or_usage(self):
        self.apply("goal", id="goal1", scope="剧本至 owner gate")
        self.candidate()
        self.apply("call", kind="review_agent", count=3, reference="三个子代理实际启动")
        self.apply("usage", goal_id="goal1", tokens=1200, source="get_goal 实际累计读数")
        self.apply("goal", id="goal2", scope="续接当前状态")
        second = Guard(self.project)
        self.assertEqual(second.summary()["actual_calls_total"], 3)
        self.assertEqual(second.summary()["candidate_count"], 1)
        self.assertEqual(second.summary()["unmeasured_goals"], ["goal2"])
        with self.assertRaises(GuardError):
            second.init([])
        with self.assertRaises(GuardError):
            self.apply("usage", goal_id="goal1", tokens=900, source="倒退")

    def test_failed_or_undispatched_image_is_never_counted_as_visual_pass(self):
        self.approved()
        self.batch(["A", "B"])
        for name, called in (("A", True), ("B", False)):
            self.apply("image_reserve", batch="storyboard", item=name, author="artist")
            self.apply("image_result", batch="storyboard", item=name, called=called, reference="工具失败" if called else "未发出调用")
        self.assertEqual(self.guard.summary()["actual_calls_total"], 1)
        self.assertNotEqual(self.guard.load()["batches"]["storyboard"]["status"], "visual_pass")

    def test_atomic_failure_preserves_original_and_cli_reads_it(self):
        original = self.guard.path.read_bytes()
        with patch.object(module.os, "replace", side_effect=PermissionError("模拟文件占用")):
            with self.assertRaises(PermissionError):
                self.apply("goal", id="goal1", scope="测试")
        self.assertEqual(self.guard.path.read_bytes(), original)
        self.assertEqual(list(self.guard.path.parent.glob(".流程状态-*.tmp")), [])
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPT), str(self.project), "status"],
                                capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads(result.stdout)["measured_tokens"])

    def test_existing_approval_adoption_does_not_fabricate_internal_reviews(self):
        path = self.write("旧剧本.md", "用户已批准的原文")
        content_hash = module.digest(Path(path).read_bytes())
        self.apply("adopt_approved", file=path, hash=content_hash, author="owner-original", approved=True,
                   message_ref="实际旧批准消息", quote="确认这份稿子，继续做资产")
        self.apply("gate", stage="assets")
        state = self.guard.load()
        self.assertEqual(state["script"]["status"], "owner_approved")
        self.assertEqual(state["script"]["candidates"][0]["reviews"], {})
        self.assertIsNone(state["script"]["candidates"][0]["decision"]["pass"])

    def test_new_owner_request_opens_local_cycle_without_resetting_calls(self):
        self.approved()
        self.apply("call", kind="review_agent", count=3, reference="原三审已运行")
        scope = {"summary": "owner 要求改最后一句", "locked_facts_check": "关系与结尾动作无变化",
                 "changed_facts": [], "downstream": ["结尾对白"], "dimensions": ["character"]}
        with self.assertRaises(GuardError):
            self.apply("owner_change", requested=True, scope=scope, affected_batches=[], downstream_check="尚无下游")
        self.apply("owner_change", requested=True, message_ref="owner-message-2", quote="最后一句更克制一点",
                   scope=scope, affected_batches=[], downstream_check="尚无下游资产")
        candidate = self.candidate("父亲合上相册。女儿点头：我记得。", ["character"])
        self.assertEqual(candidate["required_reviews"], ["character", "final"])
        self.reviews(candidate)
        state = self.decide(candidate, "improved")
        self.assertEqual(state["script"]["cycle"], 2)
        self.assertEqual(len(state["script"]["candidates"]), 2)
        self.assertEqual(len(state["script"]["history"]), 1)
        self.assertEqual(state["calls"]["review_agent"], 3)
        with self.assertRaises(GuardError):
            self.apply("gate", stage="assets")

    def test_storyboard_cannot_skip_missing_or_failed_asset_batch(self):
        self.approved()
        with self.assertRaisesRegex(GuardError, "no_assets"):
            self.apply("batch", id="storyboard", kind="storyboard", mode="prompt_only", items=["S01"])
        self.apply("batch", id="assets", kind="assets", mode="images", items=["父亲"])
        with self.assertRaisesRegex(GuardError, "资产尚未"):
            self.apply("batch", id="storyboard", kind="storyboard", mode="prompt_only", items=["S01"])
        with self.assertRaises(GuardError):
            self.apply("no_assets", reason="试图跳过资产")

    def test_approved_script_overwrite_blocks_assets(self):
        self.approved()
        self.write("剧本.md", "加入未经批准的新功能")
        with self.assertRaisesRegex(GuardError, "旧批准失效"):
            self.apply("gate", stage="assets")

    def test_prompt_overwrite_invalidates_review_and_video_gate(self):
        self.approved()
        self.batch(["S01"], mode="prompt_only")
        path = self.write("分镜.md", "父亲坐在窗边。")
        state = self.apply("prompt", batch="storyboard", item="S01", author="writer", file=path)
        artifact = state["batches"]["storyboard"]["items"]["S01"]["attempts"][-1]["artifact"]
        self.write("分镜.md", "女儿离开客厅。")
        review = {"batch": "storyboard", "item": "S01", "hash": artifact["hash"], "reviewer": "reviewer",
                  "independent": True, "read_evidence": "读取并核对全文", "hard_checks": GOOD, "issues": []}
        with self.assertRaisesRegex(GuardError, "提示词已变化"):
            self.apply("prompt_review", **review)
        self.write("分镜.md", "父亲坐在窗边。")
        self.apply("prompt_review", **review)
        self.write("分镜.md", "又变成另一份未审提示词。")
        with self.assertRaisesRegex(GuardError, "提示词文件已变化"):
            self.apply("gate", stage="video")

    def test_state_directory_link_cannot_escape_project(self):
        nested = self.project / "链接项目"
        nested.mkdir()
        outside = self.project / "外部目录"
        outside.mkdir()
        link = nested / "临时工作"
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaisesRegex(GuardError, "越出项目"):
                Guard(nested).init([])
            self.assertFalse((outside / "流程状态.json").exists())
        finally:
            if os.name == "nt":
                link.rmdir()
            else:
                link.unlink()

    def local_owner_change(self, affected_items=None, affected_batches=None, content="新请求后只修改一句对白。"):
        event = {"requested": True, "message_ref": "真实owner局部请求", "quote": "只核对父亲手机，其他保持不变",
                 "scope": {"summary": "局部措辞与相关物件核对", "locked_facts_check": "关系、产品事实、结尾逐项核对",
                           "changed_facts": [], "downstream": ["父亲手机"], "dimensions": ["character"]},
                 "downstream_check": "只列出的项目需要重审，其余身份、服装、空间未变"}
        if affected_items is not None:
            event["affected_items"] = affected_items
        if affected_batches is not None:
            event["affected_batches"] = affected_batches
        self.apply("owner_change", **event)
        candidate = self.candidate(content, ["character"])
        self.reviews(candidate)
        self.decide(candidate, "improved")
        self.apply("owner_approval", candidate=candidate["id"], hash=candidate["hash"], approved=True,
                   message_ref="本次修改批准", quote="批准这次局部修改，继续核对相关项目")

    def test_local_asset_revalidation_keeps_other_three_images_frozen_and_uses_no_generation(self):
        self.approved()
        names = ["父亲手机", "父亲", "女儿", "客厅"]
        self.batch(names, kind="assets")
        self.image("父亲手机", good=False, batch="assets")
        for name in names:
            self.image(name, good=True, batch="assets")
        before = self.guard.load()
        self.local_owner_change(affected_items={"assets": ["父亲手机"]})
        changed = self.guard.load()
        for name in names[1:]:
            self.assertEqual(changed["batches"]["assets"]["items"][name], before["batches"]["assets"]["items"][name])
        phone = changed["batches"]["assets"]["items"]["父亲手机"]
        self.assertEqual(phone["status"], "awaiting_visual_review")
        attempt = phone["attempts"][-1]
        self.assertIsNone(attempt["review"])
        self.assertEqual(attempt["prior_reviews"], [before["batches"]["assets"]["items"]["父亲手机"]["attempts"][-1]["review"]])
        self.apply("visual_review", batch="assets", item="父亲手机", hash=attempt["artifact"]["hash"],
                   reviewer="new-visual-reviewer", independent=True, viewed=True, read_evidence="按新设定实际重看已有手机图，无需生成",
                   hard_checks=GOOD, issues=[])
        after = self.guard.load()
        self.assertEqual(after["batches"]["assets"]["status"], "visual_pass")
        self.assertEqual(after["calls"], before["calls"])
        self.assertEqual(after["calls"]["image_generation"], 5)
        self.assertEqual(after["batches"]["assets"]["repairs_reserved"], before["batches"]["assets"]["repairs_reserved"])
        self.assertEqual(after["batches"]["assets"]["repairs_reserved"], 1)
        self.assertEqual(len(after["batches"]["assets"]["items"]["父亲手机"]["attempts"]), 2)

    def test_prompt_revalidation_preserves_history_and_changed_text_requires_new_candidate(self):
        self.approved()
        self.batch(["S01"], mode="prompt_only")
        path = self.write("分镜.md", "父亲把手机放在桌上。")
        initial = self.apply("prompt", batch="storyboard", item="S01", author="writer", file=path)
        artifact = initial["batches"]["storyboard"]["items"]["S01"]["attempts"][-1]["artifact"]
        review = {"batch": "storyboard", "item": "S01", "hash": artifact["hash"], "reviewer": "prompt-reviewer",
                  "independent": True, "read_evidence": "当前全文与锁定项一致", "hard_checks": GOOD, "issues": []}
        self.apply("prompt_review", **review)
        self.local_owner_change(affected_items={"storyboard": ["S01"]})
        reopened = self.guard.load()["batches"]["storyboard"]["items"]["S01"]
        self.assertEqual(reopened["status"], "awaiting_prompt_review")
        self.assertEqual(len(reopened["attempts"][-1]["prior_reviews"]), 1)
        self.apply("prompt_review", **review)
        self.assertEqual(len(self.guard.load()["batches"]["storyboard"]["items"]["S01"]["attempts"]), 1)
        self.local_owner_change(affected_batches=["storyboard"], content="第二次真实请求之后修改动作。")
        self.write("分镜.md", "父亲把手机递给女儿。")
        with self.assertRaisesRegex(GuardError, "提示词已变化"):
            self.apply("prompt_review", **review)
        state = self.apply("prompt", batch="storyboard", item="S01", author="writer", file=path)
        attempts = state["batches"]["storyboard"]["items"]["S01"]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(attempts[0]["prior_reviews"]), 2)
        with self.assertRaisesRegex(GuardError, "hash"):
            self.apply("prompt_review", **review)
        review["hash"] = attempts[-1]["artifact"]["hash"]
        self.apply("prompt_review", **review)
        self.apply("gate", stage="video")
        self.assertEqual(self.guard.summary()["actual_calls_total"], 0)

    def test_invalid_local_item_does_not_reopen_or_mutate_state(self):
        self.approved()
        self.batch(["父亲手机"], kind="assets")
        self.image("父亲手机", good=True, batch="assets")
        original = self.guard.path.read_bytes()
        with self.assertRaisesRegex(GuardError, "受影响项目"):
            self.local_owner_change(affected_items={"assets": ["不存在的手机"]})
        self.assertEqual(self.guard.path.read_bytes(), original)

    def downstream_only_event(self):
        return {"requested": True, "script_unchanged": True, "message_ref": "owner-phone-appearance-only",
                "quote": "只检查父亲手机的外观，剧本和其他三张图不动，继续做",
                "scope": {"summary": "仅核对手机背壳外观", "locked_facts_check": "剧本、人物关系、功能和动作均不改",
                          "script_unchanged_reason": "手机背壳颜色未在剧本文字中指定，外观要求不改变剧情或功能事实",
                          "changed_facts": ["手机背壳按新外观要求核对"], "downstream": ["父亲手机"], "dimensions": []},
                "affected_items": {"assets": ["父亲手机"]},
                "downstream_check": "只核对父亲手机；其余人物与环境无依赖变化"}

    def test_downstream_only_change_keeps_script_approval_cycle_text_and_other_images(self):
        self.approved()
        names = ["父亲手机", "父亲", "女儿", "客厅"]
        self.batch(names, kind="assets")
        self.image("父亲手机", good=False, batch="assets")
        for name in names:
            self.image(name, good=True, batch="assets")
        before = self.guard.load()
        script_bytes = (self.project / "剧本.md").read_bytes()
        self.apply("owner_change", **self.downstream_only_event())
        changed = self.guard.load()
        for key, value in before["script"].items():
            if key != "history":
                self.assertEqual(changed["script"][key], value, key)
        self.assertEqual((self.project / "剧本.md").read_bytes(), script_bytes)
        self.assertTrue(changed["script"]["history"][-1]["new_owner_request"]["script_unchanged"])
        for name in names[1:]:
            self.assertEqual(changed["batches"]["assets"]["items"][name], before["batches"]["assets"]["items"][name])
        phone = changed["batches"]["assets"]["items"]["父亲手机"]
        self.assertEqual(phone["status"], "awaiting_visual_review")
        self.apply("visual_review", batch="assets", item="父亲手机", hash=phone["attempts"][-1]["artifact"]["hash"],
                   reviewer="new-visual-reviewer", independent=True, viewed=True, read_evidence="按新外观要求重看已有手机图",
                   hard_checks=GOOD, issues=[])
        after = self.guard.load()
        self.assertEqual(after["batches"]["assets"]["status"], "visual_pass")
        self.assertEqual(after["calls"], before["calls"])
        self.assertEqual(after["batches"]["assets"]["repairs_reserved"], 1)
        self.assertEqual(after["script"]["candidates"], before["script"]["candidates"])
        self.assertEqual(after["script"]["cycle"], before["script"]["cycle"])

    def test_downstream_only_flag_rejects_changed_script_and_missing_scope_reason(self):
        self.approved()
        self.batch(["父亲手机"], kind="assets")
        self.image("父亲手机", good=True, batch="assets")
        original = self.guard.path.read_bytes()
        event = self.downstream_only_event()
        del event["scope"]["script_unchanged_reason"]
        with self.assertRaisesRegex(GuardError, "不受"):
            self.apply("owner_change", **event)
        self.assertEqual(self.guard.path.read_bytes(), original)
        self.write("剧本.md", "剧本已经被实质改写，不能沿用原批准")
        with self.assertRaisesRegex(GuardError, "旧批准失效"):
            self.apply("owner_change", **self.downstream_only_event())
        self.assertEqual(self.guard.path.read_bytes(), original)

    def test_owner_requested_restore_can_reuse_history_without_resetting_calls_or_image_pool(self):
        self.approved()
        original = self.guard.load()["script"]["candidates"][0]
        self.apply("call", kind="review_agent", count=3, reference="已实际完成原三审")
        self.batch(["父亲手机"], kind="assets")
        self.image("父亲手机", good=False, batch="assets")
        self.image("父亲手机", good=True, batch="assets")
        self.local_owner_change(affected_items={}, content="第二周期的新剧本文字。")
        before = self.guard.load()
        self.apply("owner_change", requested=True, message_ref="owner-restore-original", quote="恢复最早批准的剧本原文，资产沿用",
                   scope={"summary": "按owner要求恢复首稿", "locked_facts_check": "首稿功能和关系符合当前要求",
                          "changed_facts": [], "downstream": [], "dimensions": ["character"]},
                   affected_items={}, downstream_check="现有手机资产同时适用于原稿与改稿，无需重开")
        restored = self.candidate(original["content"], ["character"])
        self.assertEqual(restored["hash"], original["hash"])
        self.assertEqual(restored["reused_from"], original["id"])
        self.assertEqual(restored["reviews"], {})
        with self.assertRaises(GuardError):
            self.apply("owner_approval", candidate=restored["id"], hash=restored["hash"], approved=True,
                       message_ref="owner-restore-original", quote="恢复首稿继续")
        self.reviews(restored)
        self.decide(restored, "improved")
        self.apply("owner_approval", candidate=restored["id"], hash=restored["hash"], approved=True,
                   message_ref="owner-restore-original", quote="恢复最早批准的剧本原文，资产沿用")
        after = self.guard.load()
        self.assertEqual(after["calls"], before["calls"])
        self.assertEqual(after["batches"], before["batches"])
        self.assertEqual(len(after["script"]["candidates"]), 3)

    def test_same_cycle_repeated_content_is_still_rejected(self):
        first = self.candidate()
        self.reviews(first, "实质问题待修复")
        self.decide(first)
        original = self.guard.path.read_bytes()
        with self.assertRaisesRegex(GuardError, "同周期"):
            self.candidate(first["content"], ["character"])
        self.assertEqual(self.guard.path.read_bytes(), original)

    def test_summary_omits_prompt_and_review_evidence_but_keeps_current_hash(self):
        self.approved()
        self.batch(["S01"], mode="prompt_only")
        long_prompt = "只应在完整状态中保存的长提示词正文。" * 1000
        state = self.apply("prompt", batch="storyboard", item="S01", author="writer", file=self.write("长分镜.md", long_prompt))
        artifact = state["batches"]["storyboard"]["items"]["S01"]["attempts"][-1]["artifact"]
        self.apply("prompt_review", batch="storyboard", item="S01", hash=artifact["hash"], reviewer="prompt-reviewer",
                   independent=True, read_evidence="只应留在完整状态的独立评审证据", hard_checks=GOOD, issues=[])
        summary = self.guard.summary()
        encoded = json.dumps(summary, ensure_ascii=False)
        for forbidden in ("长提示词正文", "独立评审证据", "content", "prior_reviews", "hard_checks", "issues"):
            self.assertNotIn(forbidden, encoded)
        item = summary["batches"]["storyboard"]["items"]["S01"]
        self.assertEqual(item["artifact"]["hash"], artifact["hash"])
        self.assertEqual(item["attempt_count"], 1)
        self.assertTrue(item["review_pass"])
        self.assertEqual(self.guard.load()["batches"]["storyboard"]["items"]["S01"]["attempts"][0]["artifact"]["content"], long_prompt)


if __name__ == "__main__":
    unittest.main()
