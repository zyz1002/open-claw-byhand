# 工具目录

## 可用工具

- **get_current_time**: 获取当前亚洲/上海时间。适用场景：回答时间相关问题或在从自然语言创建提醒前获取时间。关键参数：timezone。示例：`{"timezone": "Asia/Shanghai"}`

- **calculate**: 计算简单数学表达式。适用场景：用户需要进行算术运算或快速计算。关键参数：expression。示例：`{"expression": "(10-3)/7"}`

- **save_memory**: 存储用户的持久信息，如偏好、身份细节和重复性事实。适用场景：用户说了值得以后记住的内容。关键参数：user_id, content, category。示例：`{"user_id": "u1", "content": "偏好简洁的回答", "category": "preference"}`

- **recall_memories**: 读取当前用户相关的活跃记忆。适用场景：之前的偏好或事实有助于更好地回答。关键参数：user_id, keyword。示例：`{"user_id": "u1", "keyword": "preference"}`

- **update_memory_status**: 将记忆标记为过期或已完成。适用场景：用户纠正或完成了之前记住的内容。关键参数：user_id, keyword, status。示例：`{"user_id": "u1", "keyword": "健身计划", "status": "completed"}`

- **create_reminder**: 创建一次性或周期性提醒。适用场景：用户明确要求在特定时间提醒。关键参数：user_id, content, trigger_type, trigger_expr。示例：`{"user_id": "u1", "content": "面试准备", "trigger_type": "date", "trigger_expr": "2026-04-16 20:00:00"}`

- **list_reminders**: 列出用户的活跃提醒。适用场景：用户想知道有哪些提醒。关键参数：user_id。示例：`{"user_id": "u1"}`

- **cancel_reminder**: 按 ID 取消活跃提醒。适用场景：用户明确要取消提醒。关键参数：user_id, reminder_id。示例：`{"user_id": "u1", "reminder_id": "3"}`

- **query_knowledge_hub**: 使用混合搜索（语义 + 关键词）在 RAG 知识库中搜索相关文档。适用场景：用户询问特定项目知识、技术文档，或任何可能受益于已存储文档的问题。关键参数：query, top_k, collection。示例：`{"query": "混合搜索是怎么实现的", "top_k": 5}`

- **list_collections**: 列出 RAG 知识库中所有可用的文档集合。适用场景：用户想了解有哪些知识库或文档集合。关键参数：include_stats。示例：`{"include_stats": true}`

- **get_document_summary**: 获取知识库中特定文档的摘要和元数据。适用场景：搜索结果后用户想了解某个文档的详情。关键参数：doc_id, collection。示例：`{"doc_id": "doc_abc123"}`
