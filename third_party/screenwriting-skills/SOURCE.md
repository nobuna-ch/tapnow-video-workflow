# screenwriting-skills 来源与适配范围

- 上游：[jtydhr88/screenwriting-skills](https://github.com/jtydhr88/screenwriting-skills)。
- 核对的提交：[50825325b3940a17f032129851f5c83382863000](https://github.com/jtydhr88/screenwriting-skills/commit/50825325b3940a17f032129851f5c83382863000)。
- 核对日期：2026-09-22。六个本地核心模块与 sw-workflow 的内容同该提交一致；未据此声称某个安装渠道或 release 版本。
- 原作者版权：Copyright (c) 2026 Terry Jia。保留原文 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)，两者与上游该提交一致。

本包中的 [编剧集成](../../references/编剧集成.md) 是对下列模块原创原则、检查方法和职责划分的精简转述与短视频适配，并非完整原技能或其参考库：

| 上游模块 | 采用的方法范围 | 本包适配 |
| --- | --- | --- |
| sw-premise-theme | 前提、主控思想、一句话故事、戏核 | 聚焦表达目标和可见核心动作 |
| sw-story-structure | 因果推进、开头、转变、结尾与短篇结构 | 按实际秒数组织段落，不要求长片页码和卡片 |
| sw-character-conflict | 人物背景、当下欲望、选择与转变 | 只补影响当场反应的动机，不建长篇人物研究 |
| sw-scene-craft | 场景目的、行动反应、细节/道具、过渡 | 落到分镜切点、产品因果与物件状态 |
| sw-dialogue | 对白行动、信息控制、人物用语、停顿和重复 | 落到角色原句、表演和同镜声音交付 |
| sw-format-adaptation | 可见动作、按目标修改、改编选择 | 沿用 TapNow 制作 Word，不套投稿格式 |

上游原文件统一位于该提交的 `plugins/screenwriting/skills/<模块名>/SKILL.md`；[模块目录](https://github.com/jtydhr88/screenwriting-skills/tree/50825325b3940a17f032129851f5c83382863000/plugins/screenwriting/skills) 可供查阅。本包不需要联网访问这些链接即可运行内置文字流程。

本次适配未复制原 reference.md、书籍/影视/戏曲引文、逐片分析表、故事圣经模板或完整调度器。上游 NOTICE 所列第三方书籍、译本、剧本等不因原仓库或本包采用 MIT 而重新授权。完整原技能仅在使用者已安装且确有需要时按需读取，其文件不由本包修改或复制进用户项目。

video-workflow 的文件、时长、资产和交付约定优先用于本工作流；这属于集成适配范围，不代表修改了上游对其他媒介的原始规则。升级上游参考时人工复核以上范围与本地行为，不在每次运行时自动拉取最新内容。
