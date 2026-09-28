# 视觉方向方法来源与适配范围

核对日期：2026-09-28。本目录记录 `references/视觉方向与评审.md` 中三个视觉方法来源的固定版本与适配边界。它们都是实践性创作方法；本项目不据此声称方法经过同行评审，也不声称其必然产生电影级或其他特定质量的结果。

## 1. RampStack Co. / claude-skills

- 上游：[rampstackco/claude-skills](https://github.com/rampstackco/claude-skills)。
- 固定提交：[3d4510a94a76ead80122c691b5c480f92f3fbe40](https://github.com/rampstackco/claude-skills/commit/3d4510a94a76ead80122c691b5c480f92f3fbe40)。
- 核对文件：[skills/creative-direction/SKILL.md](https://github.com/rampstackco/claude-skills/blob/3d4510a94a76ead80122c691b5c480f92f3fbe40/skills/creative-direction/SKILL.md)、[skills/art-direction/SKILL.md](https://github.com/rampstackco/claude-skills/blob/3d4510a94a76ead80122c691b5c480f92f3fbe40/skills/art-direction/SKILL.md) 和根目录 [LICENSE](https://github.com/rampstackco/claude-skills/blob/3d4510a94a76ead80122c691b5c480f92f3fbe40/LICENSE)。
- 采用范围：将全局视觉方向压缩为四个选择轴（语气、审美取向、受众关系、感官强度），并在具体交付物评审时对照方向、品牌目标和传播目标定位偏差与修正项。
- 排除：未复制完整技能、模板、示例、参考库、站点展示、图片、自动化工具或运行时。
- 许可证与署名：MIT；`Copyright (c) 2026 RampStack Co.`。原文收录于 [LICENSES](LICENSES)。

## 2. Noah Raford / art-direct

- 上游：[nraford7/art-direct](https://github.com/nraford7/art-direct)。
- 固定提交：[2b2c4506abbe9839c36a52728f1a0f9a98c0b5f9](https://github.com/nraford7/art-direct/commit/2b2c4506abbe9839c36a52728f1a0f9a98c0b5f9)。
- 核对文件：[SKILL.md](https://github.com/nraford7/art-direct/blob/2b2c4506abbe9839c36a52728f1a0f9a98c0b5f9/SKILL.md) 和根目录 [LICENSE](https://github.com/nraford7/art-direct/blob/2b2c4506abbe9839c36a52728f1a0f9a98c0b5f9/LICENSE)。
- 采用范围：用 Five-Lens（Literal、Human、Environmental、Metaphorical、Oblique）生成或比较视觉路径；评审时先概括整体视觉语言，再检查内容意图与画面执行的差距，并按段落提出修正。
- 排除：未复制完整技能、风格 YAML、提示词模板、示例、生成脚本、供应商集成或任何图片。
- 许可证与署名：MIT；`Copyright (c) 2026 Noah Raford`。原文收录于 [LICENSES](LICENSES)。

## 3. Cinematic Shot Design Skill contributors

- 上游：[ErosShen/cinematic-shot-design-skill](https://github.com/ErosShen/cinematic-shot-design-skill)。
- 固定提交：[097ffa2b336523bbf094da96aec15900b610faa7](https://github.com/ErosShen/cinematic-shot-design-skill/commit/097ffa2b336523bbf094da96aec15900b610faa7)。
- 核对文件：[SKILL.md](https://github.com/ErosShen/cinematic-shot-design-skill/blob/097ffa2b336523bbf094da96aec15900b610faa7/SKILL.md) 和根目录 [LICENSE](https://github.com/ErosShen/cinematic-shot-design-skill/blob/097ffa2b336523bbf094da96aec15900b610faa7/LICENSE)。
- 采用范围：只在少数关键镜头难以定案时，可选地比较同一戏剧节点的不同拍法，兼顾叙事清晰、构图表达和向下一秒延展的能力；默认只做内部文字比较并交付所选方案。实际试生成仍需已有生图授权并计入本工作流原有额度。
- 明确边界：这是可选的关键镜头试验，不是默认的 A/B/C 三方案流水线；备选方案不是顺拍的三镜分镜，也不是三联画。整场拆镜、镜头数量和剪辑节奏仍由本工作流决定。
- 排除：未复制完整技能、提示词正文、摄影师/艺术家风格调用、示例、图片或工具集成。
- 许可证与署名：MIT；`Copyright (c) 2026 Cinematic Shot Design Skill contributors`。原文收录于 [LICENSES](LICENSES)。

## 本地适配说明

本地文件只保留适合 TapNow 短视频资产准备与评审的中文精简转述，并以项目既有的文件、时长、角色/产品连续性和交付规则为准。以上链接用于溯源和人工升级核对；工作流运行时不下载这些仓库，也未复制或依赖其软件框架、服务或运行时。未随本项目分发任何上游演示图片、第三方媒体或供应商素材。
