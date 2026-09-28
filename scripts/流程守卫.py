#!/usr/bin/env python3
"""单项目、单写手的有界流程记录器。只验证记录，不证明人的身份或审美。"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

DIMENSIONS = ("structure", "character", "brand")
SCHEMA = 1


class GuardError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise GuardError(message)


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}不能为空")
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def checks(value):
    require(isinstance(value, list) and value, "必须逐项记录硬约束检查，不能用总分代替")
    for item in value:
        nonempty(item.get("name"), "硬约束名称")
        nonempty(item.get("evidence"), "硬约束证据")
        require(type(item.get("passed")) is bool, "硬约束 passed 必须是布尔值")
    return copy.deepcopy(value)


def issues(value):
    require(isinstance(value, list) and len(value) <= 3, "每次独立评审至多三条证据化问题")
    identifiers = set()
    for item in value:
        for key in ("id", "location", "evidence", "impact", "fix"):
            nonempty(item.get(key), f"问题 {key}")
        require(item.get("severity") in ("hard", "blocking", "preference"), "问题严重性无效")
        require(item["id"] not in identifiers, "同次评审的问题 ID 重复")
        identifiers.add(item["id"])
    return copy.deepcopy(value)


def passed(review):
    return all(x["passed"] for x in review["hard_checks"]) and not any(
        x["severity"] != "preference" for x in review["issues"])


class Guard:
    """只由宿主主代理调用；子代理只返回评审，不写状态。无并发锁。"""

    def __init__(self, project, writer="main"):
        self.project = Path(project).resolve()
        skill = Path(__file__).resolve().parents[1]
        require(not self.project.is_relative_to(skill), "项目和运行输出不能放在 skill 内")
        self.path = self.project / "临时工作" / "流程状态.json"
        self.writer = nonempty(writer, "写手")

    def load(self):
        self._location()
        require(self.path.is_file(), "尚未初始化项目流程")
        state = json.loads(self.path.read_text(encoding="utf-8"))
        require(state.get("schema") == SCHEMA, "不支持此状态版本")
        require(state.get("project") == str(self.project), "状态不属于此项目；不要复制状态重置额度")
        return state

    def _location(self):
        require(self.path.resolve().is_relative_to(self.project)
                and self.path.parent.resolve().is_relative_to(self.project),
                "临时工作/状态路径经链接解析后越出项目，拒绝读写")

    def _save(self, state, expected_revision=None):
        self._location()
        # 原子替换防止半份 JSON；revision 只发现常见误用，不是并发锁。
        if expected_revision is not None:
            require(self.load()["revision"] == expected_revision, "状态已变化；禁止并发写入")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".流程状态-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def init(self, locked_facts):
        require(not self.path.exists(), "状态已存在；禁止重新初始化或通过新 Goal 重置计数")
        require(isinstance(locked_facts, list), "locked_facts 必须是列表")
        for fact in locked_facts:
            nonempty(fact, "锁定事实")
        state = {"schema": SCHEMA, "project": str(self.project), "writer": self.writer,
                 "revision": 0, "created_at": now(), "locked_facts": locked_facts,
                 "goals": [], "calls": {}, "token_usage": {}, "events": [],
                 "script": {"status": "draft", "candidates": [], "best_id": None, "cycle": 1,
                            "cycle_scope": None, "history": [], "stop_reason": None,
                            "owner_approval": None}, "batches": {}, "no_assets": None}
        self._save(state)
        return state

    def _file(self, name, image=False):
        path = Path(nonempty(name, "文件路径"))
        path = (self.project / path).resolve() if not path.is_absolute() else path.resolve()
        require(path.is_relative_to(self.project), "源稿和选用图须位于当前项目")
        require(path.is_file(), f"文件不存在：{path}")
        data = path.read_bytes()
        require(bool(data), "文件为空")
        record = {"path": str(path), "hash": digest(data)}
        if image:
            is_image = (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")
                        or data.startswith((b"GIF87a", b"GIF89a", b"BM", b"II*\x00", b"MM\x00*"))
                        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"))
            require(is_image, "仅接受有已识别图片签名的 PNG/JPEG/GIF/BMP/TIFF/WebP；仍须实际看图")
        else:
            record["content"] = data.decode("utf-8-sig")
        return record

    @staticmethod
    def _candidate(state, identifier):
        for candidate in state["script"]["candidates"]:
            if candidate["id"] == identifier:
                return candidate
        raise GuardError("候选不存在")

    @staticmethod
    def _review(event, author, content_hash):
        require(event.get("hash") == content_hash, "评审 hash 与本次内容不符；旧评审不能复用")
        reviewer = nonempty(event.get("reviewer"), "独立评审标识")
        require(reviewer != author and event.get("independent") is True, "缺少独立评审声明，或主笔自行评审")
        nonempty(event.get("read_evidence"), "实际阅读/查看记录")
        return {"hash": content_hash, "reviewer": reviewer, "independent": True,
                "read_evidence": event["read_evidence"], "issues": issues(event.get("issues")),
                "hard_checks": checks(event.get("hard_checks")), "recorded_at": now()}

    @staticmethod
    def _count(state, kind, count=1):
        state["calls"][kind] = state["calls"].get(kind, 0) + count

    def _approved(self, state):
        script = state["script"]
        require(script["status"] == "owner_approved" and script["owner_approval"],
                "尚未记录 owner 对内部通过候选的实际批准；内部 pass 不能进入资产")
        candidate = self._candidate(state, script["best_id"])
        require(self._file(candidate["path"])["hash"] == script["owner_approval"]["hash"] == candidate["hash"],
                "当前选定剧本文件已变化，旧批准失效；须恢复批准内容或记录 owner 新修改请求")

    def _assets_ready(self, state):
        assets = [b for b in state["batches"].values() if b["kind"] == "assets"]
        require(assets or state["no_assets"], "先完成资产批次，或以 no_assets 明确记录本片无必需资产的依据")
        for batch in assets:
            require(batch["status"] == "visual_pass", "必需资产尚未全部 visual_pass，不能进入分镜")
            self._verify_images(batch)

    def _batch(self, state, event):
        require(event.get("batch") in state["batches"], "批次不存在")
        return state["batches"][event["batch"]]

    def _item(self, state, event):
        batch = self._batch(state, event)
        self._approved(state)
        if batch["kind"] == "storyboard":
            self._assets_ready(state)
        require(event.get("item") in batch["items"], "图片/提示词项目不存在")
        return batch, batch["items"][event["item"]]

    @staticmethod
    def _refresh(batch):
        statuses = [item["status"] for item in batch["items"].values()]
        success = "visual_pass" if batch["mode"] == "images" else "prompt_only_pass"
        batch["status"] = success if all(s == success for s in statuses) else "pending"
        if batch["mode"] == "images":
            for item in batch["items"].values():
                if item["status"] == "needs_fix":
                    if len(item["attempts"]) >= 3:
                        item["stop_reason"] = "per_image_limit"
                    elif batch["repairs_reserved"] >= batch["extra_limit"]:
                        item["stop_reason"] = "batch_extra_limit"
                    if item.get("stop_reason"):
                        batch["status"] = "stopped"

    def _verify_images(self, batch):
        for item in batch["items"].values():
            if item["status"] == "visual_pass":
                artifact = item["attempts"][-1]["artifact"]
                require(self._file(artifact["path"], image=True)["hash"] == artifact["hash"],
                        "已通过图片已被覆盖；原评审失效，不能沿用 visual_pass")
            elif item["status"] == "prompt_only_pass":
                artifact = item["attempts"][-1]["artifact"]
                require(self._file(artifact["path"])["hash"] == artifact["hash"],
                        "已通过提示词文件已变化；不能沿用旧 prompt_only_pass")

    def apply(self, event):
        state = self.load()
        require(state["writer"] == self.writer, "仅登记的宿主主代理可写；子代理交回结果")
        revision = state["revision"]
        action = event.get("action")
        script = state["script"]
        active = [c for c in script["candidates"] if c["cycle"] == script["cycle"]]
        if action == "goal":
            identifier = nonempty(event.get("id"), "Goal ID")
            require(identifier not in [g["id"] for g in state["goals"]], "Goal 已登记")
            state["goals"].append({"id": identifier, "scope": nonempty(event.get("scope"), "阶段范围")})
        elif action == "usage":
            identifier = event.get("goal_id")
            require(identifier in [g["id"] for g in state["goals"]], "先登记 Goal")
            tokens = event.get("tokens")
            require(type(tokens) is int and tokens >= 0, "只登记实际测得的累计 token；未知时不调用 usage")
            require(tokens >= state["token_usage"].get(identifier, {}).get("tokens", 0), "同一 Goal 的实际累计用量不能倒退")
            state["token_usage"][identifier] = {"tokens": tokens,
                                                "source": nonempty(event.get("source"), "真实测量来源")}
        elif action == "call":
            kind = nonempty(event.get("kind"), "调用种类")
            require(kind != "image_generation", "图像实际调用由 image_result 自动登记，不能重复手填")
            count = event.get("count", 1)
            require(type(count) is int and count > 0, "调用次数必须为正整数")
            nonempty(event.get("reference"), "调用事实引用")
            self._count(state, kind, count)
        elif action == "adopt_approved":
            require(not script["candidates"] and script["status"] == "draft", "仅用于接入已有批准的旧项目，不覆盖现有候选")
            require(event.get("approved") is True, "必须有 owner 真实批准")
            artifact = self._file(event.get("file"))
            require(event.get("hash") == artifact["hash"], "既有批准必须绑定当前文件的真实 hash")
            approval = {"candidate": "c1", "hash": artifact["hash"], "origin": "existing_owner_approval",
                        "message_ref": nonempty(event.get("message_ref"), "已有 owner 消息引用"),
                        "quote": nonempty(event.get("quote"), "已有批准原话"), "recorded_at": now()}
            script["candidates"].append({"id": "c1", "cycle": script["cycle"], **artifact,
                "author": nonempty(event.get("author"), "原稿作者/来源"), "hard_checks": [],
                "scope": None, "base": None, "required_reviews": [], "reviews": {},
                "decision": {"pass": None, "origin": "existing_owner_approval", "rationale": "沿用真实 owner 批准，未声称执行本轮内部三审"}})
            script.update(status="owner_approved", best_id="c1", owner_approval=approval, stop_reason="existing_owner_approval")
        elif action == "owner_change":
            require(script["status"] in ("owner_approved", "internal_pass", "stopped"), "当前轮次尚未收敛；先处理当前真实状态")
            require(event.get("requested") is True, "修改只可由 owner 实际新要求触发")
            nonempty(event.get("message_ref"), "owner 新请求引用")
            nonempty(event.get("quote"), "owner 新修改原话")
            script_unchanged = event.get("script_unchanged", False)
            require(type(script_unchanged) is bool, "script_unchanged 必须是布尔值")
            scope = event.get("scope")
            self._scope(scope, allow_empty_dimensions=script_unchanged)
            if script_unchanged:
                self._approved(state)
                nonempty(scope.get("script_unchanged_reason"), "须具体说明剧本为何不受此次下游修改影响")
            affected = event.get("affected_batches", [])
            require(isinstance(affected, list) and set(affected) <= set(state["batches"]), "affected_batches 仅列整批受影响的现有批次")
            affected_items = event.get("affected_items", {})
            require(isinstance(affected_items, dict) and set(affected_items) <= set(state["batches"]),
                    "affected_items 须为现有批次到具体项目列表的映射")
            require(not (set(affected) & set(affected_items)), "同一批次不能同时声明整批和局部失效")
            targets = {identifier: list(state["batches"][identifier]["items"]) for identifier in affected}
            for identifier, names in affected_items.items():
                require(isinstance(names, list) and names and len(set(names)) == len(names)
                        and set(names) <= set(state["batches"][identifier]["items"]), "受影响项目须存在且不重复")
                targets[identifier] = names
            require("affected_batches" in event or "affected_items" in event, "须明确下游失效范围，无变化则传空映射")
            nonempty(event.get("downstream_check"), "现有下游影响/不受影响依据")
            script["history"].append({"cycle": script["cycle"], "status": script["status"],
                "best_id": script["best_id"], "owner_approval": script["owner_approval"], "stop_reason": script["stop_reason"],
                "new_owner_request": copy.deepcopy(event)})
            if not script_unchanged:
                script.update(cycle=script["cycle"] + 1, cycle_scope=scope, status="draft", owner_approval=None, stop_reason=None)
            for identifier, names in targets.items():
                batch = state["batches"][identifier]
                for name in names:
                    item = batch["items"][name]
                    if item["status"] in ("visual_pass", "prompt_only_pass"):
                        attempt = item["attempts"][-1]
                        attempt.setdefault("prior_reviews", []).append(attempt["review"])
                        attempt["review"] = None
                        item["status"] = "awaiting_visual_review" if batch["mode"] == "images" else "awaiting_prompt_review"
                self._refresh(batch)
        elif action == "candidate":
            require(script["status"] in ("draft", "needs_revision"), "已通过、已停止或尚未完成评审；不能继续自动改稿")
            require(len(active) < 3, "本轮已达初稿加两次修订上限")
            artifact = self._file(event.get("file"))
            require(artifact["hash"] not in [c["hash"] for c in active], "同周期候选内容没有变化，禁止空转")
            reused_from = next((c["id"] for c in reversed(script["candidates"]) if c["hash"] == artifact["hash"]), None)
            author = nonempty(event.get("author"), "主笔标识")
            scope = event.get("scope", script["cycle_scope"])
            required = list(DIMENSIONS)
            base = None
            if script["candidates"]:
                self._scope(scope)
                dimensions = scope["dimensions"]
                base = event.get("base", script["best_id"])
                self._candidate(state, base)
                required = list(dimensions) + ["final"]
            identifier = f"c{len(script['candidates']) + 1}"
            script["candidates"].append({"id": identifier, "cycle": script["cycle"], **artifact, "author": author,
                                         "hard_checks": checks(event.get("hard_checks")), "scope": scope,
                                         "base": base, "reused_from": reused_from, "required_reviews": required,
                                         "reviews": {}, "decision": None})
            script["status"] = "reviewing"
        elif action == "review":
            candidate = self._candidate(state, event.get("candidate"))
            require(script["status"] == "reviewing" and candidate["decision"] is None, "此候选评审已封存")
            dimension = event.get("dimension")
            require(dimension in candidate["required_reviews"], "此维度不在本次声明的复审范围")
            require(dimension not in candidate["reviews"], "不能覆盖独立评审；问题需在下一候选修复")
            review = self._review(event, candidate["author"], candidate["hash"])
            require(event.get("full_read") is True, "剧本评审须完整读取当前候选全文，不能只读主笔摘要")
            review["full_read"] = True
            if dimension != "final":
                require(review["reviewer"] not in [r["reviewer"] for d, r in candidate["reviews"].items() if d != "final"],
                        "三个专业维度应由不同独立评审负责")
            candidate["reviews"][dimension] = review
        elif action == "decide":
            candidate = self._candidate(state, event.get("candidate"))
            require(script["status"] == "reviewing" and candidate["decision"] is None, "此候选不能再次裁决")
            require(set(candidate["required_reviews"]) <= set(candidate["reviews"]), "独立评审缺失，不能判定通过")
            rationale = nonempty(event.get("rationale"), "最佳候选比较依据")
            comparison = event.get("comparison", "initial" if len(script["candidates"]) == 1 else None)
            require(comparison in ("initial", "improved", "equivalent", "regressed", "oscillating"), "须判断较最佳候选进步、相当、退步或反复")
            require((candidate["id"] == "c1") == (comparison == "initial"), "只有初稿使用 initial")
            success = all(c["passed"] for c in candidate["hard_checks"]) and all(passed(r) for r in candidate["reviews"].values())
            substantive = {i["id"] for r in candidate["reviews"].values() for i in r["issues"] if i["severity"] != "preference"}
            previous = {i["id"] for c in active if c["id"] != candidate["id"]
                        for r in c["reviews"].values() for i in r["issues"] if i["severity"] != "preference"}
            reason = ("regression" if comparison == "regressed" else "oscillation" if comparison == "oscillating"
                      else "repeated_substantive_issue" if substantive & previous else None)
            if comparison == "equivalent" and success and reason is None and script["best_id"] is not None:
                best = self._candidate(state, script["best_id"])
                require(best["decision"] and best["decision"].get("pass") is True,
                        "相当候选通过但当前最佳候选未通过；请核实比较结论，确有进步时改用 improved")
            candidate["decision"] = {"pass": success and reason is None, "comparison": comparison, "rationale": rationale}
            if script["best_id"] is None or comparison == "improved":
                script["best_id"] = candidate["id"]
            if reason:
                script["status"], script["stop_reason"] = "stopped", reason
            elif success:
                script["status"], script["stop_reason"] = "internal_pass", "passed"
            elif len(active) == 3:
                script["status"], script["stop_reason"] = "stopped", "candidate_limit"
            else:
                script["status"] = "needs_revision"
        elif action == "owner_approval":
            require(script["status"] == "internal_pass", "仅内部通过后记录 owner 批准")
            candidate = self._candidate(state, event.get("candidate"))
            require(candidate["id"] == script["best_id"] and candidate["decision"]["pass"], "批准须对应选定通过候选")
            require(event.get("hash") == candidate["hash"], "owner 批准内容与候选不符")
            require(self._file(candidate["path"])["hash"] == candidate["hash"], "先将选定候选恢复到实际源稿再记录批准")
            require(event.get("approved") is True, "未声明 owner 实际批准")
            script["owner_approval"] = {"candidate": candidate["id"], "hash": candidate["hash"],
                "message_ref": nonempty(event.get("message_ref"), "owner 实际消息引用"),
                "quote": nonempty(event.get("quote"), "owner 批准原话"), "recorded_at": now()}
            script["status"] = "owner_approved"
        elif action == "no_assets":
            self._approved(state)
            require(not any(b["kind"] == "assets" for b in state["batches"].values()), "已有必需资产批次，不能用无资产声明绕过")
            state["no_assets"] = nonempty(event.get("reason"), "无必需资产的具体依据")
        elif action == "batch":
            self._approved(state)
            identifier = nonempty(event.get("id"), "批次 ID")
            require(identifier not in state["batches"], "批次已存在；禁止重建以重置图片计数")
            kind, mode = event.get("kind"), event.get("mode")
            require(kind in ("assets", "storyboard") and mode in ("images", "prompt_only"), "批次种类或模式无效")
            require(not any(b["kind"] == kind for b in state["batches"].values()), "同阶段只有一个批次；须一次列全项目，禁止拆批重置额外池")
            require(kind != "assets" or mode == "images", "资产图需实际看图；prompt-only 分支用于分镜提示词")
            if kind == "storyboard":
                self._assets_ready(state)
            else:
                require(not any(b["kind"] == "storyboard" for b in state["batches"].values()), "分镜已开始，不能追补资产批次改变依赖")
                state["no_assets"] = None
            names = event.get("items")
            require(isinstance(names, list) and names and all(isinstance(n, str) and n.strip() for n in names)
                    and len(set(names)) == len(names), "批次须一次列全不重复的必需项目")
            existing = {name for b in state["batches"].values() if b["kind"] == kind for name in b["items"]}
            require(not (existing & set(names)), "同类项目已登记，禁止换批次重置其计数")
            state["batches"][identifier] = {"kind": kind, "mode": mode, "status": "pending",
                "extra_limit": math.ceil(len(names) / 2), "repairs_reserved": 0,
                "items": {name: {"status": "pending", "attempts": [], "stop_reason": None} for name in names}}
        elif action in ("image_reserve", "image_existing"):
            batch, item = self._item(state, event)
            require(batch["mode"] == "images", "prompt-only 不能生成或宣称视觉通过")
            require(item["status"] in ("pending", "needs_fix"), "已通过或待评审/待返回的图片不能再生成")
            require(len(item["attempts"]) < 3, "每图片最多初始加两次修复")
            require(not item.get("stop_reason"), "图片已达到停止条件")
            author = nonempty(event.get("author"), "出图/选图者")
            if action == "image_existing":
                require(not item["attempts"], "现有图只能登记为初始选图，不能绕过修复额度")
                artifact = self._file(event.get("file"), image=True)
                item["attempts"].append({"author": author, "status": "returned", "called": False,
                                        "source": "existing", "artifact": artifact, "review": None})
                item["status"] = "awaiting_visual_review"
            else:
                if item["attempts"]:
                    require(batch["repairs_reserved"] < batch["extra_limit"], "整批共享修复额度已用尽")
                    batch["repairs_reserved"] += 1
                item["attempts"].append({"author": author, "status": "reserved", "called": None,
                                        "artifact": None, "review": None})
                item["status"] = "awaiting_image"
        elif action == "image_result":
            batch, item = self._item(state, event)
            require(batch["mode"] == "images" and item["attempts"] and item["status"] == "awaiting_image", "先预约本次生成额度")
            attempt = item["attempts"][-1]
            require(type(event.get("called")) is bool, "须如实记录是否已实际发出生成调用")
            attempt["called"] = event["called"]
            attempt["reference"] = nonempty(event.get("reference"), "调用结果/未调用原因")
            attempt["status"] = "returned"
            if event["called"]:
                self._count(state, "image_generation")
            if event.get("file"):
                require(event["called"], "未调用时不能附带生成结果；使用 image_existing 登记已有图")
                attempt["artifact"] = self._file(event["file"], image=True)
                item["status"] = "awaiting_visual_review"
            else:
                item["status"] = "needs_fix"
            self._refresh(batch)
        elif action == "visual_review":
            batch, item = self._item(state, event)
            require(batch["mode"] == "images" and item["status"] == "awaiting_visual_review", "没有待评审实际图，不能判 visual_pass")
            attempt = item["attempts"][-1]
            artifact = attempt["artifact"]
            require(self._file(artifact["path"], image=True)["hash"] == artifact["hash"], "图片已变化；评审必须对应选用内容")
            require(event.get("viewed") is True, "须先实际查看图片")
            attempt["review"] = self._review(event, attempt["author"], artifact["hash"])
            item["status"] = "visual_pass" if passed(attempt["review"]) else "needs_fix"
            self._refresh(batch)
        elif action == "prompt":
            batch, item = self._item(state, event)
            require(batch["mode"] == "prompt_only" and item["status"] in ("pending", "needs_fix", "awaiting_prompt_review"),
                    "仅 prompt-only 未通过项目可登记提示词；重审时正文变化须登记新候选")
            require(len(item["attempts"]) < 3, "提示词也使用至多三候选，禁止无谓循环")
            artifact = self._file(event.get("file"))
            require(artifact["hash"] not in [a["artifact"]["hash"] for a in item["attempts"]], "提示词未变化")
            item["attempts"].append({"artifact": artifact, "author": nonempty(event.get("author"), "提示词主笔"), "review": None})
            item["status"] = "awaiting_prompt_review"
        elif action == "prompt_review":
            batch, item = self._item(state, event)
            require(batch["mode"] == "prompt_only" and item["status"] == "awaiting_prompt_review", "没有待评审提示词")
            attempt = item["attempts"][-1]
            require(self._file(attempt["artifact"]["path"])["hash"] == attempt["artifact"]["hash"], "当前提示词已变化，不能评审旧内容")
            attempt["review"] = self._review(event, attempt["author"], attempt["artifact"]["hash"])
            item["status"] = "prompt_only_pass" if passed(attempt["review"]) else "needs_fix"
            self._refresh(batch)
        elif action == "gate":
            self._approved(state)
            stage = event.get("stage")
            require(stage in ("assets", "video"), "支持 assets 和 video 阶段门禁")
            if stage == "video":
                self._assets_ready(state)
                require(any(b["kind"] == "storyboard" for b in state["batches"].values()), "尚未登记分镜批次")
                for batch in state["batches"].values():
                    require(batch["status"] in ("visual_pass", "prompt_only_pass"), "必需资产/分镜尚未通过")
                    self._verify_images(batch)
        else:
            raise GuardError(f"未知操作：{action}")
        state["revision"] += 1
        state["events"].append({"revision": state["revision"], "action": action, "at": now(),
                                "reference": event.get("reference")})
        self._save(state, revision)
        return state

    @staticmethod
    def _scope(scope, allow_empty_dimensions=False):
        require(isinstance(scope, dict), "修订必须记录实际修改范围和锁定事实检查")
        nonempty(scope.get("summary"), "修改范围")
        nonempty(scope.get("locked_facts_check"), "锁定事实检查及授权变化说明")
        require(isinstance(scope.get("changed_facts"), list) and isinstance(scope.get("downstream"), list),
                "须记录 changed_facts 与 downstream；不涉及则为空列表")
        dimensions = scope.get("dimensions")
        require(isinstance(dimensions, list) and (dimensions or allow_empty_dimensions) and len(set(dimensions)) == len(dimensions)
                and set(dimensions) <= set(DIMENSIONS), "记录需要局部复审的有效维度")

    def summary(self):
        state = self.load()
        measured = state["token_usage"]
        batches = {}
        for identifier, batch in state["batches"].items():
            compact = {key: batch[key] for key in ("kind", "mode", "status", "extra_limit", "repairs_reserved")}
            compact["items"] = {}
            for name, item in batch["items"].items():
                latest = item["attempts"][-1] if item["attempts"] else {}
                artifact = latest.get("artifact")
                review = latest.get("review")
                compact["items"][name] = {"status": item["status"], "attempt_count": len(item["attempts"]),
                    "stop_reason": item["stop_reason"],
                    "artifact": {key: artifact[key] for key in ("path", "hash")} if artifact else None,
                    "reviewer": review["reviewer"] if review else None,
                    "review_pass": passed(review) if review else None}
            batches[identifier] = compact
        return {"state_file": str(self.path), "revision": state["revision"],
                "script_status": state["script"]["status"], "best_id": state["script"]["best_id"],
                "stop_reason": state["script"]["stop_reason"], "candidate_count": len(state["script"]["candidates"]),
                "cycle": state["script"]["cycle"],
                "current_candidate_count": sum(c["cycle"] == state["script"]["cycle"] for c in state["script"]["candidates"]),
                "candidates": [{"id": c["id"], "hash": c["hash"], "required_reviews": c["required_reviews"],
                                "received_reviews": list(c["reviews"])} for c in state["script"]["candidates"]],
                "calls": state["calls"], "actual_calls_total": sum(state["calls"].values()),
                "measured_tokens": sum(x["tokens"] for x in measured.values()) if measured else None,
                "unmeasured_goals": [g["id"] for g in state["goals"] if g["id"] not in measured],
                "batches": batches}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="项目根目录；状态固定为 临时工作/流程状态.json")
    parser.add_argument("command", choices=("init", "apply", "status"))
    parser.add_argument("--writer", default="main")
    parser.add_argument("--event", help="UTF-8 JSON 文件：init 使用 locked_facts，apply 使用 action")
    arguments = parser.parse_args(argv)
    try:
        guard = Guard(arguments.project, arguments.writer)
        event = json.loads(Path(arguments.event).read_text(encoding="utf-8-sig")) if arguments.event else {}
        if arguments.command == "init":
            guard.init(event.get("locked_facts", []))
        elif arguments.command == "apply":
            guard.apply(event)
        print(json.dumps(guard.summary(), ensure_ascii=False, indent=2))
        return 0
    except (GuardError, OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"流程守卫拒绝：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
