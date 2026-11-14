# project2tutorial

把任意项目拆成一套**能读懂、能复现、还能拿出去讲**的多章 Markdown 教程。

它是给 AI Agent（Claude Code、Cursor、DeepSeek Harness 等）用的 **skill**：你只负责编排一条由子 agent 组成的流水线，不亲手写章节、不亲手画架构图。输入是一个代码仓库 / 压缩包 / 一堆按专题写的笔记，输出是一棵按阅读顺序生长的教程目录树。

![project2tutorial 工作流：11 个阶段、6 个角色、1 道机械闸门](assets/workflow.svg)

---

## 安装

### 方式一：skills CLI（推荐，一行装好）

```bash
npx skills add https://github.com/Jenlybein/project2tutorial --skill project2tutorial
```

- 默认装到**当前项目**：CLI 会自动识别并写入 `.agents/skills/`、`.claude/skills/` 等目标目录，并生成 `skills-lock.json` 便于团队复现；
- 加 `--global` 装到用户级，所有项目都能用；
- 加 `--agent '*'` 装到本机所有它支持的 agent；
- 只想先看看仓库里有什么：`npx skills add https://github.com/Jenlybein/project2tutorial -l`。

### 方式二：手动 clone

Skill 目录约定是 `~/.agents/skills/<name>/SKILL.md`，本仓库的根目录就是 skill 根，直接 clone 进去即可：

```bash
# macOS / Linux
git clone https://github.com/Jenlybein/project2tutorial.git ~/.agents/skills/project2tutorial

# Windows PowerShell
git clone https://github.com/Jenlybein/project2tutorial.git "$env:USERPROFILE\.agents\skills\project2tutorial"
```

两种方式装出来的是同一份内容：`SKILL.md` + `references/` + `scripts/` + `assets/`。装好之后，遇到「帮我拆解这个项目」「把这个仓库讲透」「这个项目面试该怎么讲」这类请求，Agent 会自动加载它。

---

## 为什么值得用

三个问题决定了它必须这么组织：

**1. 先建底座，再分析。**
两到三个分析成员各自摸索同一份代码库，必然得出互相矛盾的结论。所以第一步先产出一份**只记录「是什么」、不含任何判断**的事实底座，全员基于同一份开工——分歧的地基就没了。

**2. 文件是消息总线。**
一个阶段的完整正文必须落成文件，下一阶段拿到的是**文件路径 + 一句「整篇读完再开工」**。摘要一旦进了上下文，内容就丢了。

**3. 三个检查方向不可合并。**
主笔管「写得清不清楚」，工程师管「跑不跑得通」，审计管「漏没漏、对不对得上」。只做前两项，教程会「看起来很完整但少了东西」。

还有两条：**每个实现步骤先写 `00-来龙去脉.md`**，讲清上一步留下什么、项目进展到哪、为什么做这个功能、做完是什么样，再进入难点、流转与动手；四篇各守分工，每个知识点交代「从哪来 / 为什么现在 / 到哪去」，让初级程序员顺着读也不一头雾水，但不哄人、不靠降低信息密度换易读（完整尺度见 [references/output-spec.md](<references/output-spec.md>)）。另一条是动笔前的硬规矩：**术语、归属、数字必须先冻结**。四十多篇的教程，一致性靠「写的人记性好」不成立。一次跳过冻结的完整事故复盘见 [references/canon-and-glossary.md](<references/canon-and-glossary.md>)。

---

## 怎么触发

对它说人话就行，例如：

- 「我本地有个项目 `D:\projects\mini-rag`，帮我拆解成一套能看懂、也能从零复现的多章教程」
- 「不用写教程，我只想搞明白这个仓库分几块、一次问答请求怎么从入口跑到向量库」
- 「我攒了 20 多篇按专题写的笔记，帮我整理成按实现步骤组织的教程，数字和上限别丢」
- 「教程写好了，帮我拆一下这东西面试该怎么讲、简历能怎么写」

技能内部按你手里的材料判四档：**A** 完整拆解 + 全教程、**B** 只要架构、**C** 已有架构只要教程、**D** 只要章节文档。**A 档再按项目规模自动分 A-lite（默认，约 10–11 次派工）与 A-全量（23–28 次）：小项目合并 0.5/1/2、单写手 2–3 批、Phase 5 换人双查。两档都只在写作首批抽检一次，并采用三层派工输入。**

**档位判据、A 档规模分流、Phase 序列、降级规则的唯一真相源是 [references/workflows.md](<references/workflows.md>)**；每个 Phase 怎么跑见 [references/pipeline.md](<references/pipeline.md>)。两处关键纪律：会写章节正文的档位都要先过 2.5 + 2.8（C 必做 2.5，2.8 的口径来源随档位变，逐档见 pipeline.md 的 Phase 2.8）；面试与简历章只在 A 默认产出，跳过要在汇报里说一声。

阶段之间的交接永远是「文件路径 + 整篇读完再开工」，不是摘要。六个角色的分工表与派工模板见 [SKILL.md](<SKILL.md>)。

---

## 质量闸门

交付前必须跑机械审计，**脚本有 error 就不许汇报**：

```bash
python scripts/audit_teardown.py "<教程目录>" --glossary "<教程目录>/.work/28-authoring/glossary.md"

# 严格模式：README 必须直达每一个文件
python scripts/audit_teardown.py "<教程目录>" --readme-strict --json

# 审计 skill 说明仓库自身（跳过 SVG 画法示例与图片模板示例的误报）
python scripts/audit_teardown.py . --profile skill --no-readme-check
```

它分两层检查：

| 层 | 查什么 |
|---|---|
| **文件系统层** | 断链、配图可达与归属目录、`alt` 是否说清内容、SVG 是否合法、全篇有无 Mermaid / 字符画 / 正文里的 SVG 源码、README 导航覆盖、孤立与空置配图目录 |
| **文本层**（专治「看起来完整」） | 唯一 H1、标题层级跳跃、附录倒置、编号式 H2、步骤编号断档、自链接、全角括号配对、单篇行数（600 提醒 / 900 硬上限）、跨文件重复代码块与表格、冻结词表 `_Avoid_` 命中、中文夹多余空格 |

常用参数：

```bash
--glossary PATH        冻结词表路径（给了才做术语检查）
--max-lines N          单篇行数建议上限，默认 600
--max-lines-hard N     单篇行数硬上限，默认 900
--readme-strict        README 必须直接链到每个文件
--no-readme-check      跳过 README 覆盖检查
--profile skill        审计 skill 说明仓库自身，跳过示例类误报
--json                 机器可读输出
```

退出码：有 error 返回 1；warn 不改变退出码但需人眼判断。八条交付底线（技术栈三层、验证点、导航与术语、溯源、每步来龙去脉与叙述链、面试简历可核验、配图、术语冻结与单篇体量）见 [SKILL.md](<SKILL.md>) 与 [references/output-spec.md](<references/output-spec.md>)。

---

## 仓库结构

```
project2tutorial/
├── SKILL.md                     # 技能主文件：角色表、派工机制、档位判据、底线
├── README.md                    # 本文件
├── assets/workflow.svg          # 工作流图（手写 SVG）
├── evals/evals.json             # 产物与触发判别的评测用例
├── references/
│   ├── workflows.md             # 档位与 Phase 序列的唯一真相源
│   ├── pipeline.md              # 每个 Phase 的输入、验收、交接
│   ├── output-spec.md           # 交付目录形态、四件套分工、叙述链三问、页型边界
│   ├── canon-and-glossary.md    # 事故复盘、账本字段、自检 12 条
│   ├── diagrams.md              # 图型选择、SVG 画法、路径与 alt
│   └── roles/                   # 六份角色作业说明，派工时整篇下发
└── scripts/
    ├── audit_teardown.py        # 机械审计：文件系统层 + 文本层
    └── scaffold_teardown.py     # 建目录骨架与 .work/
```

## 它不创造事实

代码里读不出来的设计意图，只能标「推测 + 依据」，不能写成结论；命令没在干净环境验证过，就标「需验证」。

用户会拿这套教程去复现、去投简历——写错的代价由他承担。所以宁可写「未定位」，不要写看起来很懂的猜测。

## License

MIT，见 [LICENSE](LICENSE)。你可以自由使用、修改、再发布，保留版权声明即可。
