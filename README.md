<div align="center">

# 🤖 OfferPath Job Agent

**简体中文 · [English](README.en.md)**

### 让每一次申请，都有准备、有证据、有下文。

一个陪你认真找工作的开源 Agent Skill。<br/>
用你自己的AI读懂岗位、逐岗定制简历，把PDF确认与申请记录连接到OfferPath。

[🌐 打开 OfferPath](https://offerpath.xingo.fun) · [🚀 开始使用](#-开始使用) · [🧭 完整工作流](#-一次申请怎么走完) · [🛠 开发与测试](#-开发与测试)

![OfferPath求职伙伴：认真修改简历、核对清单，并沿路径整理申请材料的蓝色小机器人](assets/offerpath-companion.png)

**一岗一版简历 · 提交前检查 · 真实回执 · 可追溯记录**

</div>

## 🆕 先在 Codex 中使用

当前优先完善 **Codex + GitHub Skill + 本地 OfferPath 连接器**。你在 Codex 对话里提供简历和完整JD，Agent逐岗定制并生成实际PDF；本人审阅后，再按真实申请结果同步记录与附件。无需在网页和AI之间来回复制结果JSON。

**无需另购模型API。**内容定制使用你现有的Codex模型权益，额度和使用条件由平台决定，不承诺无限免费。连接器只在本机运行，没有部署公共服务或修改OfferPath线上网站。

| 能力 | 当前边界 |
| --- | --- |
| Codex技能与本地MCP连接 | 技能安装与工具连接分两步；需要Python、PDF依赖和一次本地配置 |
| 简历资料与岗位录入 | Codex提出事实供本人确认，保存完整JD；私有资料放在仓库外 |
| 逐岗草稿与实际PDF | Codex生成内容，连接器核验事实引用、版本并生成文件；引用不能自动证明语义真实 |
| PDF确认 | 本人打开本地审阅卡查看具体PDF并确认，AI不得代点 |
| 合成记录同步 | 只写本机模拟台账，保留实际PDF；不写正式账户 |
| 正式OfferPath连接 | 需本人独立授权；正式账户与云端预览仍需分别验收 |
| 原有Codex执行器 | `agent.py`、`setup.py`、离线演示、私有配置及钥匙串认证全部保留 |

[Codex安装与连接指南 →](references/codex.md)

已通过98项本地合成测试，并实测本机Codex app-server的工具发现、草稿保存与实际PDF读取。桌面GUI新用户安装及正式账户联调仍需独立验收，详见[Codex合成验收记录](docs/codex-acceptance.md)。

千问办公等其他客户端**暂缓适配**。已有[千问参考文档](references/qwenwork.md)与代码保留，当前不作为推荐使用入口；先把Codex流程实际跑通，再扩展其他客户端。

## 🌱 为什么做这个项目

找工作常常同时打开招聘网站、简历编辑器、邮箱和一张越来越长的表格。

这个岗位看过完整要求了吗？发出去的是哪一版简历？同一岗位是否在另一个渠道投过？“提交成功”之后，材料和反馈又放在哪里？

OfferPath Job Agent 想让这些问题有据可查。它把求职经验整理成可复用的技能，并用本地检查工具记录每次申请的材料、状态和证据。

它适合愿意认真准备材料、希望借助AI减少重复劳动的人。你决定求职方向与申请范围，Agent协助执行具体工作；每次申请都应体现你真实的经历，以及你能为岗位提供的价值。

## 🧰 它能帮你做什么

| 环节 | 具体工作 | 留下什么 |
| --- | --- | --- |
| 找岗位 | 按你的城市、方向、薪资与时效偏好核查完整JD | 岗位快照、来源与筛选依据 |
| 找匹配 | 将岗位要求对应到你已确认的工作、项目与成果 | JD—经历映射和内部差距记录 |
| 改简历 | 逐岗调整简介、项目排序、表达重点与成果 | 岗位专用源文件、PDF和改动说明 |
| 做检查 | 核查定制证据、视觉验收、授权范围及重复申请 | 可审计的申请包与提交前记录 |
| 记结果 | 按真实回执区分成功、未知和待处理 | 该次申请的回执与材料快照 |
| 同步进度 | 写入OfferPath，并下载比对实际简历附件 | 正式记录、附件核验及预览状态 |

**当前是开发者预览版。**搜索与内容定制由运行技能的AI及其可用工具完成；本地桥负责事实引用和版本检查、PDF与模拟记录。原有Python执行器负责正式申请包检查、状态保留和OfferPath同步。它没有一键全网投递、自动邮件发送或定时跟进功能。

## 🌈 配合 OfferPath，让申请有下文

### [前往 OfferPath → offerpath.xingo.fun](https://offerpath.xingo.fun)

**Agent帮你准备和执行，OfferPath帮你看清求职进度。**

在OfferPath里整理岗位，把想投、已投递、面试等进展集中管理；保存简历附件、备注与下一步，回头就能找到“这家公司、这个岗位、当时交的那份材料”。

原有Codex执行器的OfferPath同步器会把成功申请关联到对应记录，上传提交时保存的PDF快照，再下载比对原始字节。申请已经成功但同步失败时，只补记录和附件，不重新投递。

- **刚开始找工作？** 先在OfferPath整理候选岗位和申请进展。
- **准备让Agent帮忙？** 配置自己的经历和规则，从“只准备、不提交”开始。
- **希望记录跟执行连起来？** 在本人授权的OfferPath账户中启用可用的独立自动化授权，再连接同步器。

你可以单独使用OfferPath管理求职。原有`agent.py`的`check`、`reserve`与`sync`需要可访问的OfferPath账户。新连接器的默认合成模式有独立本地模拟台账，不是正式状态源，也不能为原有投递流程放行。

## 🧭 一次申请怎么走完

```mermaid
flowchart LR
    A[🔎 读完整JD] --> B[🧩 匹配真实经历]
    B --> C[📝 定制专用简历]
    C --> D[👀 渲染与验收]
    D --> E[🔐 授权与实时去重]
    E --> F[📮 提交一次]
    F --> G[🧾 核对真实回执]
    G --> H[🗂 同步OfferPath]
    H --> I[✅ 附件与预览核验]
```

每个岗位有一个申请包：完整JD、真实经历映射、定制说明、源文件、最终PDF、视觉预览和回执。检查器会绑定这些文件的版本；把通用简历改个文件名，不能通过母版一致性检查。

申请包通过检查后，工具在本地SQLite里保存岗位锁与实际PDF字节。随后由Agent在当前授权范围内，通过可用浏览器工具完成申请。没有回执，结果就保持未知，不能盲目再发一次。

### 三个结果，分别看

| 结果 | 说明 |
| --- | --- |
| 申请成功 | 有平台成功回执、候选人中心确认或相应可靠发送证据 |
| 附件核验完成 | OfferPath中的实际PDF已下载，名称、字节与哈希一致 |
| 完整闭环 | 还完成了实际云端预览检查，并保存核验证据 |

“点了提交”“上传成功”“总数增加”都不直接等于完整完成。程序检查也不能替代对简历内容和预览的实际审阅。

## 🚀 开始使用

### 推荐：Codex对话连接器

先让Codex按[连接指南](references/codex.md)安装GitHub技能、建立仓库外合成工作区，并生成本机MCP配置片段。由本人将片段合并到Codex设置或配置，重新载入后开启新任务。**安装技能不等于MCP已连接。**

工具可用后，在Codex中说：

```text
$offerpath-job-agent
先选一个合成岗位，读取已确认经历，按完整JD逐岗定制简历。
给我实际PDF和本地审阅链接，等我本人确认后再继续。
只做合成体验，不连接真实账号、不真实投递。
```

Codex启动MCP进程时会自动启动本机PDF审阅服务，不必另开服务终端。PDF确认仍由本人在本地审阅卡完成，AI不能代点。你可在确认后让Codex模拟报告申请结果并同步本地合成记录；合成结果不能冒充真实回执。

### 保留：原有Codex申请包工作流

已有私有配置可继续使用以下流程，不必迁移。连接器的合成记录不授予原有检查器投递许可，也不解除历史未知结果锁。

### 1. 先试运行测试

原有`agent.py`只使用Python标准库；对话连接器生成和核验PDF需要额外依赖。建议先建立虚拟环境，再安装连接器依赖并运行全部测试：

```sh
git clone https://github.com/Olandooooes/offerpath-job-agent.git
cd offerpath-job-agent
python3 -m pip install -r requirements-connector.txt
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

测试使用临时文件、合成材料、假账户和本机临时HTTP服务。不需要真实账户或令牌，不会发送申请或写入生产记录。环境若禁止本机端口监听，HTTP集成测试需要在允许环回网络的环境运行。

完整测试还需要中文TrueType字体；Linux CI安装`fonts-wqy-zenhei`和`poppler-utils`，其他环境见[Codex字体与启动说明](references/codex.md)。既有HTTP连接器的合成验收范围见[历史验收记录](docs/qwenwork-acceptance.md)；这些结果不代表已完成Codex客户端或正式账户验收。

### 2. 作为Codex技能安装

将本仓库放在你的Codex技能目录。例如，尚未安装同名技能时，可用官方文档中的用户技能目录：

```sh
git clone https://github.com/Olandooooes/offerpath-job-agent.git \
  "$HOME/.agents/skills/offerpath-job-agent"
```

本机已有的`~/.codex/skills/`兼容安装可保留，避免同一技能重复安装。保留同名技能和本地修改，不直接覆盖。让Codex重新发现技能后，使用`$offerpath-job-agent`调用；需要新对话工具时，再完成[本地MCP连接](references/codex.md)。

### 3. 建立自己的私有工作区

运行配置向导，指定**仓库外尚不存在的新目录**；省略路径会询问目录。向导只创建私有模板，不读取钥匙串、不联网、不授予投递权限。

```sh
python3 scripts/setup.py init --workspace /path/to/new-private-workspace
python3 scripts/setup.py check --config /path/to/new-private-workspace/agent.local.json
```

本地检查会指出路径缺失、仓库内路径和未修改的钥匙串引用；它不会核验事实内容或凭据。默认模板尚不能用于真实投递，先填写资料和本人既有钥匙串引用，再运行 `agent.py doctor`。已存在的目录不会被覆盖。

也可以手动配置：

从[配置样例](examples/private-config.example.json)、[个人资料样例](examples/profile.example.md)和[执行规范样例](examples/policy.example.md)开始。将修改后的个人文件放到仓库外，再配置真实绝对路径。

```text
你的私有工作区/
├── AGENTS.md
├── agent.local.json
├── profile.md
├── facts.md
├── policy.md
├── workbench.md
├── batches/
└── runtime/
```

在你工作区的`AGENTS.md`中写明本技能使用哪个私有JSON配置。城市、薪资、事实来源、简历母版和授权边界都由你决定，不继承作者的个人经历或偏好。

**原有Codex执行器的真实账户认证仅适配macOS钥匙串。**先由本人在OfferPath中获取可用的独立自动化授权，并通过系统钥匙串工具保存；配置文件只引用条目名称，不存令牌明文。授权入口是否可用以本人账户页面为准，连接失败时不会自动创建或扩大权限。

### 4. 从“只准备”开始

```text
$offerpath-job-agent
按我的个人配置筛选三个岗位，读取完整JD，逐岗定制简历并渲染验收。
保存申请包和匹配说明，先不提交。
```

当你确实决定投递，再明确这次的数量、渠道以及是否要逐岗审阅：

```text
$offerpath-job-agent
本批投递三个合格岗位，必须逐岗定制、验收并实时去重。
完成后同步OfferPath记录和实际附件，核对云端预览并报告未完成项。
```

调用技能不自动授权发送；批量授权也不省略定制、核验和回执检查。

## 🎭 离线合成演示

无需账户即可试跑完整状态流程：

```sh
python3 scripts/demo.py --output /path/to/new-demo-directory
```

打开生成的 `index.html` 查看虚构JD、定制前后文字、状态变化和模拟OfferPath记录；`report.json` 为机器可读结果，另有合成PDF与证据文件。输出目录必须在仓库外且尚不存在。

**演示不联网、不读凭据、不投递、不写真实云端。**回执和视觉验收均为明确标注的模拟数据，不能作为真实投递证据。它演示检查与同步状态机，不会自动生成真实岗位的简历，也不替代实际PDF渲染验收。

## 🛠 开发与测试

命令入口：`scripts/agent.py`。完整字段与操作见[申请包契约](references/package.md)和[操作说明](references/operations.md)。

| 命令 | 行为 |
| --- | --- |
| `doctor` | 核查私有文件入口与OfferPath只读连通 |
| `check` | 校验申请包并实时查询正式台账，不产生提交许可 |
| `reserve` | 重新检查后保存岗位锁和最终PDF快照 |
| `confirm` | 绑定真实回执，记录confirmed或unknown |
| `sync` | 默认只读预演；加`--write`才同步正式记录与附件 |
| `preview` | 保存实际云端预览核验证据，标记完整闭环 |
| `status` | 查看该批岗位结果及同步进度 |

```sh
python3 scripts/agent.py --config /你的私有工作区/agent.local.json doctor
python3 scripts/agent.py --config /你的私有工作区/agent.local.json \
  check --package /你的私有工作区/batches/package.json
```

原有自动测试覆盖通用母版改名、跨批复用同PDF、授权数量超限、旧发送锁、实时去重、结果未知恢复、错误回执、附件快照、同步中断恢复、不同附件保护以及面试状态保留等。测试中的合成图片与PDF不代表真实材料的视觉验收。

## 🧩 项目结构

```text
offerpath-job-agent/
├── SKILL.md                 Agent的流程入口
├── scripts/agent.py         原有Codex检查、执行状态与OfferPath同步
├── scripts/codex_bridge.py  Codex stdio MCP入口与配置生成
├── scripts/qwenwork.py      复用的本地材料、PDF审阅与记录服务
├── requirements-connector.txt  PDF依赖（无需模型API）
├── tests/test_agent.py      合成测试与本机HTTP集成测试
├── references/              申请包契约与命令说明
├── examples/                无个人数据的配置起点
├── docs/                    协作、设计与素材说明
└── assets/                  项目卡通封面
```

## 🪴 接下来慢慢长大

- [x] 逐岗材料版本与证据检查
- [x] 持久化未知结果锁和附件快照
- [x] OfferPath记录与实际PDF同步回读
- [x] 云端预览独立确认
- [x] 合成HTTP集成测试
- [x] 仓库外私有工作区初始化与本地配置检查
- [x] 离线合成流程演示
- [ ] 更友好的申请包编辑体验
- [ ] Codex客户端安装、工具发现与PDF确认回流实机验收
- [ ] 其他AI客户端适配（千问办公暂缓）
- [ ] 面向普通用户的OfferPath独立授权连接
- [ ] Windows/Linux正式账户凭据适配
- [ ] 对内容定制质量的辅助评估与更多行为测试
- [ ] 基于当前接口能力改进并发冲突处理
- [ ] 更多招聘渠道的明确适配与回执采集

这些未勾选项是计划，不是已上线能力。欢迎用Issue描述实际使用场景，或通过PR逐步完善。

## 🤝 一起完善

请先阅读[贡献说明](CONTRIBUTING.md)。反馈时使用脱敏或合成示例；真实简历、公司保密材料、个人配置、回执、执行库和账户凭据都不要提交到公共仓库。

本项目来自个人求职流程的持续整理，技能入口与Python执行器在此维护。它可以作为你自己的求职工作流起点；结合其他项目时，请保留各自的许可证与必要署名。

代码采用[MIT许可证](LICENSE)。卡通封面使用AI生成，生成方式与提示词见[素材说明](docs/artwork.md)。

---

<div align="center">

**认真准备，也记得看见自己的每一步。**

[🌐 用 OfferPath 整理下一次机会](https://offerpath.xingo.fun)

</div>
