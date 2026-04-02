# Catalyst — Feature Dependency Map

**Last Updated:** 2026-04-01
**Purpose:** Show what depends on what, so the roadmap respects build order.

---

## Visual Dependency Chain

```
                    ┌─────────────────┐
                    │  Fix Truncated   │
                    │  Frontend Files  │
                    │  (TD-001–005)    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Frontend        │
                    │  Compiles        │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼───────┐ ┌───▼──────────┐
     │ Upload Flow   │ │ Signal     │ │ Entity       │
     │ Works in UI   │ │ Triage     │ │ Browser      │
     │               │ │ Works in UI│ │ Works in UI  │
     └────────┬──────┘ └────┬───────┘ └───┬──────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │  Detection →    │
                    │  Finding        │
                    │  Workflow in UI │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  AI Memo        │
                    │  Generation     │
                    │  (Claude/OpenAI)│
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼───────┐ ┌───▼──────────┐
     │ Visual Polish │ │ Deployment │ │ README +     │
     │ + Error       │ │ IBM Cloud  │ │ GitHub       │
     │ Handling      │ │            │ │ Cleanup      │
     └───────────────┘ └────────────┘ └──────────────┘
```

---

## Detailed Dependencies

### Milestone 1: Frontend Compilation
**Depends on:** Nothing — this is the foundation
**Blocks:** Everything else

| Task | Depends On |
|------|-----------|
| Fix types.ts | Nothing |
| Fix CaseDetailView.tsx | types.ts fixed |
| Fix DocumentsTab.tsx | types.ts fixed |
| Fix PdfViewer.tsx | types.ts fixed, fetchDocumentDetail defined |
| Add fetchDocumentDetail to api.ts | Nothing |
| Run ExtractionStatus migration | Nothing (backend-only) |

### Milestone 2: Golden Path Wiring
**Depends on:** Milestone 1 complete (frontend compiles)
**Blocks:** AI memo generation, polish, deployment

| Task | Depends On |
|------|-----------|
| Upload flow end-to-end in UI | DocumentsTab.tsx fixed, CaseDetailView.tsx fixed |
| Signal triage connected | TriageView working (already works if frontend compiles) |
| Detection → Finding workflow in UI | Signal triage working, Finding API endpoints connected |
| Activity feed shows events | DashboardView working (already works if frontend compiles) |

### Milestone 3: AI Memo Generation
**Depends on:** Milestone 2 complete (Golden Path works)
**Blocks:** Nothing directly, but should precede deployment for full demo

| Task | Depends On |
|------|-----------|
| API key management (env vars) | Nothing |
| Structured data assembly (findings, entities, signals → prompt) | Findings exist in database (Milestone 2) |
| LLM API call and response handling | API key configured |
| Human review/edit interface | Frontend compiles (Milestone 1) |
| PDF/DOCX export with hash table | Memo content generated |

### Milestone 4: Polish and Deploy
**Depends on:** Milestones 1-3 complete
**Blocks:** GitHub cleanup (needs deployed URL for README)

| Task | Depends On |
|------|-----------|
| Loading states and error handling | Frontend compiles |
| Dockerfile creation | Application works locally |
| IBM Cloud PostgreSQL provisioning | IBM Cloud account active |
| Static file serving | Dockerfile works |
| Deploy and verify | All above |

### Milestone 5: GitHub and Documentation
**Depends on:** Milestone 4 (need deployed URL and screenshots)
**Blocks:** Nothing — this is the final step

---

## V2 Dependencies (Post-V1)

| Feature | Depends On |
|---------|-----------|
| Relationship graph | Entity data populated (V1 provides this), React-Flow or D3 library |
| Timeline view | AuditLog data (V1 provides this) |
| User authentication | Frontend multi-user design (V1 shell has user context) |
| Agency-specific templates | Basic memo generation (Milestone 3) |
| Ohio UCC connector | Nothing — independent module |
