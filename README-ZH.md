# MiroFish Story MVP

当前这个仓库已经先改造成一版 **按章节推进的交互式小说引擎 MVP**。

你给它一个随机种子、一段设定、或者一份文本素材，系统会先生成一个轻量级 `story bible`，写出当前章节，然后给出 **3 个下一章 topic 候选**。用户点击其中一个，系统再继续写下一章。

## 当前 MVP 流程

1. **种子输入**
   上传文本材料，或者直接填写故事需求。
2. **世界 / 图谱准备**
   继续复用原有的图谱构建和模拟准备流程。
3. **启动故事会话**
   生成故事设定和第一章。
4. **章节工作台**
   阅读当前章节，并从 3 个下一章 topic 中选择一个。
5. **后续互动**
   章节生成后仍可进入已有的世界 / 角色视图。

## 这次改造后的核心变化

- 原来的“报告生成”链路，现在被当成 **故事会话** 链路使用。
- Step 4 不再是预测报告页。
- Step 4 现在是 **章节阅读 + 下一章 topic 选择** 页面。
- 后端现在持久化的数据包括：
  - 故事标题 / premise / 风格
  - 已生成章节
  - 当前可选 topic
  - 已选择 topic 历史

## MVP 的关键行为

- 一次只生成一章，不直接整本写完。
- 每章结束后固定生成 **3 个下一章候选 topic**。
- 用户不选 topic，故事就不会自动继续。
- 为了兼容旧结构，故事数据目前仍然保存在 `backend/uploads/reports/` 目录下。

## 关键文件

- 后端故事主循环：`backend/app/services/story_mvp.py`
- 故事会话接口：`backend/app/api/report.py`
- Step 4 章节界面：`frontend/src/components/Step4Report.vue`
- 前端故事 API：`frontend/src/api/report.js`

## 当前接口说明

虽然路由名还保留 `/api/report/*`，但语义已经改成故事模式：

- `POST /api/report/generate`
  创建一个故事会话，并生成第一章。
- `GET /api/report/<report_id>`
  获取当前故事会话状态。
- `POST /api/report/<report_id>/choose-topic`
  选择一个下一章 topic，并继续生成下一章。

## 本地开发

### 环境要求

- Node.js 18+
- Python 3.11+
- `uv`
- 已配置 `LLM_API_KEY`

### 安装依赖

```bash
npm run setup:all
```

或者分步安装：

```bash
npm run setup
npm run setup:backend
```

### 启动项目

```bash
npm run dev
```

默认端口：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:5001`

## 当前限制

- 公开路由名称还叫 `report`，这一轮只改了行为和主链命名。
- Step 5 里还有不少旧的 report 文案和变量名没完全清干净。
- “Story Guide Chat” 现在只是一个轻量占位，不是完整的剧情问答 Agent。
- 还没有实现完整分支树、回退重选、章节重写流水线。

## 下一步建议

1. 把路由、视图、模型里的 `report` 统一改成 `story`。
2. 增加章节目录和分支历史。
3. 增加“重写本章”和“重新生成 topic”。
4. 把 Step 5 也统一成小说术语和流程。
