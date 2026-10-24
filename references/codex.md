# 在 Codex 中使用 OfferPath Job Agent

当前先完善Codex，其他客户端暂缓。这个技能让Codex读取你选择的简历和完整JD、逐岗定制并生成实际PDF；本地连接器负责事实引用、版本、本人确认和记录附件。它不要求另购模型API，内容定制使用你现有的Codex模型权益，仍受平台额度和使用条件约束。

这是本地开发者预览。安装技能、连接MCP、本人确认PDF和连接正式OfferPath账户是四件事，不能互相替代。已实测本机Codex app-server的工具发现、草稿保存和实际PDF读取；桌面GUI新用户安装及正式账户仍需独立验收，见[验收范围](../docs/codex-acceptance.md)。

## 1. 安装技能和本地依赖

如果没有同名技能，可以从GitHub安装到Codex官方文档中的用户技能目录：

```sh
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/Olandooooes/offerpath-job-agent.git \
  "$HOME/.agents/skills/offerpath-job-agent"
```

本机已有的`~/.codex/skills/offerpath-job-agent`兼容安装可继续保留，避免再安装一份同名技能。已有目录时先保留本地修改，再按Git更新，不覆盖个人资料。让Codex重新发现技能后，可用`$offerpath-job-agent`调用。

也可以把本仓库安装任务交给Codex，但不要让它把私有配置、简历或凭据提交进技能仓库。

以下命令从安装后的仓库根目录运行。使用Python 3.9或更新版本，并在仓库外建立虚拟环境：

```sh
python3 -m venv /path/to/private-runtime
/path/to/private-runtime/bin/python -m pip install -r requirements-connector.txt
```

Windows使用虚拟环境的`Scripts/python.exe`。生成中文PDF需要本机支持中文的TrueType字体：连接器检测macOS的Arial Unicode、Windows的微软雅黑或Linux的文泉驿正黑；也可用`OFFERPATH_CJK_FONT`指定本人有权使用的TTF/TTC文件。字体不会随仓库分发。Linux可安装`fonts-wqy-zenhei`；实际图片预览需要`poppler-utils`，未安装渲染器时应打开实际PDF审阅。

## 2. 建立合成工作区并生成Codex配置

先用虚构资料跑通，暂不连接正式账户。选择一个**尚不存在、位于所有Git仓库之外**的新目录：

```sh
/path/to/private-runtime/bin/python scripts/codex_bridge.py init \
  --workspace /path/to/new-private-workspace
/path/to/private-runtime/bin/python scripts/codex_bridge.py config \
  --workspace /path/to/new-private-workspace \
  --output /path/to/new-private-codex-mcp.toml
```

`init`仅建立虚构人物、合成岗位和私有状态，不读取作者配置或正式凭据。`config`生成一个新的TOML配置片段，使用运行脚本的Python绝对路径、技能脚本绝对路径和你的工作区路径。它只写路径和启动参数，不包含令牌，也不修改Codex全局配置。私有路径仍应留在本机，不上传公开Issue。

由本人把片段合并到Codex的MCP设置或`~/.codex/config.toml`，保留已有设置，避免同名`mcp_servers`条目冲突。它的作用相当于让Codex启动：

```sh
/path/to/private-runtime/bin/python /absolute/path/to/offerpath-job-agent/scripts/codex_bridge.py \
  stdio --workspace /path/to/new-private-workspace
```

无需单独运行上述命令来维持终端。配置生效后，Codex会管理stdio子进程，并由该进程自动启动仅监听本机环回地址的PDF审阅服务。不要把stdio进程通过公网隧道开放，也不要向其标准输出打印调试文字。

**同一私有工作区一次只允许运行一个连接器进程。**第二个Codex任务连接同一工作区前，先结束旧任务的连接器；需要同时使用时，另建独立工作区。不要删除`.lock`文件或SQLite数据库来绕过占用锁。stdio进程关闭后，原本地审阅URL随之失效；重新启动后，让Codex再次调用`get_pdf`取得当前链接，不沿用旧地址。

重新载入Codex的连接配置并开启新任务；若客户端提示需要重启，按提示重启。**技能出现在列表里不等于MCP已连接。**确认当前任务能发现`list_jobs`、`get_context`、`save_draft`和`get_pdf`等工具后，再开始体验。工具名可能带服务前缀。

可检查私有工作区状态：

```sh
/path/to/private-runtime/bin/python scripts/codex_bridge.py status \
  --workspace /path/to/new-private-workspace
```

如果未发现工具，先查生成的Python/脚本/工作区绝对路径是否存在、该Python是否装有PDF依赖，以及Codex是否重新载入了MCP配置。不要重复初始化同一工作区，也不要把“技能已安装”报告为“连接成功”。

## 3. 在Codex里逐岗定制并本人确认PDF

在已连通工具的新任务中说：

```text
$offerpath-job-agent
本次只做合成体验。列出合成岗位，选一个并读取完整JD和已确认经历。
逐岗定制简历，保留事实依据，列出无法证明的要求和改动。
给我实际PDF和本地审阅链接，等我本人确认再继续。
不连接真实账号、不真实投递，不替我点击确认。
```

Codex读取`get_context`返回的本岗材料，使用`save_draft`保存有事实引用和JD映射的专用草稿。连接器生成实际PDF、版本和SHA256。Codex通过`get_pdf`取得文件及`review_url`，可读取MCP PDF资源并向你展示；客户端无法直接展示时，打开本地审阅链接查看实际文件。

本人在本地审阅页登录、核对内容与排版，明确确认该版本。页面登录使用私有工作区`secrets.json`中的`review_code`：仅由本人在本机查看并输入页面，不粘贴到AI聊天、Issue或Git。AI不得读取或代填该口令，也不能代点资料确认、PDF确认或留档预览确认；对话中一句“确认了”也不能替代页面中的版本绑定。修改简历后，新PDF必须重新审阅。

合成工作区已有确认的虚构事实。改用本人简历时，由Codex调用`propose_profile`提出事实，本人先在本地页核对并确认，才能定制。使用`save_job`保存完整JD，不从缺失的信息猜造经历、数字或岗位要求。个人资料始终保存在仓库外；你仍需自行决定哪些内容可以提供给Codex模型。

引用和数字检查不能自动证明语义真实。要逐条核对经历、成果、措辞与原始证据，并检查实际PDF有无截断、缺字或错误分页。

## 4. 用合成结果体验记录和附件同步

本人已确认PDF后，可以继续说：

```text
继续本次合成体验。明确标注“没有发生真实申请”，
模拟用户报告的结果并同步到本地合成台账。
核对留档PDF的文件名、字节和SHA256，给我实际留档预览。
等我本人检查预览后，再报告哪些步骤完成、哪些没有。
```

连接器没有招聘投递工具。`report_application`记录本人陈述，`user_reported`不是独立核验的成功回执，`unknown`保持未知锁定；不能据此冒称申请成功或再投一次。合成记录仅写本机模拟台账，不能写入真实OfferPath账户。

`sync_records`绑定已确认的具体PDF，写记录与附件后重新下载核对，失败只补同步、不重投。实际留档文件还需要本人打开检查。**本地合成留档预览不能代替正式OfferPath的云端预览**；真实流程应分别报告申请结果、流程合规和同步闭环，缺少记录、附件、回执或预览证据时保持未完成。

## 5. 之后再连接自己的OfferPath

合成体验通过后，如你已在自己的[OfferPath](https://offerpath.xingo.fun)账户获得可用的独立自动化授权，可在本地审阅页中由本人填写服务地址和令牌。令牌不经AI聊天、不写入Codex MCP配置，不复用作者账户。该步骤不代表公共OAuth或普通用户一键授权已经上线；正式账户尚需独立验收。

连接身份变化时，旧确认不会自动继承；合成材料不能迁移成真实申请。已经报告、但留档未完成的同一次真实申请，需本人重新核对目标与实际PDF，仅补同步。未知结果保持锁定。断开本机连接不自动撤销服务端令牌，撤销需到自己的OfferPath账户操作。

OfferPath网站原有的岗位看板、记录和附件功能保持不变。你也可以只使用网站管理求职，不连接此技能。

## 保留原有工作流

已有用户继续使用`scripts/setup.py`、`scripts/agent.py`、`scripts/demo.py`、私有JSON配置与macOS钥匙串。新连接器的合成台账不替代正式状态源、不授予旧检查器投递许可、不解除历史发送锁。完整原命令见[README](../README.md)、[申请包契约](package.md)和[操作说明](operations.md)。

底层工具的字段、事实标题与0基JD索引要求沿用现有[共享工具契约](qwenwork.md#4-先确认资料再在对话里定制)。此链接用于查字段，不需要安装或启用千问办公。

## 官方依据与验收边界

- [Codex技能文档](https://learn.chatgpt.com/docs/build-skills)：技能目录与`SKILL.md`使用方式。
- [Codex MCP文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)：stdio服务器和Codex配置方式。

协议测试、合成资料测试、实际客户端安装和正式OfferPath账户联调分别验收。模拟MCP宿主通过不等于真实Codex客户端通过；本地附件回读通过不等于真实云端预览通过。后续验收必须保留这些区别。
