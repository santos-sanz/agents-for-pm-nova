# Research Notes

This file keeps sourced claims separate from the deck. Use it to validate claims before rehearsal or publication.

## Nova Event

- Event page: https://app.novatalent.com/events/1320
- Public API: https://quasar.novatalent.com/public/events/1320
- Title: From PM to AI Builder: Deploy Your First Agent with Anthropic | Online
- Date: June 10, 2026
- Time: 18:00-19:00 Europe/Madrid
- Format: Online
- Language: English

## The 95% GenAI Pilot Claim

Source used for the talk narrative:

- MIT/NANDA, *The GenAI Divide: State of AI in Business 2025*: https://www.artificialintelligence-news.com/wp-content/uploads/2025/08/ai_report_2025.pdf

Working claim:

> The report states that 95% of enterprise GenAI pilots were not producing measurable or visible business returns.

How to use it:

- Use the statistic as the opening problem statement.
- Do not over-focus on the exact percentage during the talk.
- The important point is the gap between impressive demos and deployed systems that change workflows.

Talk phrasing:

> The report made explicit what many teams were already feeling: demos are easy, deployed impact is hard.

## Cynefin

Reference:

- Cynefin wiki: https://cynefin.io/index.php/Cynefin

Talk usage:

- Use Cynefin as a decision tool for PMs.
- Avoid making it academic.
- Explain that "clear" is the newer label for the domain many people used to call "simple."

Domains for the talk:

- Chaotic: act first to stabilize.
- Complex: probe, sense, respond.
- Complicated: analyze with expertise.
- Clear: categorize and apply known practice.

## Water-Cycle Analogy

Purpose:

Use the water cycle to explain how knowledge can move a problem across Cynefin domains.

Narrative:

- What once felt chaotic or mystical became observable.
- What became observable was modeled by experts.
- What experts modeled became simple enough to teach to children.

Important nuance:

The analogy should not mock pre-scientific explanations. It should show how the same phenomenon can move domains as knowledge, models, and teaching improve.

## Anthropic: Building Effective Agents

Reference:

- https://www.anthropic.com/engineering/building-effective-agents

Useful framing:

- Agents are systems where models dynamically direct their own processes and tool usage.
- Workflows are more predictable, coded paths.
- The talk should preserve the distinction: not every AI automation needs an agent.

Talk phrasing:

> A workflow is what you use when the path is known. An agent is what you use when the path must be decided at runtime.

## Claude Managed Agents

Reference:

- https://platform.claude.com/docs/en/managed-agents/overview

Talk usage:

Claude Managed Agents is the demo example for platform simplification. It lets the talk show an agent as more than a single model call:

- agent definition;
- environment;
- session;
- tool execution;
- streaming events;
- output inspection.

Implementation note:

Managed Agents is a beta product surface. The demo should include a fallback transcript and prebuilt output.

## Expert Deployment Services

### Anthropic Enterprise AI Services

Reference:

- https://www.anthropic.com/news/enterprise-ai-services-company

Talk usage:

Use this as evidence that frontier labs are moving closer to enterprise deployment and implementation work.

### OpenAI Deployment Company

Reference:

- https://openai.com/index/openai-launches-the-deployment-company/

Talk usage:

Use this as the paired example for the "expert deployment services" response.

Note:

The OpenAI page may be blocked by Cloudflare in some environments. Keep the URL in sources but verify manually before presenting if needed.

## Slidev

Reference:

- https://sli.dev/guide/

Why it was chosen:

- Markdown source of truth.
- Presenter notes.
- Mermaid diagrams.
- Live drawing/annotation.
- Exportable to static site or PDF.

## Claims To Avoid

- Do not claim Claude Managed Agents is generally available unless confirmed at rehearsal time.
- Do not claim the demo provides financial advice.
- Do not claim all AI pilots fail for the same reason.
- Do not claim consulting is the only path for enterprise AI deployment.
