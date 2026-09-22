#!/usr/bin/env python3
"""视频工作流 Markdown/TXT 的基础内容检查；只使用 Python 标准库。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


SHOT = re.compile(r"^##\s+镜头\s*([0-9]+[A-Za-z]?)\b([^\n]*)", re.M | re.I)
TIME = re.compile(r"全片\s*约?\s*([0-9]+(?:\.\d+)?)\s*[—–-]\s*约?\s*([0-9]+(?:\.\d+)?)\s*秒")
DURATION = re.compile(r"(?:成片时长|新增时长|原片时长)\s*[:：]?\s*约?\s*([0-9]+(?:\.\d+)?)\s*秒")
FIELD_START = re.compile(
    r"^(?:地点|主要环境锚点|连接素材|画面输入|画面来源|起始状态|动作记录|"
    r"说话人|台词文本|台词|固定音色|本句情绪|情绪与语速|情绪|语速|发言时机|"
    r"音效(?:\s*prompt)?|建议素材时长|素材时长|出现时机|衔接|合成)\s*[:：]",
    re.I,
)


@dataclass(frozen=True)
class Shot:
    number: str
    title: str
    body: str
    start: float | None
    end: float | None


def read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def shots(text: str) -> list[Shot]:
    matches = list(SHOT.finditer(text))
    result: list[Shot] = []
    for index, match in enumerate(matches):
        body = text[match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        timing = TIME.search(body)
        result.append(Shot(match.group(1).upper(), match.group(2).strip(), body,
                           float(timing.group(1)) if timing else None,
                           float(timing.group(2)) if timing else None))
    return result


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.I | re.M | re.S) is not None


def _clean_value(value: str) -> str:
    return re.sub(r"^[`*_# \t]+|[`*_# \t]+$", "", value.strip())


def _field_value(text: str, label: str) -> str:
    """只读同一行字段值，避免空标签吞掉下一行字段。"""
    match = re.search(r"(?:^|[。；;][ \t]*)(?:\*\*)?" + label + r"(?:\*\*)?[ \t]*[:：][ \t]*([^。；;\r\n]*)", text, re.I | re.M)
    return _clean_value(match.group(1)) if match else ""


def _inline_field_value(text: str, label: str) -> str:
    """读取同一行可与其他字段并列的短字段。"""
    matches = list(re.finditer(label + r"[ \t]*[:：][ \t]*([^\r\n；;。]*)", text, re.I))
    for match in reversed(matches):
        value = _clean_value(match.group(1))
        if value:
            return value
    return ""


def _section_bodies(text: str, label: str) -> list[str]:
    """读取一个或多个 prompt 标题后的正文；遇到下一字段或标题立即停止。"""
    matches = list(re.finditer(r"^(?:#{1,4}[ \t]+)?" + label + r"[ \t]*[:：]?[ \t]*([^\r\n]*)$", text, re.I | re.M))
    bodies: list[str] = []
    for match in matches:
        inline = _clean_value(match.group(1))
        if inline:
            bodies.append(inline)
            continue
        collected: list[str] = []
        for raw in text[match.end():].splitlines():
            line = raw.strip()
            if not line or re.fullmatch(r"`{3,}|~{3,}", line):
                continue
            if line.startswith("#") or FIELD_START.match(line) or re.match(r"^\*\*[^*]+\*\*$", line):
                break
            collected.append(line.strip("`"))
        bodies.append("\n".join(collected).strip())
    return bodies


def _section_body(text: str, label: str) -> str:
    bodies = _section_bodies(text, label)
    return bodies[0] if bodies else ""


def _section_has_body(text: str, label: str) -> bool:
    return bool(_section_body(text, label))


def _named_section_body(text: str, label: str) -> str:
    match = re.search(r"^(?:【[^\r\n】]*" + label + r"[^\r\n】]*】|" + label + r"[^\r\n:：]*)[ \t]*$", text, re.I | re.M)
    if not match:
        return ""
    collected: list[str] = []
    for raw in text[match.end():].splitlines():
        line = raw.strip()
        if not line:
            if collected:
                break
            continue
        if line.startswith(("【", "#")) or FIELD_START.match(line):
            break
        collected.append(line.strip("`"))
    return "\n".join(collected).strip()


def _check_declared_duration(item: Shot, prefix: str, problems: list[str]) -> None:
    if item.start is None or item.end is None:
        return
    match = DURATION.search(item.body)
    if match and abs(float(match.group(1)) - (item.end - item.start)) > 0.011:
        problems.append(f"{prefix}：声明的成片时长与全片时间区间不一致")


def check_timeline(items: list[Shot], label: str) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    manual: list[str] = []
    timed = [item for item in items if item.start is not None and item.end is not None]
    for item in timed:
        if item.end <= item.start:
            problems.append(f"{label}镜头{item.number}：全片时间区间无效")
    for previous, current in zip(timed, timed[1:]):
        if current.start is not None and previous.end is not None:
            if current.start > previous.end + 0.01:
                problems.append(f"{label}：镜头{previous.number}到{current.number}之间有时间空档")
            elif current.start < previous.end - 0.01:
                manual.append(f"{label}：镜头{previous.number}与{current.number}时间重叠，请确认是否为有意的声画跨切或合成")
    return problems, manual


def check_storyboard(text: str) -> dict:
    problems: list[str] = []
    manual: list[str] = []
    items = shots(text)
    if not items:
        return {"问题": ["分镜图提示词：未识别到镜头标题"], "待人工": [] , "镜头": []}
    seen: set[str] = set()
    for item in items:
        prefix = f"分镜镜头{item.number}"
        if item.number in seen:
            problems.append(f"{prefix}：镜号重复")
        seen.add(item.number)
        if item.start is None:
            problems.append(f"{prefix}：缺少全片时间区间")
        _check_declared_duration(item, prefix, problems)
        composite = _has(item.body, r"分屏|两侧|左右.{0,20}合成")
        exceptional = composite or _has(item.body, r"(?:复用|沿用|合成|现成|末帧|尾片|独立空镜).{0,30}(?:来源|素材|画面|视频|片段|镜头)|(?:来源|素材).{0,30}(?:复用|合成|现成|末帧|尾片)")
        anchor_value = _field_value(item.body, r"主要环境锚点")
        anchor_ids = set(re.findall(r"[\w\u3400-\u9fff]+_E\d+[A-Za-z]?", anchor_value))
        if not anchor_value and not exceptional:
            problems.append(f"{prefix}：缺少主要环境锚点或明确的复用/合成来源")
        elif len(anchor_ids) > 1:
            problems.append(f"{prefix}：普通镜头的主要环境锚点包含多个 E 编号")
        if composite and not anchor_value:
            sides = list(re.finditer(r"^###\s*(左半屏|右半屏|左侧|右侧)[^\n]*$", item.body, re.M))
            for index, side in enumerate(sides):
                segment = item.body[side.end():sides[index + 1].start() if index + 1 < len(sides) else len(item.body)]
                ids = set(re.findall(r"[\w\u3400-\u9fff]+_E\d+[A-Za-z]?", segment))
                if len(ids) != 1:
                    problems.append(f"{prefix}：{side.group(1)}应明确且只使用一个 E 编号环境锚点")
        if not _section_has_body(item.body, r"分镜图\s*prompt") and not _has(item.body, r"(?:无需(?:新)?(?:分镜图)?生成|无需新分镜图|现成尾片|复用现成)"):
            problems.append(f"{prefix}：缺少分镜图 prompt")
        if not _field_value(item.body, r"连接素材") and not exceptional:
            problems.append(f"{prefix}：缺少连接素材或明确来源")
        if not _field_value(item.body, r"起始状态"):
            problems.append(f"{prefix}：缺少起始状态")
        if not (_field_value(item.body, r"衔接") or _field_value(item.body, r"合成")):
            problems.append(f"{prefix}：缺少衔接说明")
    p, m = check_timeline(items, "分镜")
    problems.extend(p); manual.extend(m)
    manual.append("分镜图的主体身份、空间、数量、穿模、画面一致性与实际节点绑定仍需人工看图确认")
    return {"问题": list(dict.fromkeys(problems)), "待人工": list(dict.fromkeys(manual)), "镜头": items}


def _dialogue_groups(body: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^\*\*\s*([^*\n]+?)台词\s*\*\*\s*$", body, re.M))
    groups = []
    for index, match in enumerate(matches):
        segment = body[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(body)]
        groups.append((match.group(1).strip(), segment))
    # 兼容模板的“说话人：…。台词文本：……”格式，保留后续声音字段。
    template = list(re.finditer(r"(?:^|\n)说话人\s*[:：]\s*([^。\n]+)", body))
    for index, match in enumerate(template):
        end = template[index + 1].start() if index + 1 < len(template) else len(body)
        segment = body[match.end():end]
        groups.append((match.group(1).strip(), segment))
    return groups


def _dialogue_text(segment: str) -> str:
    template_text = re.search(r"台词文本\s*[:：][ \t]*(.+?)(?=\n(?:固定音色|本句情绪|情绪|语速|发言时机)\s*[:：]|\Z)", segment, re.S)
    if template_text:
        return re.sub(r"^[`\s]+|[`\s]+$", "", template_text.group(1))
    return next((line.strip(" `*\t") for line in segment.splitlines()
                 if line.strip() and not re.match(r"^(固定音色|本句情绪|情绪|语速|发言时机)\s*[:：]", line)), "")


def _plain_compare(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", text).lower()


def check_video(text: str) -> dict:
    problems: list[str] = []
    manual: list[str] = []
    items = shots(text)
    if not items:
        return {"问题": ["视频提示词与台词：未识别到镜头标题"], "待人工": [], "镜头": []}
    seen: set[str] = set()
    for item in items:
        prefix = f"视频镜头{item.number}"
        if item.number in seen:
            problems.append(f"{prefix}：镜号重复")
        seen.add(item.number)
        if item.start is None:
            problems.append(f"{prefix}：缺少全片时间区间")
        _check_declared_duration(item, prefix, problems)
        no_generation = _has(item.body, r"无需(?:新)?(?:视频)?生成|现成(?:品牌)?(?:尾片|视频)|直接(?:延续|复用|使用).{0,30}(?:视频|片段|末帧)")
        reused_input = _has(item.body, r"(?:画面来源|直接延续|末帧|复用).{0,50}(?:视频|分镜|画面|素材)")
        if not _field_value(item.body, r"画面输入") and not (no_generation or reused_input):
            problems.append(f"{prefix}：缺少画面输入或明确无需生成")
        video_prompt = "\n".join(_section_bodies(item.body, r"(?:[^#\n]+[ \t]+)?视频\s*prompt(?:\s*与对应台词)?"))
        if not video_prompt and not no_generation:
            problems.append(f"{prefix}：缺少视频 prompt")
        if not no_generation and not _field_value(item.body, r"起始状态"):
            problems.append(f"{prefix}：缺少起始状态")
        if not no_generation and not _field_value(item.body, r"动作记录"):
            problems.append(f"{prefix}：缺少起止动作记录")
        if not (_field_value(item.body, r"衔接") or _field_value(item.body, r"合成")):
            problems.append(f"{prefix}：缺少衔接说明")

        groups = _dialogue_groups(item.body)
        no_dialogue = _has(item.body, r"台词\s*[:：]\s*无\b|本镜无台词|无对白")
        reused_dialogue = _has(item.body, r"跨镜对白\s*[:：].{0,80}(?:复用|沿用|延续|尾段|最后)")
        if not groups and not no_dialogue and not reused_dialogue and not no_generation:
            problems.append(f"{prefix}：缺少台词无/跨镜复用声明或完整台词组")
        for speaker, segment in groups:
            group = f"{prefix} {speaker}台词"
            first = _dialogue_text(segment)
            if not first:
                problems.append(f"{group}：缺少纯台词文本")
            elif re.match(r"^(?:台词|表演|备注|情绪|音色)\s*[:：]", first):
                manual.append(f"{group}：首行可能混入标签，请人工确认复制内容是否为纯台词")
            voice = _field_value(segment, r"固定音色")
            if not voice:
                problems.append(f"{group}：缺少固定音色")
            elif _has(voice, r"^(?:同上|沿用上[文一]|与上(?:文|一条)?相同)(?:[。.]|$)"):
                problems.append(f"{group}：固定音色不能写“同上”或要求跳转查找")
            if not _inline_field_value(segment, r"(?:本句)?情绪(?:与语速)?"):
                problems.append(f"{group}：缺少情绪")
            speed = _inline_field_value(segment, r"语速")
            if not speed or not _has(speed, r"字/秒|快|慢|自然|秒"):
                problems.append(f"{group}：缺少语速")
            if not _field_value(segment, r"发言时机"):
                problems.append(f"{group}：缺少发言时机")
            if first and video_prompt:
                spoken = _plain_compare(first)
                prompt_plain = _plain_compare(video_prompt)
                offscreen = _has(item.body, re.escape(speaker) + r".{0,24}画外|画外.{0,24}" + re.escape(speaker))
                cross_exception = reused_dialogue or _has(item.body, r"跨镜|尾段.{0,20}(?:延续|复用)")
                if spoken and spoken not in prompt_plain and not (offscreen or cross_exception):
                    problems.append(f"{group}：可见说话人的视频 prompt 未包含实际台词")

        effect = re.search(r"(?:^|[。；;][ \t]*)音效(?:\s*prompt)?[ \t]*[:：][ \t]*([^\r\n]*)$", item.body, re.M | re.I)
        if not effect or not _clean_value(effect.group(1)):
            if not (no_generation and _has(item.body, r"(?:声音|音轨).{0,80}(?:延续|保留|无|不新增)")):
                problems.append(f"{prefix}：缺少音效无/复用或音效 prompt")
        else:
            value = _clean_value(effect.group(1))
            exempt = _has(value, r"^(?:无|无新增)|沿用|复用|连续|无需")
            if not exempt:
                prompt_label = re.search(r"^音效\s*prompt[ \t]*[:：]", item.body, re.I | re.M)
                if prompt_label and not _field_value(item.body, r"音效\s*prompt"):
                    problems.append(f"{prefix}：独立音效 prompt 未填写")
                elif not prompt_label and len(_plain_compare(value)) <= 12:
                    problems.append(f"{prefix}：独立音效缺少可生成的 prompt 描述")
                duration = _field_value(item.body, r"(?:建议)?素材时长")
                timing = _field_value(item.body, r"出现时机")
                if not duration and not _has(value, r"(?:素材|时长|建议).{0,12}\d+(?:\.\d+)?\s*秒|(?<!前)(?<!内)约\s*\d+(?:\.\d+)?\s*秒"):
                    problems.append(f"{prefix}：独立音效缺少素材时长")
                if not timing and not _has(value, r"时|对齐|镜初|镜末|全程|随后|对应|动作|出现|开始|结束"):
                    problems.append(f"{prefix}：独立音效缺少出现时机")

        for ref in re.findall(r"@?分镜[_\s-]*([0-9]+[A-Za-z]?)", item.body, re.I):
            same_family = ref.upper() == item.number or (item.number.isdigit() and ref.upper().startswith(item.number))
            explained = _has(item.body, r"(?:末帧|复用|合并|连续).{0,50}(?:镜|分镜)[_\s-]*" + re.escape(re.sub(r"[A-Za-z]$", "", ref)),)
            if not same_family and not explained:
                problems.append(f"{prefix}：引用分镜_{ref.upper()}，未说明跨镜复用/合并")
    p, m = check_timeline(items, "视频")
    problems.extend(p); manual.extend(m)
    manual.append("机器检查不能证明口型同步、表演、画面连续性、声音试听效果或平台节点已正确连接")
    return {"问题": list(dict.fromkeys(problems)), "待人工": list(dict.fromkeys(manual)), "镜头": items}


def check_script(text: str) -> dict:
    """检查剧本的最小制作字段；兼容旧稿将字段写在开头自然段。"""
    problems: list[str] = []
    manual: list[str] = []
    intro = text.split("\n## ", 1)[0]
    duration = _field_value(text, r"目标时长")
    if not duration and not _has(intro, r"(?:剧情|全片|总时长|总)\s*约?\s*\d+(?:\.\d+)?\s*秒"):
        problems.append("剧本：缺少目标时长字段或可识别时长")
    aspect = _field_value(text, r"画幅")
    if not aspect and not _has(intro, r"画幅\s*[:：]?\s*\d+\s*[∶:]\s*\d+"):
        problems.append("剧本：缺少画幅字段或可识别比例")
    style = _field_value(text, r"视觉风格")
    if not style and not _has(intro, r"写实|纪实|动画|插画|水彩|电影感|极简|复古|未来感"):
        problems.append("剧本：缺少视觉风格字段或可识别风格")
    story = (_field_value(text, r"一句话故事") or _field_value(text, r"表达目标")
             or _field_value(text, r"故事梗概"))
    if not story:
        problems.append("剧本：缺少一句话故事/表达目标字段")

    scene_matches = list(re.finditer(r"^#{2,4}\s+([^\n]+)$", text, re.M))
    scene_bodies: list[str] = []
    for index, match in enumerate(scene_matches):
        title = match.group(1).strip()
        if title.startswith(("一 ", "二 ", "三 ", "附录")):
            continue
        end = scene_matches[index + 1].start() if index + 1 < len(scene_matches) else len(text)
        body = text[match.end():end].strip()
        if not body:
            problems.append(f"剧本段落“{title}”：缺少动作/对白正文")
        else:
            scene_bodies.append(body)
    joined = "\n".join(scene_bodies) if scene_bodies else text
    has_action = _has(joined, r"动作\s*[:：]\s*\S|走|坐|站|拿|放|抬|转头|打开|关上|看向|停住|切到|淡入|淡出|吃|笑")
    if not has_action:
        problems.append("剧本：缺少可见动作内容")
    has_dialogue = _has(joined, r"[“\"]\s*[^”\"\n]+[”\"]|(?:对白|台词)\s*[:：][ \t]*(?:无|\S+)|^[^#\n：:]{1,12}[：:][ \t]*\S+")
    if not has_dialogue:
        problems.append("剧本：缺少对白内容或明确的“对白：无”")
    manual.append("剧本动作是否可拍、对白时长是否自然仍需结合实际表演人工判断")
    return {"问题": list(dict.fromkeys(problems)), "待人工": manual}


def check_people_notes(root: Path) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    manual: list[str] = []
    folder = root / "制作素材" / "人物"
    if not folder.is_dir():
        return problems, manual
    for image in folder.rglob("*"):
        if not image.is_file() or image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        notes = [image.with_suffix(ext) for ext in (".txt", ".md") if image.with_suffix(ext).is_file()]
        if not notes:
            problems.append(f"人物素材 {image.relative_to(root)}：缺少同名 TXT/Markdown 说明")
            continue
        if not image.with_suffix(".txt").is_file() and image.with_suffix(".md").is_file():
            manual.append(
                f"人物说明 {image.with_suffix('.md').relative_to(root)}：仅有 Markdown；请确认这是 owner 指定或既有兼容格式，新建人物说明默认使用 TXT"
            )
        text = read_utf8(notes[0])
        checks = {
            "参考图片": _field_value(text, r"参考图片"),
            "人物名称": _field_value(text, r"(?:人物|主体)名称"),
            "主体描述": _named_section_body(text, r"主体描述"),
            "外形复用提示词": _named_section_body(text, r"(?:(?:外形|图片)复用提示词|重做参考图)"),
            "试听台词": _named_section_body(text, r"(?:试听台词|试听用原句)"),
            "表演说明": _named_section_body(text, r"(?:表演说明|试听台词与表演)"),
            "声音状态": _field_value(text, r"声音状态"),
        }
        for label, value in checks.items():
            if not value:
                problems.append(f"人物说明 {notes[0].relative_to(root)}：缺少或未填写{label}")
        voice = _named_section_body(text, r"固定音色")
        if not voice:
            if not _has(text, r"(?:无台词|不说话|无说话).{0,30}(?:无需|不需要|理由)"):
                problems.append(f"人物说明 {notes[0].relative_to(root)}：缺少或未填写固定音色，且未说明无说话角色的理由")
        reference = _field_value(text, r"参考图片")
        if reference and Path(reference).name != image.name:
            problems.append(f"人物说明 {notes[0].relative_to(root)}：参考图片与同名图片不一致")
    return problems, manual


def check_current_content(root: Path) -> dict:
    source = root / "归档" / "文档源稿"
    problems: list[str] = []
    manual: list[str] = []
    script_path = source / "剧本.md"
    image_path, video_path = source / "分镜图提示词.md", source / "视频提示词与台词.md"
    script_result = check_script(read_utf8(script_path)) if script_path.is_file() else {"问题": [], "待人工": []}
    image_result = check_storyboard(read_utf8(image_path)) if image_path.is_file() else {"问题": [], "待人工": [], "镜头": []}
    video_result = check_video(read_utf8(video_path)) if video_path.is_file() else {"问题": [], "待人工": [], "镜头": []}
    problems.extend(script_result["问题"]); problems.extend(image_result["问题"]); problems.extend(video_result["问题"])
    manual.extend(script_result["待人工"]); manual.extend(image_result["待人工"]); manual.extend(video_result["待人工"])
    if image_result["镜头"] and video_result["镜头"]:
        images = {x.number: x for x in image_result["镜头"]}
        videos = {x.number: x for x in video_result["镜头"]}
        image_order = [x.number for x in image_result["镜头"]]
        video_order = [x.number for x in video_result["镜头"]]
        if set(image_order) != set(video_order):
            problems.append("分镜图与视频文档的镜号集合不一致")
        elif image_order != video_order:
            problems.append("分镜图与视频文档的镜号顺序不一致")
        for number in images.keys() & videos.keys():
            a, b = images[number], videos[number]
            if (a.start, a.end) != (b.start, b.end):
                problems.append(f"镜头{number}：分镜图与视频的全片时间不一致")
    p, m = check_people_notes(root)
    problems.extend(p); manual.extend(m)
    return {"问题": list(dict.fromkeys(problems)), "待人工": list(dict.fromkeys(manual))}


def check_source_content(path: Path, *, formal: bool) -> dict:
    text = read_utf8(path)
    if path.name == "分镜图提示词.md":
        result = check_storyboard(text)
    elif path.name == "视频提示词与台词.md":
        result = check_video(text)
    elif path.name == "剧本.md":
        result = check_script(text)
    else:
        result = {"问题": [], "待人工": []}
    return {"问题": result["问题"] if formal else [],
            "待补": [] if formal else result["问题"],
            "待人工": result["待人工"]}
