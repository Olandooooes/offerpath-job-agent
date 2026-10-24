# 申请包与证据契约（v1）

JSON文件放在使用者批次目录，不能放进技能分享目录。所有artifact为`{"path":"/绝对路径","sha256":"64位SHA256"}`，哈希使用最终原始字节；所有时间为ISO8601含时区。`policy_sha256`绑定私有规范原文，规范改动后须重新审阅申请包。

顶层：
- `version`: 1；`batch_id`: 唯一执行批次ID。
- `authorization`: `action: "apply"`、`user_instruction_ref`（本次本人指示来源，不得自造）、`max_submissions`（本人授权上限）。同次授权的子批次必须使用相同来源标识，程序累计检查已保留岗位数；未知或超时锁也计入，防止补位重投。JSON中的授权字段是审计记录，不能替代真实用户授权或通过换标识取得新授权。
- `policy_sha256`: 私有配置policy_path原文哈希。
- `jobs`: 岗位对象数组。自用时推荐每次只保留一个即将提交的岗位，批次名加岗位后缀，并在外部总清单控制总数，不得用子批次突破本人上限。

每岗字段：
- 身份：`company`, `role`, `job_id`, `location`, `url`, `channel`, `application_id`（已存在OfferPath记录ID，或新建UUID；保存后不变）。
- `verified_at`: 24小时内核验时间。
- `screening`: `passed: true`，以及非空`employer`, `location`, `duties`, `qualifications`, `salary`, `posting_date`, `employment`, `language`。填写具体证据、缺口与配置判断，不填笼统“已核对”。发布日期例外需引用本人批准范围。
- artifact字段：`jd`（完整JD快照）、`base_resume`（认可母版）、`resume`（最终专用PDF）、`source`（专用生成源或内容源）。
- `tailoring`: `substantive_reviewed: true`、`changes`（实质内容改动列表）、`mapping`（数组，每条`requirement`, `evidence`, `fact_source`）、`diff`（定制差异说明artifact）。只改标题不合格，代理必须读实际内容判断。
- `visual`: `passed: true`, `resume_sha256`, `checked_at`, `pages`, `previews`（实际渲染预览artifact数组）。填写前必须看过每页，机器哈希检查不能替代视觉验收。
- `form_reviewed: true`, `selected_attachment_sha256`；`requires_user_confirmation: false`或为true并提供`user_confirmation_ref`。上传后再次核对实际附件，发现不同则不提交。
- 可选`application_answers`保存与招聘相关的实际表单回答，`next_action`保存明确下一步。不得写凭据或无关私人敏感信息。同步备注将关联本地JD、定制说明、验收及回执路径。

confirm回执JSON：`application_id`, `job_id`, `resume_sha256`, `kind`（platform_success/candidate_center/smtp_accepted之一）、`summary`、`observed_at`、`submitted_at`、`artifact`（平台回执截图或文本）。submitted_at是实际提交时刻，不能为通过检查伪填当前时间；与reserve相隔超过10分钟时停止自动合格认定，保留结果人工审计。unknown也要提供已观察的证据，不能写成功。证据文件不得含令牌或无关私信。

preview回读JSON：`application_id`, `resume_sha256`, `passed: true`, `checked_at`, `artifact`（实际云端预览截图/核查记录）。实际打开云端预览核对后才能填，下载字节一致不等于预览检查通过。

检查器只能校验结构、版本、哈希、时效和状态，无法证明映射正确、视觉结论真实、用户授权有效；禁止用合成图、假回执或空泛说明获得放行。
