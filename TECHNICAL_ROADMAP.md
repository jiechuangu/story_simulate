# MiroFish Novel Engine Technical Notes

## Scope

This workspace is the isolated optimization copy used to continue the novel-world migration without interfering with the running original project.

## Implemented Optimizations

### 1. Process Page Consolidation

- The actual `/process/:projectId` route is driven by `frontend/src/views/MainView.vue`.
- Ontology generation and graph build now both expose:
  - backend task progress
  - task logs
  - chunk progress details
  - project artifact previews
- The page now recovers state from `project_id` and task polling instead of trusting stale local UI state.

### 2. Task Center And Visual Logs

- Backend task state now persists an in-memory log stream in `backend/app/models/task.py`.
- Frontend home keeps a recent project-task list through `frontend/src/components/ProjectTaskHistory.vue`.
- Step 1 now shows:
  - ontology progress bar
  - graph build progress bar
  - current chunk / total chunk
  - provider / graph id
  - recent task chips
  - latest ontology and graph chunk artifact previews

### 3. Chunk Output Artifacts

Per-project artifact files are written into:

- `backend/uploads/projects/<project_id>/ontology_chunks/`
- `backend/uploads/projects/<project_id>/graph_chunks/`

The backend exposes these previews through:

- `GET /api/graph/project/<project_id>/artifacts`

Files include:

- `chunk_01.json`, `chunk_02.json`, ...
- `summary.json`
- `archive_entities.json`

### 4. Novel Build Defaults

Default graph build chunk settings were raised from `500/50` to `2400/240` in:

- `backend/app/config.py`
- `backend/app/models/project.py`
- `backend/app/services/text_processor.py`

This is meant to reduce request count for long-form novels when using local models.

### 5. Low-Value Entity Lifecycle

The graph builder now treats entities as a lifecycle instead of blindly promoting every mention into the main graph.

Entity states:

- `candidate`: extracted but not yet admitted into the active graph
- `active`: admitted to the main graph and visible in graph queries
- `dormant`: once active but later demoted due to low value and long inactivity

Current scoring signals:

- mention count
- links to core entities
- entity type priority
- aliases
- identity / stage attributes
- description richness

Current thresholds:

- activate when importance is high enough, repeated enough, or linked to core entities
- demote to dormant after long inactivity and weak value

### 6. Rehydration / Memory Recall

Low-value entities are not hard-deleted during evolution.

Current behavior:

- candidate entities stay in canonical memory during the build
- dormant entities keep a serialized snapshot
- snapshots are written to `archive_entities.json`
- if a later chunk mentions the same entity again and the admission score rises, the entity is promoted back to `active`

This is a soft-demotion strategy rather than destructive pruning.

### 7. Graph Query Resilience

`GET /api/graph/data/<graph_id>` now degrades to an empty graph payload with a warning if Neo4j readback fails transiently during incremental build, instead of returning a hard 500 to the UI every time.

### 8. Neo4j Display Filtering

Graph readback now defaults to active entities only.

Effects:

- lower clutter in graph view
- dormant entities stay preserved but hidden from the default graph panel
- relationships attached to inactive endpoints are also hidden from the default graph view

## Remaining Follow-Ups

### High Priority

- Persist archived entity memory outside in-memory task scope for cross-run continuation, not just per-build artifact files.
- Add explicit cancel / pause / resume for long graph tasks.
- Add chunk-level retry from `N`.
- Add a dedicated artifact viewer page instead of raw previews.

### Medium Priority

- Promote chapter-aware chunking over plain fixed-length chunking when chapter headers exist.
- Add ontology evolution suggestions during graph build.
- Add a `main graph` vs `archive graph` distinction in Neo4j if Aura capacity becomes tight.

### Long-Term

- Replace heuristic importance gating with hybrid rules + local embedding similarity + LLM arbitration.
- Add full ontology versioning and migration.
- Support lightweight world preview before full graph build finishes.

## Operational Notes

### Separate Ports

When validating this optimization copy, run it on ports different from the original project.

Suggested example:

- backend: `5002`
- frontend: `3001`

Recommended environment:

```bash
cd /Users/mufeizhao/Downloads/codex_workspace/MiroFish_opt/backend
FLASK_RUN_PORT=5002 python run.py
```

```bash
cd /Users/mufeizhao/Downloads/codex_workspace/MiroFish_opt/frontend
VITE_API_BASE_URL=http://127.0.0.1:5002 npm run dev -- --port 3001
```

## Relevant Files

- `backend/app/api/graph.py`
- `backend/app/models/task.py`
- `backend/app/models/project.py`
- `backend/app/services/neo4j_graph_store.py`
- `backend/app/services/novel_graph_builder.py`
- `frontend/src/views/MainView.vue`
- `frontend/src/components/Step1GraphBuild.vue`
- `frontend/src/components/ProjectTaskHistory.vue`
