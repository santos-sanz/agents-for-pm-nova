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

## Anthropic Code with Claude Workshop References

Source collection:

- Anthropic, Code with Claude workshops repository: https://github.com/anthropics/cwc-workshops/tree/main
- How to get to production faster with Claude Managed Agents: https://youtu.be/zenIB7XLZxQ
- Build a production-ready agent with Claude Managed Agents: https://youtu.be/jWWsLe4Gh5Y
- Getting more out of the Claude Platform: https://youtu.be/QIriO1-vHYw
- Ship your first Managed Agent: https://youtu.be/19HDQ9HppOA
- Tool, skill, or subagent? Decomposing an agent that outgrew its prompt: https://youtu.be/mWvtOHlZM-I

Best references for this Nova workshop:

- Ship Your First Managed Agent: https://github.com/anthropics/cwc-workshops/tree/main/ship-your-first-managed-agent
  - Best fit for a PM-friendly workshop because the build is organized around seven small API calls: agent, environment, file upload, session, event stream, local tool handling, and cleanup.
  - Useful steering idea: keep the demo path linear and visible. The audience should always know which resource is being created or inspected.
- Production-ready Agent / Deal Desk: https://github.com/anthropics/cwc-workshops/tree/main/production-ready-agent
  - Best fit for showing what "production-ready" means beyond a toy demo: event streams, gated tool confirmations, sub-agent threads, memory, resource mounts, and outcome definitions.
  - Useful steering idea: after the first demo works, ask what would need to be added before a company could trust it.
- Agent Decomposition: https://github.com/anthropics/cwc-workshops/tree/main/agent-decomposition
  - Best fit for the "prompt is not the product" lesson. It gives a practical decision framework: tool call, skill, or subagent.
  - Useful steering idea: turn the audience discussion into decomposition practice. Ask what should be deterministic tooling, what should live as reusable instructions, and what deserves a separate agent.

Lower-priority references for the live deck:

- "How to get to production faster" is useful background for the managed-platform argument, but overlaps with the production-ready and first-agent material.
- "Getting more out of the Claude Platform" is broad platform context. Keep it as optional prep unless the audience needs more Claude Platform orientation.

Workshop steering ideas:

- Anchor every section in the same loop: define the job, attach evidence, run the session, inspect events, improve the contract.
- Use the first managed-agent demo as the "happy path" and the production-ready workshop as the "what changes before real deployment?" discussion.
- Ask PMs to critique outputs, not prompts. This keeps the session grounded in product quality, evidence, risk, and reviewability.
- Treat tool/skill/subagent decomposition as a workshop exercise: give the room one messy agent behavior and ask where each responsibility should move.
- Keep "managed" concrete: fewer custom decisions about environment, session state, tool execution, event streams, and inspection.

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

## Visual Sources

- Nova event image: https://quasar.novatalent.com/public/events/1320
- Anthropic agent diagrams: https://www.anthropic.com/engineering/building-effective-agents
- Water-cycle cloud background by Dadee Aissa on Unsplash: https://unsplash.com/photos/cumulus-clouds-Pe1Ol9oLc4o

## Claims To Avoid

- Do not claim Claude Managed Agents is generally available unless confirmed at rehearsal time.
- Do not claim the demo provides financial advice.
- Do not claim all AI pilots fail for the same reason.
- Do not claim consulting is the only path for enterprise AI deployment.
