---
name: reguardian
description: Verify EU AI Act compliance for AI features in this repository with the Reguardian MCP server. Use before writing or modifying code that uses AI models, processes personal data through AI, or automates decisions about people; after applying a compliance fix to log it; and when a compliance question needs an article-grounded answer.
---

# Reguardian

Reguardian checks planned and applied changes against the EU AI Act (Regulation (EU) 2024/1689) through the MCP server at https://mcp.reguardian.eu. The server returns article-grounded verdicts and keeps a compliance record for this project. Reguardian is a decision aid, not legal advice.

## When to run an analysis

Call `analyze_code_snippet` before writing or modifying code that:

- calls an AI model (chat, generation, classification, recommendation, scoring, ranking);
- processes personal data through AI;
- automates or supports a decision about a person (hiring, credit, pricing, moderation, support triage);
- ships user-facing AI disclosure, logging, or human-review requirements.

Pass `taskDescription` when the change is not written yet: it states what you are about to do and lets Reguardian count the violation as prevented. Pass `filePath` so verdicts are attributable to the file.

## Reading verdicts and risk tiers

`analyze_code_snippet` returns per-obligation verdicts: `violation`, `concern`, or `compliant`, plus a remediation type: `mechanical` (the agent can apply it) or `structural` (a human must decide).

`get_business_context` returns the project risk tier:

| Tier | Meaning | What it obliges |
| --- | --- | --- |
| `NO_OBLIGATION` | Outside the Act's obligations | Keep the record; re-check when the feature changes |
| `LIMITED_RISK` | Transparency duties | Disclose AI interaction, label AI-generated content |
| `HIGH_RISK` | Annex III use cases | Risk management, logging, human oversight, documentation |
| `UNACCEPTABLE` | Prohibited practices | Stop: the feature must not ship as designed |

Quote the article references returned by the server (article_refs). Never invent article numbers, verdicts, or metrics.

## Logging fixes

Call `log_fix` after applying a correction:

- `obligationId`: the obligation ID from `analyze_code_snippet` or `get_business_context`;
- `summary`: feed-ready, at most 160 characters, for example "Added the AI disclosure banner to the support chat";
- `files`: the files you touched (shown as files_touched on the dashboard);
- `newCodeSnippet`: the corrected code, so the server can verify it;
- `kind`: `fixed` after applying the correction, `prevented` when the check stopped a violation before it shipped.

Only verified fixes move the score. If verification fails, the score is untouched: fix the code and call `log_fix` again.

## Surfacing what was avoided

The project feed shows what Reguardian helped avoid (évité). It is built from logged events only. Report only what the server confirmed: prevented analyses and verified fixes, with their article references and files. Never invent, estimate, or reword an avoided entry, and never claim a fix you did not log.

## Decisions

`request_decision` opens a structural decision when an obligation needs human judgment (prohibited or limited scope, Annex III scope, provider or deployer role). Present the returned `presentToUser` text to the user exactly as returned, then record the answer with `record_decision` before continuing. Never apply a structural obligation silently.

`get_score` returns the current score and counters. `search_regulation` searches the Act itself when an article-grounded explanation is needed.
