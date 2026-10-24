# 自用操作

使用Python标准库；不依赖原job-search-batch安装，不复制旧SMTP代码或个人发件地址。依次运行，任何失败停止相关动作。以下`CONFIG`和`SKILL`是使用者指定的绝对路径。

```sh
python3 "$SKILL/scripts/agent.py" --config "$CONFIG" doctor
python3 "$SKILL/scripts/agent.py" --config "$CONFIG" check --package /绝对路径/package.json
python3 "$SKILL/scripts/agent.py" --config "$CONFIG" reserve --package /绝对路径/package.json
# 真实用户授权与材料检查通过后，由可用浏览器工具在有效期内执行一次申请。
python3 "$SKILL/scripts/agent.py" --config "$CONFIG" confirm --batch 本次执行ID --job-key '规范化公司|规范化岗位ID' --outcome confirmed --evidence /绝对路径/receipt.json
python3 "$SKILL/scripts/agent.py" --config "$CONFIG" sync --batch 本次执行ID
python3 "$SKILL/scripts/agent.py" --config "$CONFIG" sync --batch 本次执行ID --write
# 打开OfferPath中正确岗位的云端附件预览，实际检查后：
python3 "$SKILL/scripts/agent.py" --config "$CONFIG" preview --batch 本次执行ID --job-key '规范化公司|规范化岗位ID' --evidence /绝对路径/preview.json
python3 "$SKILL/scripts/agent.py" --config "$CONFIG" status --batch 本次执行ID
```

`check`与`reserve`都实时读OfferPath，仅reserve修改本地状态。reserve保存附件原始字节及申请包、建立唯一岗位锁，初始unknown。没有自动解锁/删除命令；未确认、进程中断或许可超时不能重新申请。成功confirm可针对同一次执行查证，不得重新点击提交。

`sync`默认只读预演；`--write`才写正式台账。仅confirmed可同步，使用reserve时的PDF快照，不从后来改动的路径重新取件。同步每岗可恢复；已有不同附件不覆盖。已确认面试/结束状态保持原样，只补本次缺失证据和实际附件。服务端现有接口缺少记录CAS，仍须避免与本人同时编辑同一记录，不能声称严格跨设备防并发。

状态：`unknown/pending` → `confirmed/pending` → `confirmed/bytes_verified` → `confirmed/complete`。首次sync成功仅证明附件字节回读，预览仍待人工检查。sync失败保持检查点，仅重新sync，不重新reserve或投递。

`doctor`核查私有文件入口及正式台账只读连通，两次读取计算指纹，不创建云端测试记录、不发送邮件、不上传文件。测试使用独立临时SQLite与合成文件，不能把合成预览作为真实材料验收。运行测试：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$SKILL/tests" -v`。

私有配置JSON（不得放入技能目录；不存在的路径不猜填）：

```json
{
  "policy_path": "/使用者工作区/岗位投递执行规范.md",
  "profile_path": "/使用者工作区/个人配置.md",
  "workbench_path": "/使用者工作区/求职工作台.md",
  "facts_path": "/使用者工作区/项目事实.md",
  "batch_root": "/使用者工作区/批次",
  "state_db": "/使用者私有目录/执行状态.sqlite3",
  "resume_pages": 1,
  "legacy_lock_databases": [],
  "offerpath": {
    "base_url": "https://offerpath.xingo.fun",
    "keychain": {"service": "使用者既有钥匙串服务名", "account": "使用者既有账户名"}
  }
}
```

此版本真实HTTP认证目前适配macOS security钥匙串；缺少授权或令牌过期时由本人处理。不得自动创建令牌或查找其他凭据。未来跨平台凭据接入尚未实现。路径、私人信息、SQLite、真实申请包、简历和回执均在技能目录外。公开仓库只包含通用代码、说明与合成示例，发布时检查许可证和文件清单；不得打包使用者私有工作区。
