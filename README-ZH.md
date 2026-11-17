# Story Simulate

一个按章节推进的互动小说引擎：**先让世界里的人物行动，再把发生的事写成小说。** 每章结束后，由读者选择（或自己写）下一章的方向。

## 每章的流程

```
导演安排场景（只定地点、在场人物和起始情境，不定结果）
  → 角色轮流行动：每个角色只能看到自己知道的事实和亲历的往事，自己决定说什么、做什么
  → 设定审校：检查有没有角色用了不该知道的信息、违背世界规则等，并修正
  → 叙述者根据事件记录和上一章结尾原文写正文
  → 润色：去掉 AI 腔
  → 把状态变化（位置、情绪、目标、谁知道了什么、关系）写回世界状态
  → 根据新的世界状态给出 3 个下一章方向
```

**世界状态（WorldState）是唯一的事实来源**，包括：角色、各角色已知的事实与秘密、关系、完整事件时间线、未解决的线索。界面右侧可以看到它，“幕后：事件记录”标签页可以看到每章实际发生了什么。

## 功能

- 输入故事需求和/或上传素材（txt / md / pdf）。长素材会分段整理再合并，不会直接截断。
- 蓝图可以反复按意见修改，确认后才开始写第一章。
- 每章可以：从 3 个方向里选一个、自己写方向、重写本章、回退到任意一章重新选择。
- 任务状态保存在磁盘上；失败或后端重启后可以一键重试，失败时不会写入半成品状态。

## 启动

需要 Node.js 18+ 和 Python 3.11+。

```bash
cp .env.example .env      # 填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME
npm run setup:all
npm run dev               # 前端 http://localhost:3000，后端 http://localhost:5001
```

任意 OpenAI 兼容接口都可以使用。生成一章大约需要 15–25 次 LLM 调用（其中角色行动约 6–12 次），
建议把 `LLM_WRITER_MODEL_NAME` 设为写作能力更强的模型，用于写正文和润色。模拟参数见 `.env.example`。

## 代码结构

```
backend/app/
  story/models.py    数据模型：WorldState / Character / Fact / Event / Chapter / StorySession
  story/engine.py    引擎：素材整理、蓝图、导演、角色行动、审校、写作、润色、状态回写、方向生成
  story/prompts.py   所有提示词
  story/memory.py    从 WorldState 中检索上下文（按角色、关系、可见范围，加文本相似度）
  story/service.py   后台任务（状态持久化、重试、回退）
  story/store.py     存储：uploads/stories/<id>/session.json、story.md
  api/story.py       REST 接口 /api/story/*
frontend/src/views/  Home.vue（创建 / 列表）、StoryView.vue（蓝图、阅读、方向选择、世界状态）
```
