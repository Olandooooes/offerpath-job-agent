# 千问办公与 OfferPath 本地连接

当前优先支持 [Codex](codex.md)，千问适配暂缓。本文保留早期配置和共享工具字段说明，当前不作为推荐安装入口。

本指南针对千问办公国内桌面端。技能负责求职流程，客户端AI负责内容定制，本地MCP桥负责材料、PDF与记录。无需购买模型API；客户端自身的额度、网络和权益仍由平台决定。

## 当前验证范围

本版本按千问办公公开的技能目录和Streamable HTTP配置格式适配。本地测试使用合成经历、模拟MCP宿主和本机假OfferPath服务，没有调用外部模型、提交招聘申请或向生产账户写测试记录。这只描述本仓库的测试：合成标记表示资料是虚构的；实际在千问办公中运行时，内容定制由客户端模型处理，不代表客户端没有调用模型。

**尚未完成千问办公客户端实机验收。**官方文档描述了Skill UI，但没有为本项目证明可依赖的“对话内真人PDF确认”协议。因此当前由本人打开一次本地审阅页，查看实际PDF后确认；AI不能替本人点击。这里无需来回复制简历材料或AI返回JSON，也不用进入OfferPath网站逐条建记录。

安装GitHub技能只取得代码和流程，不代表本地桥已经运行、正式账户已经连接，或公共MCP/OAuth服务已经上线。

## 1. 安装技能

可以在千问办公桌面端直接说：

```text
请将 https://github.com/Olandooooes/offerpath-job-agent 安装到
~/.qwenworkcn/skills/offerpath-job-agent。
如果已有同名技能，保留本地修改，先说明如何更新，不要覆盖私有资料。
```

国内客户端目录为 `~/.qwenworkcn/skills/`；国际版文档使用不同目录，请按本人客户端文档处理，不把Qwen Code视作千问办公。也可以在「扩展 → 技能 → 安装技能」上传本仓库。

## 2. 建立仓库外的合成工作区

以下命令从仓库根目录运行。使用本机Python 3.9或更新版本；如依赖安装由系统限制，先创建虚拟环境。不要把真实简历或令牌放进技能目录。

```sh
python3 -m venv /path/to/private-runtime
/path/to/private-runtime/bin/python -m pip install -r requirements-qwenwork.txt
/path/to/private-runtime/bin/python scripts/qwenwork.py init \
  --workspace /path/to/new-private-workspace
/path/to/private-runtime/bin/python scripts/qwenwork.py serve \
  --workspace /path/to/new-private-workspace --port 4327
```

Windows使用虚拟环境的 `Scripts/python.exe`。`init`要求一个尚不存在、位于仓库外的新目录；默认只创建虚构人物、岗位、私有状态及本地连接密钥，不读取作者配置或真实凭据。`serve`仅监听本机环回地址，不应使用公网隧道或对外暴露端口。

PDF需要支持中文的TrueType字体。本机优先检测macOS的Arial Unicode、Windows的微软雅黑或Linux的文泉驿正黑；找不到时通过`OFFERPATH_CJK_FONT`指定本人有权使用的TTF/TTC文件。Linux可安装`fonts-wqy-zenhei`，实际图片预览另需`poppler-utils`；未安装渲染器时打开实际PDF检查。字体不会复制进仓库或随技能分发。

保持服务终端运行。在另一个终端生成千问连接配置：

```sh
/path/to/private-runtime/bin/python scripts/qwenwork.py config \
  --workspace /path/to/new-private-workspace \
  --output /path/to/private-qwenwork-connection.json
/path/to/private-runtime/bin/python scripts/qwenwork.py open \
  --workspace /path/to/new-private-workspace
```

`config`将含本地Bearer的JSON写入仓库外私有文件，不打印令牌；文件与工作区均不得发布。`open`打开本人本地审阅控制页，不在终端显示登录密钥。状态可通过以下命令检查：

```sh
/path/to/private-runtime/bin/python scripts/qwenwork.py status \
  --workspace /path/to/new-private-workspace
```

## 3. 添加连接器

在千问办公桌面端打开「扩展 → 连接器 → 添加 → 粘贴JSON配置」，将上一步生成的私有配置导入。它采用如下结构；公开样例中的占位符不是可用令牌：

```json
{
  "mcpServers": {
    "offerpath-local": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:4327/mcp",
      "headers": {
        "Authorization": "Bearer REPLACE_WITH_LOCAL_BRIDGE_TOKEN"
      }
    }
  }
}
```

此处Bearer只授权千问访问本机桥，不是模型API Key，也不是OfferPath账户令牌。不要让AI把配置内容打印到聊天里，不要把私有配置上传Issue或提交Git。

添加后新建一个对话任务，确认能发现OfferPath工具。若连不上，先检查服务正在运行、地址和端口一致、配置文件完整及连接器已启用。不要改成无需认证或开放公网端口来排查。实际客户端若不接受本机HTTP或自定义请求头，应保留错误信息、标明尚未连通，不宣称已完成实机适配。

## 4. 先确认资料，再在对话里定制

默认演示已有已确认的虚构资料。改用本人资料时，把用户选择的简历提供给千问办公AI；技能通过 `propose_profile` 提取并保存待确认事实。本人打开本地页逐项核对经历、数字和来源后确认；资料未确认时，`get_context` 会拒绝定制。AI不得代为确认，资料变化后重新确认。

用户可直接把完整岗位JD交给AI，工具 `save_job` 保存公司、岗位、地点、来源、完整JD和要求。岗位有自己的ID和版本；不必手改profile/jobs JSON文件，也不从缺失信息猜造事实。

这些资料是仓库外的本人私有缓存，不代表云端事实库已经部署。选择何种资料发送给客户端AI由本人决定；本地桥未调用模型API与客户端推理是两件事。

### 合成体验示例

可以直接说：

```text
使用 offerpath-job-agent，列出合成岗位并选一个。
读取该岗位和已确认事实，逐岗改写简历，保留事实依据并列出缺口。
给我实际PDF，等我本人在本地页面审阅确认后再继续。
本次只做合成体验，不是真实投递。
```

桥会公开下列工具；参数细节以 `tools/list` 的实际schema为准，工具名称可能带客户端服务前缀。

| 工具 | 用途与关键参数 |
| --- | --- |
| `propose_profile` | `{name,education,skills,synthetic,facts:[{id,title,details}]}`，保存待确认资料；`synthetic`准确说明是否虚构 |
| `save_job` | `{company,role,location,url,jd,requirements,synthetic}`，保存完整JD，生成或更新岗位ID与版本 |
| `list_jobs` | 列出当前模式中可用岗位 |
| `get_context` | `{job_id, fact_ids?}`，读取本岗材料和选定事实，返回绑定版本的 `context_id` |
| `save_draft` | 保存 `{context_id, summary:{text,fact_ids}, items:[{fact_id,title,text}], mapping:[{requirement_index,fact_id:null或事实ID}], changes:[]}` |
| `get_pdf` | `{package_id}`，返回实际PDF的 `resource_uri`、本地文件和 `review_url`；生成文件不等于已确认 |
| `report_application` | `{package_id,outcome:"user_reported"或"unknown",same_attachment,receipt}`，记录本人陈述与回执，不提交申请 |
| `sync_records` | `{package_id}`，在当前模式及本人授权范围内同步记录和实际附件 |
| `list_records` | 读取已形成记录的申请、附件与同步状态；不列出待审草稿包 |

`items.title`必须原样保持`get_context`中对应事实的原标题；可针对岗位改写`text`，不要把事实标题改成岗位名称。`mapping.requirement_index`为`requirements`数组的0基索引：第一项用0，第二项用1，每项按schema映射。保留`save_draft`返回的`package_id`供`get_pdf`使用，不能靠`list_records`找回尚未形成记录的待审包。AI应保持事实ID、量化内容与版本一致。引用检查能发现缺失和错误引用，不能证明改写语义一定真实；本人仍须审阅内容。

### PDF确认

AI使用 `get_pdf` 返回的 `resource_uri` 调用MCP `resources/read`读取实际PDF并展示给本人。客户端不能显示PDF资源时，使用返回的 `review_url` 打开本地审阅页中的实际文件；不要只展示草稿文字后声称用户看过PDF。本人在本地页登录、查看实际文件并明确确认该版本；确认绑定具体文件，不接受工具传入 `approved:true` 等替代。内容改变后必须确认新PDF。即使AI能控制浏览器，也不能替本人完成这一步。

### 申请与同步

本地桥没有投递工具。合成体验使用明确标注的虚构结果；真实流程由本人完成申请后，AI才按本人陈述记录。`user_reported`表示用户报告，不冒称系统已独立核验；`unknown`保持未知，不能作为成功同步或再次投递的依据。

记录同步需要已确认的实际PDF。保存草稿、确认PDF、点击提交和记录增加分别是不同状态；不能互相替代。同步失败只补同步，不重投。正式账户附件下载比对与实际云端预览仍是独立检查，未完成时报告待完成项。

## 5. 本人连接自己的正式OfferPath

合成流程通过后，如本人已经在自己的OfferPath账户取得可用的独立自动化授权，可以打开本地审阅控制页，在连接表单中输入本人服务地址和令牌。**只经本机页面填写，不经过AI聊天，不复用作者账户，不把OfferPath令牌放入千问MCP配置。**

本地桥的Bearer、页面登录密钥和OfferPath令牌作用不同。私有工作区中的 `secrets.json` 必须保留在仓库外，不能发布或转发。绑定后先检查当前模式与本人账户，不把合成申请包同步到生产。

每次重新授权或更换连接都会更改连接身份，旧确认不会自动继承。服务端稳定账户ID尚未验证，不能将相同`base_url`视为同一个人或同一个账户。

已由本人申报但留档未完成的同一次申请，可以在本地PDF卡中由本人重新查看实际PDF，明确选择绑定到当前目标“仅补同步”。这不是再次投递，也不是AI确认接口；未知结果和已完成记录禁止迁移，旧PDF、原回执和岗位锁不变，不继承旧云端预览状态。未申报的草稿则应在新连接下重新读取材料和定制。

需要断开时，在本地控制页操作断开连接：删除本机保存的OfferPath令牌并回到合成模式。这不会撤销服务端授权；如需撤销令牌，须由本人在OfferPath账户中操作。

本项目没有部署新的OAuth授权页。现有OfferPath授权入口对本人账户是否可用，需要本人页面验证；未取得有效授权时留在合成模式，不能承诺所有新用户已经能一键连接。真实同步适配可以用本机假服务验证协议，但不等于生产联调已完成。

如果只想用网页看板，可独立访问 [OfferPath](https://offerpath.xingo.fun)；连接器适配不会替换原有产品功能。

## 原有Codex流程

已有Codex用户继续使用原来的 `scripts/setup.py`、`scripts/agent.py`、私有配置和macOS钥匙串。连接器的本地合成台账不授予原有检查器投递许可，不替代正式状态源，不解除历史未知结果锁。原命令见[操作说明](operations.md)。

## 官方依据与后续验收

核查日期：2026-10-24。

- [千问办公技能](https://docs.qwenwork.cn/features/skills)：公开GitHub安装方法、国内技能目录及Skill UI概述。没有据此宣称本项目已进入官方市场。
- [千问办公连接器](https://docs.qwenwork.cn/features/connectors)：自定义MCP、Streamable HTTP与Bearer请求头配置，以及新增连接器后新建任务的要求。
- [千问办公个人版权益](https://help.aliyun.com/zh/qwenwork/personal-benefits)：客户端权益由平台提供；本项目不收模型调用费，也不承诺第三方长期无限免费额度。

本地验收应覆盖MCP初始化/工具发现、事实引用和旧版本拦截、两岗位不同PDF、真人确认门槛、未知结果锁、附件哈希与同步幂等，以及账号隔离和私有信息不泄露。后续仍需在本人千问办公桌面端验证安装、发现工具、文件展示和确认回流。客户端未实机验证、生产授权未验证、云端预览未检查时，分别保留相应未完成状态。
