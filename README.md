# TapNow Video Workflow

A lightweight AI video workflow skill for TapNow: screenwriting, asset organization, storyboard and video prompts, dialogue and voice direction, with Word export.

面向 TapNow 的轻量 AI 视频创作 Skill：编剧、资产整理、分镜与视频提示词、台词及声音指导，支持 Word 导出。

面向中文短视频项目的轻量 Codex 技能：从想法或现有剧本开始，整理人物、环境与道具参考，再按固定镜号交付分镜图提示词、视频提示词、对应台词、音色和独立音效。最终图片、声音与视频由使用者在 TapNow 等实际制作入口生成、试听和选用。

技能默认交付三个独立文件：`剧本.docx`、`分镜图提示词.docx`、`视频提示词与台词.docx`，并在项目的 `归档/文档源稿/` 保留对应 Markdown 源稿。图片和视频默认无字幕。

## 能做什么

- 讨论点子、诊断或修改剧本，形成可拍的动作和对白。
- 规划人物、声音、环境和关键道具；区分已确认、待生成、待查看和需修正。
- 按镜交付图片 prompt、视频 prompt、台词、固定音色、时机和音效 prompt。
- 从约定格式的 Markdown 导出 Word，并对项目命名、正文、链接和配套内容做自动检查。
- 保持项目文件、临时工作和归档分开，避免在技能目录产生项目文件或缓存。

## 能力边界

基础文字工作只要求宿主能读取 `SKILL.md`。讨论剧本、编写 prompt 和运行纯文本检查不要求 TapNow 账户、API key、图像模型或第三方 Python 包。

Word 导出和随附检查脚本是可选扩展，脚本最低要求 Python 3.10，并需要 `python-docx`、`Pillow` 才能处理 Word。基础创作不需要 Python。图片生成通过宿主提供的 imagegen 能力完成，它不是 pip 依赖，也不默认绑定任何供应商或模型。

已内置 [screenwriting-skills 的轻量编剧集成](references/编剧集成.md)：前提与主题、结构与节奏、人物与动机、场景与衔接、对白与潜台词、改编与表达。它提供可直接执行的方法和阶段入口，不只是可选技能名单；默认每次选相关的1—2个模块，修改直接进入现有文档。无需再安装整套 sw-*；本机已有原技能时，可按问题深入读取。此适配不等于携带上游全套知识库，未复制引文参考库或独立项目调度。

集成不增加 Python 包、API、项目管理文件或用户填表步骤。仍按需交付原来的三类 Word，不建 story-bible、人物研究册、节拍卡、额外审批或另一份项目状态。来源与许可见 [SOURCE](third_party/screenwriting-skills/SOURCE.md)。

TapNow 账户只在实际生成、试听、选用和连接节点时需要。本技能不会假装已连接节点、已生成内容或已完成平台验收，也不需要 TapNow API 或插件才能准备制作文本。

自动检查不能代替视觉验收。检测到 Word、WPS、LibreOffice 或 Poppler 的可执行文件，只表示存在候选工具；正式 Word 仍要实际导出为页面、逐页查看图片、分页、截断、溢出和链接。宿主可用 documents 渲染器时可直接使用；否则可采用 Word/WPS/LibreOffice 导出 PDF，再用 Poppler 转成页面图。

## 安装

根据 [OpenAI 的 Codex 技能文档](https://developers.openai.com/codex/skills/)，当前用户级本地技能目录是 `$HOME/.agents/skills`。从本 GitHub 仓库选择 **Code → Download ZIP**，解压后保证目录结构如下：

```text
$HOME/.agents/skills/video-workflow/
├── SKILL.md
├── README.md
├── LICENSE
├── THIRD_PARTY.md
├── requirements-word.txt
├── assets/
├── examples/
├── references/
├── third_party/              # 编剧集成来源与原许可
├── scripts/
└── tests/                    # 维护者验证用
```

不要把 ZIP 外层自动生成的仓库名再嵌套一层；`SKILL.md` 必须直接位于 `video-workflow/` 内。Codex 通常会自动发现技能；若没有出现，请重启 Codex。

也可先克隆仓库，再在仓库根目录使用下方对应系统的命令安装。目标目录必须尚不存在，以免覆盖已有定制内容。

```bash
git clone https://github.com/nobuna-ch/tapnow-video-workflow.git
cd tapnow-video-workflow
```

PowerShell：

```powershell
$target = Join-Path $HOME ".agents\skills\video-workflow"
if (Test-Path -LiteralPath $target) { throw "目标已存在：$target" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
New-Item -ItemType Directory -Path $target | Out-Null
$items = @("SKILL.md", "README.md", "LICENSE", "THIRD_PARTY.md", "requirements-word.txt", ".gitignore", "assets", "examples", "references", "third_party", "scripts", "tests")
foreach ($item in $items) {
    Copy-Item -Recurse -LiteralPath (Join-Path (Get-Location) $item) -Destination $target
}
```

macOS / Linux：

```bash
target="$HOME/.agents/skills/video-workflow"
test ! -e "$target" || { echo "目标已存在：$target" >&2; exit 1; }
mkdir -p "$target"
for item in SKILL.md README.md LICENSE THIRD_PARTY.md requirements-word.txt .gitignore assets examples references third_party scripts tests; do
  cp -R "$item" "$target/"
done
```

以上仅复制技能文件，不复制 Git 历史或本地测试产生的临时工作目录。

安装完成后先做只读自检：

```bash
python -B -X utf8 "$HOME/.agents/skills/video-workflow/scripts/环境自检.py" --要求 text
```

Windows PowerShell 可写为：

```powershell
python -B -X utf8 "$HOME\.agents\skills\video-workflow\scripts\环境自检.py" --要求 text
```

## 环境自检与退出码

自检脚本只使用 Python 标准库，不联网、不自动安装软件、不启动 Office GUI，也不创建缓存或项目文件。

```bash
python -B -X utf8 scripts/环境自检.py --要求 text
python -B -X utf8 scripts/环境自检.py --要求 screenwriting
python -B -X utf8 scripts/环境自检.py --要求 word --格式 json
python -B -X utf8 scripts/环境自检.py --要求 render
```

- `--要求 text`：检查随附纯文本工具所需的标准库 Python。Word 扩展缺失不会导致它失败；基础创作本身无需运行此脚本。
- `--要求 screenwriting`：检查内置六模块及来源/许可材料完整；不要求旁边安装 sw-*，也不联网。通过只代表可读取集成资源，不是创作质量评分。
- `--要求 word`：要求 `python-docx` 与 `Pillow` 在当前 Python 中可导入。
- `--要求 render`：只读探测无法证明一次真实渲染已通过，因此返回 `not_verified`，直到在实际项目中完成导出与逐页检查。
- 退出码 `0` 表示所要求的能力可用，`2` 表示缺失，`3` 表示尚未验证。参数错误由 Python `argparse` 返回 `2`。

若宿主已有满足要求的 Python 环境，直接使用该环境，不要重复安装。需要自行启用 Word 扩展时，把虚拟环境和 pip 缓存放在用户项目的 `临时工作/`，不要写进 skill 目录，也不要修改系统 Python 或现有共享环境。

macOS / Linux：

```bash
project_dir="/absolute/path/to/your/project"
skill_dir="$HOME/.agents/skills/video-workflow"
mkdir -p "$project_dir/临时工作/pip-cache"
python3 -m venv "$project_dir/临时工作/.venv"
PIP_CACHE_DIR="$project_dir/临时工作/pip-cache" \
  "$project_dir/临时工作/.venv/bin/python" -m pip install \
  -r "$skill_dir/requirements-word.txt"
```

Windows PowerShell：

```powershell
$projectDir = [System.IO.Path]::GetFullPath("<项目目录>")
$skillDir = Join-Path $HOME ".agents\skills\video-workflow"
$venv = Join-Path $projectDir "临时工作\.venv"
$env:PIP_CACHE_DIR = Join-Path $projectDir "临时工作\pip-cache"
New-Item -ItemType Directory -Force -Path $env:PIP_CACHE_DIR | Out-Null
python -m venv $venv
& (Join-Path $venv "Scripts\python.exe") -m pip install `
  -r (Join-Path $skillDir "requirements-word.txt")
```

本项目验证过 `python-docx 1.2.0` 与 `Pillow 12.3.0`；`requirements-word.txt` 使用同一主版本范围。

## 最小使用流程

先把 `examples/最小示例/` 完整复制到你选择的项目目录，再在复制后的项目里运行工具。不要直接在技能目录内导出 Word 或保存项目素材。

```bash
python -B -X utf8 "<技能目录>/scripts/导出说明书.py" "<项目目录>/归档/文档源稿/剧本.md" --项目目录 "<项目目录>"
python -B -X utf8 "<技能目录>/scripts/导出说明书.py" "<项目目录>/归档/文档源稿/分镜图提示词.md" --项目目录 "<项目目录>"
python -B -X utf8 "<技能目录>/scripts/导出说明书.py" "<项目目录>/归档/文档源稿/视频提示词与台词.md" --项目目录 "<项目目录>"
python -B -X utf8 "<技能目录>/scripts/检查项目.py" "<项目目录>" --模式 word
```

只检查 Markdown 文本而不要求 Word 扩展：

```bash
python -B -X utf8 "<技能目录>/scripts/检查项目.py" "<项目目录>" --模式 text
```

需要先看草稿时，在导出命令后加 `--草稿`；预览会进入项目的 `临时工作/导出预览/`。正式当前稿固定使用三个标准文件名。`--输出` 只接受项目内 `临时工作/**` 或 `归档/临时工作/**` 下的同名目标；历史文件的明确修复另用 `--修复归档`。完整规则以 `SKILL.md` 和命令自身的 `--help` 为准。

## 项目与隐私

维护者可运行两组回归；不是用户日常制作步骤。执行检查测试需要 Word 扩展，测试工作目录必须放在项目内。文件名为中文，请直接运行以下测试入口，不用默认的 unittest discover（它可能报告运行了零项）。PowerShell 示例：

```powershell
$skillRoot = Join-Path $HOME ".agents\skills\video-workflow"
$testRoot = "<项目目录>\临时工作\技能测试"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$env:VIDEO_WORKFLOW_TEST_ROOT = $testRoot
$env:TEMP = $testRoot
$env:TMP = $testRoot
python -B -X utf8 "$skillRoot\tests\环境自检测试.py"
python -B -X utf8 "$skillRoot\tests\执行检查.py" --工作目录 "$testRoot\执行检查"
```

macOS/Linux 可设置同名 VIDEO_WORKFLOW_TEST_ROOT、TMPDIR 后运行相同 Python 入口（路径分隔符用 `/`）。工作目录只用于本轮测试，不能指定为包含用户素材的目录。

示例只包含虚构的最小内容。请勿把私有项目素材、实物照片、品牌视频、账户信息或 API key 提交到本仓库。技能执行产生的 Word、PDF、页面图、音视频和日志应留在用户选择的项目目录，不应写回安装目录。

## 许可证

仓库贡献者原创文件采用 [MIT License](LICENSE)。第三方软件与用户内容的许可边界见 [THIRD_PARTY.md](THIRD_PARTY.md)。本许可证不替使用者取得人物照片、品牌素材、字体、音乐、视频、其他技能或在线服务的使用授权。
