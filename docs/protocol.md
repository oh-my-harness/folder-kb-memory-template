# 模板接口

使用 Folder KB 文件协议 1.1。输入是完整更新工作区快照、request.json 和 materials.jsonl；输出是完整候选工作区和 result.json。检索目录必须是工作区的子目录，默认 knowledge；metadata/memory-template 保存更新状态，不对消费 Agent 开放。

程序只生成候选，不修改输入、不发布、不操作 Git。发布者必须先校验结果及 base_version，再使用平台自己的发布机制。平台的更新进程可按绑定模板调度程序、通过环境变量注入模型连接、生成候选并等待管理员审核发布。本仓库同时保留命令行程序和独立协议联调脚本。

材料沿用平台的 new_content、correction、observation。内部记忆类型 user、feedback、project、reference 只用于组织记忆，不是 MCP 新接口。observation 暂存待审；明确 correction 才允许替换已有记忆。同一材料 ID 重放幂等，ID 对应内容变化则拒绝。

LLM 可提出结构化整理决策，程序校验类型、作用域、已有目标、证据引文和操作条件。引文校验只能保证来源存在，不能证明推断正确；候选仍需审核。首次初始化要求无本模板状态及无已有 INDEX.md，避免覆盖其他模板。更新时禁止覆盖被人工修改的托管文件，应先整理为纠错材料或显式迁移。
