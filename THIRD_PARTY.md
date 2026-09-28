# 第三方软件说明

`video-workflow` 的基础文字工作流与 `scripts/环境自检.py` 只使用 Python 标准库。以下软件只在启用相应扩展时使用，不随本仓库再分发：

| 软件 | 用途 | 本项目测试版本 | 上游许可证 |
| --- | --- | --- | --- |
| [python-docx](https://github.com/python-openxml/python-docx) | 生成和读取 Word `.docx` | 1.2.0 | MIT |
| [Pillow](https://github.com/python-pillow/Pillow) | 读取图片尺寸并协助嵌图 | 12.3.0 | MIT-CMU |

本包内置了 [screenwriting-skills](https://github.com/jtydhr88/screenwriting-skills) 六个核心模块原创方法的[轻量适配](references/编剧集成.md)。上游作者为 Terry Jia，适配来源、固定提交与范围见 [SOURCE](third_party/screenwriting-skills/SOURCE.md)，其 [MIT 许可证](third_party/screenwriting-skills/LICENSE) 和 [NOTICE](third_party/screenwriting-skills/NOTICE) 随包保留。未复制原项目的书籍/影视引文、参考库或完整调度器；这些第三方内容不纳入本包 MIT 授权。

本包的[视觉方向与评审](references/视觉方向与评审.md)还精简转述了三个 MIT 项目的方法：RampStack Co. 的 `creative-direction` / `art-direction`、Noah Raford 的 `art-direct`，以及 Cinematic Shot Design Skill contributors 的单镜头设计规则。固定提交、采用范围与排除项见 [SOURCE](third_party/visual-direction/SOURCE.md)，三份上游 MIT 许可证原文见 [LICENSES](third_party/visual-direction/LICENSES)。其中 Cinematic Shot Design Skill 只用于可选的关键镜头备选试验，不构成本工作流默认的三方案流程。

Word、WPS Office、LibreOffice、Poppler、TapNow、Codex 的 documents/imagegen 能力以及外部完整编剧与视觉方向技能不是本仓库的一部分；它们分别受各自的条款和许可证约束。

本仓库的 MIT 许可证只覆盖仓库贡献者原创并随仓库发布的文件。用户项目中的人物照片、品牌素材、音乐、视频、字体、第三方服务输出和其他技能不因此获得许可；使用者仍需自行确认相应权利。
