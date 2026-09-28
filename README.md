# TapNow Video Workflow

面向中文视频项目的轻量创作与自动评审 skill。把想法、大纲或参考片变成可审阅剧本，组织并检查资产、分镜，最后交付能直接复制的视频提示词。默认用于剧情与产品结合的品牌短片，也支持纯产品、氛围片与局部改稿。

当前文字交付按阶段采用 `剧本.docx`、`资产设定.docx`、`分镜.docx`、`视频提示词.docx`，源稿在项目 `归档/文档源稿/`。图片仍为独立图像文件。音效与对白包含在每个视频提示词正文末尾，随视频生成。

## 执行能力

- [主入口](SKILL.md)：阶段推进、owner gate、文件边界和提示词约定。
- [编剧集成](references/编剧集成.md)：六个短片编剧模块的轻量适配，不需要安装另一套知识库。
- [自动评审](references/自动评审.md)：主笔与三位评审、最多三份候选、局部变更、停止条件，以及流程守卫的实际用法。
- [制作规则](references/制作规则.md)：资产与分镜独立看图、风格基准、防漂移、出图与 prompt-only 分支。
- [执行与验收](references/执行与验收.md)：DOCX 导出、历史保护、检查和页面验证。

宿主提供 Goal、子代理和图像生成工具；本包不实现后台运行器，不安装重型代理框架、GPU 审美模型、视频模型适配或 TapNow 服务。Goal 仅在 owner 明确要求且宿主支持时使用；它不能越过 owner gate 或重置额度。

基础讨论可只读规则。可执行守卫和文本检查使用 Python 3.10+ 标准库；Word 导出使用 `python-docx` 与 `Pillow`。自动评审需要真实独立代理，视觉 pass 需要实际看图；缺少相应能力就注明未执行，不能用主笔自评冒充。

## 有界评审

剧本默认一位主笔和三个评审维度，初稿加至多两次实质返修。每位评审最多三条有证据的问题，硬约束不靠主观评分抵消。通过即停止；失败到限交付最佳候选及原因。小改动只复审受影响部分，不自动颠覆结构。

`流程守卫.py` 把候选、评审、owner 批准和图像调用额度保存在项目 `临时工作/流程状态.json`。只有主代理写入；重新运行或新 Goal 沿用原状态。守卫可以拒绝越阶段、旧候选评审和超额尝试，不能证明人类批准的真实性、语义判断或审美质量；这些需要宿主根据实际会话和工具结果负责。详见自动评审文档及脚本 `--help`。

内部剧本 pass 后交 owner 批准再生成资产。图像每项最多一次初次生成和两次返工，且全批额外调用不超过 `ceil(N/2)`。prompt-only 通过表示提示词可执行，不表示图片已验收；它可继续进入视频提示词，不要求先回传图片。

## 视频节点的交付约定

设置区列模式、输入素材和建议秒数。首尾帧通过软件选图，正文不机械加入 @首尾帧；多素材参考模式才按实际需要 @对应素材及用途。

每个节点只含一个完整复制块：动作与镜头描述，然后是音效、对白。必要音色、情绪和说话时机也在这一块内。没有独立配音/音效生成或后期替换音轨的默认流程。平台能力按实际入口核实，不预设 Wan 或某个版本。

## 安装与依赖

把本目录安装到宿主的技能目录，确保 `video-workflow/SKILL.md` 直接可读。已有安装先保留定制内容，不盲目覆盖。目录包括入口、规则、模板、示例、标准库脚本与维护者测试；运行产物都留在项目中。

从 [GitHub 仓库](https://github.com/nobuna-ch/tapnow-video-workflow) 下载 ZIP，或克隆源码：

```text
git clone https://github.com/nobuna-ch/tapnow-video-workflow.git
cd tapnow-video-workflow
```

Codex 沿用本机已生效的技能目录，例如 `$HOME/.codex/skills/video-workflow/`；若已有安装在 `$HOME/.agents/skills/` 或自定义 `CODEX_HOME` 下，继续使用原位置，只保留一个 `video-workflow`。解压后若出现两层同名目录，取直接含 `SKILL.md` 的内层，不能把整个外层套进技能目录。

首次安装可在源码根目录用 PowerShell 复制。替换 `<技能目录>` 为上述实际目标；已有安装则先核对、备份，再同步文件，不创建带“新版”后缀的第二个技能。

```powershell
$target = [System.IO.Path]::GetFullPath('<技能目录>')
if (Test-Path -LiteralPath $target) { throw "目标已存在，请先核对并备份：$target" }
New-Item -ItemType Directory -Force -Path $target | Out-Null
$items = @('SKILL.md', 'README.md', 'LICENSE', 'THIRD_PARTY.md', 'requirements-word.txt', '.gitignore', 'assets', 'examples', 'references', 'third_party', 'scripts', 'tests')
foreach ($item in $items) {
    Copy-Item -Recurse -LiteralPath (Join-Path (Get-Location) $item) -Destination $target
}
```

其他系统同样只复制以上文件和目录，不复制 `.git`、`临时工作` 或解压外层。源码仓库与视频项目分开放置；后续修改、测试、Git 提交与推送在源码仓库进行，通过后同步安装副本。导入另一台设备的文件时保留当前仓库的 `.git`，移除新版已替代的旧示例，避免混成两个入口。升级技能不会自动迁移视频项目。

有工作区依赖查询工具时优先查询现成 Python；不修改系统 Python，不重复安装已有库。不需要第三方包也能运行下面两个只读检查：

```text
python -B -X utf8 <技能目录>/scripts/环境自检.py --要求 text
python -B -X utf8 <技能目录>/scripts/环境自检.py --要求 screenwriting
```

Word 能力检查：

```text
python -B -X utf8 <技能目录>/scripts/环境自检.py --要求 word --格式 json
```

确实缺少 Word 依赖时，可在项目 `临时工作/` 的虚拟环境使用 `requirements-word.txt`，pip 缓存也放项目中。不安装大型办公套件以绕过缺失能力。本包保留 Python-docx 1.2、Pillow 12 的已用范围。

自检退出码：0 可用；2 缺少能力；3 尚未验证。`--要求 render` 是只读探测，不能证明真实页面已经通过，须实际渲染和逐页检查。优先用宿主 documents 渲染器；其环境有捆绑运行库时使用捆绑版本。

## 最小示例

将 `examples/最小示例/` 复制到独立项目目录。不要在安装目录导出 Word。四份源稿是可复用格式示例，不表示生成过示例中的资产或视频。

```text
python -B -X utf8 <技能目录>/scripts/导出说明书.py <项目目录>/归档/文档源稿/剧本.md --项目目录 <项目目录>
python -B -X utf8 <技能目录>/scripts/导出说明书.py <项目目录>/归档/文档源稿/资产设定.md --项目目录 <项目目录>
python -B -X utf8 <技能目录>/scripts/导出说明书.py <项目目录>/归档/文档源稿/分镜.md --项目目录 <项目目录>
python -B -X utf8 <技能目录>/scripts/导出说明书.py <项目目录>/归档/文档源稿/视频提示词.md --项目目录 <项目目录>
python -B -X utf8 <技能目录>/scripts/检查项目.py <项目目录> --模式 word
```

路径有空格时按所在 shell 规则加引号。正式输出同名当前稿；`--草稿` 输出到项目 `临时工作/导出预览/`。`--输出` 只允许项目临时工作范围；冻结历史的明确修复另有 `--修复归档`，不会自动更改历史。

只核对文本时用 `--模式 text`，不要求 Word 依赖。旧名 `分镜图提示词`、`视频提示词与台词` 仍兼容，已有项目无需批量迁移；同类不能同时有新旧两份当前稿。新内容统一使用当前模板，即使沿用旧文件名。

## 维护者验证

这些检查用于升级，不是每个创作项目都要执行。测试目录必须是项目临时工作中的专用目录，不能指定已有用户素材目录。示例 PowerShell：

```powershell
$skillRoot = '<技能目录>' # 指向本机实际已安装的 video-workflow，不是解压外层
$testRoot = '<项目目录>\临时工作\技能测试'
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$env:VIDEO_WORKFLOW_TEST_ROOT = $testRoot
$env:TEMP = $testRoot
$env:TMP = $testRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B -X utf8 "$skillRoot\tests\环境自检测试.py"
python -B -X utf8 "$skillRoot\tests\执行检查.py" --工作目录 "$testRoot\执行检查"
python -B -X utf8 "$skillRoot\tests\流程守卫测试.py"
```

中文测试文件直接运行，不用可能返回零项的默认 unittest discover。除代码回归，还须演练真实输入、确认局部改动与阶段停止行为，并导出、渲染、检查示例 Word。测试通过只能证明被测试的流程和格式，不证明自动编剧达到 owner 的审美标准；通过真实批准/否决样本逐步校准。

## 来源与许可

沿用 [screenwriting-skills](https://github.com/jtydhr88/screenwriting-skills) 六模块的精简适配；固定来源与范围见 [SOURCE](third_party/screenwriting-skills/SOURCE.md)。本次新增的有限循环、状态守卫和交付规则属于本工作流设计，不声称上游已实现同一自动系统。

原创文件采用 [MIT](LICENSE)。第三方许可见 [THIRD_PARTY](THIRD_PARTY.md)，上游原许可及 NOTICE 保留。用户项目照片、品牌资料、字体、音乐、平台服务及其生成内容不因本包许可证而自动获授权；私有素材和账户信息不进入技能包。
