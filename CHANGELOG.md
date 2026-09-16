# 更新日志

本插件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [v1.0.0] - 2026-09-16

### 新增

- 群聊连续对话核心功能：@机器人 或唤醒词唤醒后，该用户后续消息免唤醒直接触发 AI 回复
- 滑动窗口超时机制：每发一条消息刷新 `timeout_seconds` 计时，超时自动退出连续对话
- 按「群 ID + 用户 ID」隔离的会话状态，多用户互不影响
- 配置项：`wake_words`、`timeout_seconds`（最小 5 秒）、`enable_at_wake`、`enable_word_wake`、`whitelist_groups`
- 基于 KV 存储的持久化，插件重载后未过期的活跃状态自动恢复
- `on_llm_request` 钩子拦截未唤醒用户的 LLM 请求，机器人对未唤醒用户保持沉默

[unreleased]: https://github.com/Zxin-Pro/astrbot_plugin_continuous_chat/compare/v1.0.0...HEAD
[v1.0.0]: https://github.com/Zxin-Pro/astrbot_plugin_continuous_chat/releases/tag/v1.0.0
