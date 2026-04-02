# Catalyst — Risk Register

**Last Updated:** 2026-04-01
**Purpose:** Identify and track risks that could block or delay the project.

---

## Active Risks

| ID | Likelihood | Impact | Description | Mitigation |
|----|-----------|--------|-------------|------------|
| RISK-001 | HIGH | HIGH | **GovOS CountyFusion outage.** The majority of Ohio county recorder portals (~70/88) run on GovOS CountyFusion. If GovOS has an outage, the county recorder connector's URL builder produces dead links. | The connector is human-in-the-loop by design — investigators verify URLs before using them. No automated dependency on GovOS uptime. |
| RISK-002 | MEDIUM | HIGH | **AI API costs.** Claude/OpenAI API calls for memo generation will incur costs. Unrestricted usage during development could get expensive. | Set API budget limits. Use small test cases during development. Cache responses during testing. Consider using Haiku/GPT-4-mini for dev, full model for production. |
| RISK-003 | MEDIUM | HIGH | **Context loss between sessions.** The AI assistant loses context when conversations end. Critical project state could be lost or misunderstood. | CURRENT_STATE.md and session handoff template mitigate this. Every session ends with an update. |
| RISK-004 | MEDIUM | MEDIUM | **External API changes.** ProPublica, IRS, Ohio SOS could change their APIs or data formats without notice. | All connectors have comprehensive test suites with mocked responses. Changes will be caught by test failures. |
| RISK-005 | LOW | HIGH | **Truncated files recurrence.** Files have been truncated during AI-assisted editing sessions (4 files currently broken). This could happen again. | Always run `npm run build` or `npx tsc --noEmit` after any frontend file edit. Add build check to session handoff checklist. |
| RISK-006 | LOW | MEDIUM | **IBM Cloud deployment complexity.** First deployment to IBM Cloud with Docker + PostgreSQL. Unknown unknowns in configuration. | Research IBM Cloud container deployment early (Milestone 4 prep). Have a fallback plan (Heroku, Railway, or DigitalOcean). |
| RISK-007 | LOW | LOW | **PostgreSQL version mismatch.** Local dev uses PostgreSQL 16 in Docker. IBM Cloud may offer a different version. | PostgreSQL is highly backward-compatible. Test with IBM Cloud's available version early. |

---

## Retired Risks

| ID | Description | Outcome |
|----|-------------|---------|
| *(none yet)* | | |
