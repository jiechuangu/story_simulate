# MiroFish Story MVP

MiroFish is currently adapted into an **interactive chapter-by-chapter fiction engine**.

You provide a seed idea, source text, or a short premise. The system builds a lightweight story bible, writes the current chapter, then offers **3 candidate topics** for the next chapter. The user chooses one topic, and the story continues along that branch.

## Current MVP Flow

1. **Seed Ingestion**
   Upload text material or enter a story requirement.
2. **World / Graph Prep**
   Reuse the existing graph-building and simulation preparation pipeline.
3. **Story Session Start**
   Generate a story bible plus Chapter 1.
4. **Chapter Workspace**
   Read the latest chapter and choose the next topic from 3 options.
5. **Interactive Follow-up**
   Continue into the world / character views after a chapter is generated.

## What Changed

- The old “report generation” path is now used as a **story session** path.
- Step 4 is no longer a prediction report viewer.
- Step 4 is now a **chapter reader + next-topic selector**.
- The backend now persists:
  - story title / premise / style
  - generated chapters
  - next-topic candidates
  - selected topic history

## Key MVP Behavior

- Start with one chapter, not a full novel.
- After each chapter, generate exactly **3 next chapter topics**.
- The story only continues after the user chooses one topic.
- Story state is saved under the existing `backend/uploads/reports/` directory for compatibility.

## Main Files

- Backend story loop: `backend/app/services/story_mvp.py`
- Story session API: `backend/app/api/report.py`
- Step 4 chapter UI: `frontend/src/components/Step4Report.vue`
- Story session client API: `frontend/src/api/report.js`

## API Notes

The project still keeps the historical `/api/report/*` routes for compatibility, but the semantics are now story-oriented:

- `POST /api/report/generate`
  Creates a story session and generates Chapter 1.
- `GET /api/report/<report_id>`
  Returns the current story session.
- `POST /api/report/<report_id>/choose-topic`
  Selects one of the proposed topics and generates the next chapter.

## Local Development

### Requirements

- Node.js 18+
- Python 3.11+
- `uv`
- configured `LLM_API_KEY`

### Setup

```bash
npm run setup:all
```

Or step by step:

```bash
npm run setup
npm run setup:backend
```

### Run

```bash
npm run dev
```

Default ports:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:5001`

## Current Limitations

- The public route names still say `report`; only the behavior changed.
- Step 5 still contains older report-oriented naming in some views.
- The “story guide chat” endpoint is only a lightweight placeholder in this MVP.
- The full branch tree, rewind, and chapter revision pipeline are not implemented yet.

## Next Recommended Iterations

1. Rename route/view/model terminology from `report` to `story`.
2. Add branch history and chapter index.
3. Add “rewrite this chapter” and “regenerate topic candidates”.
4. Refactor Step 5 to match story terminology throughout.
