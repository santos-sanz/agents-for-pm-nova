---
theme: default
title: "From PM to AI Builder"
info: |
  Nova talk: From PM to AI Builder: Deploy Your First Agent with Anthropic.
  Speaker: Andrés Santos Sanz.
author: "Andrés Santos Sanz"
class: text-left
drawings:
  enabled: true
  persist: false
transition: fade
mdc: true
fonts:
  sans: "Inter"
---

<div class="hero cover-grid">
  <div>
    <div class="kicker">Nova Knowledge | 15 min setup + live demo</div>
    <h1>From PM to<br/>AI Builder</h1>
  </div>
  <div class="cover-panel">
    <p class="subtitle">Deploy your first agent with Anthropic</p>
    <p class="byline">Andrés Santos Sanz<br/>Applied AI Manager<br/>Bit2Me<br/>ex-Revolut</p>
  </div>
</div>

<!--
Speaker notes:
Hi everyone, I am Andrés. Today I want to make agents feel less abstract and more buildable.
This is not a research talk and it is not a long tour of every AI concept. The goal is practical: set up the context quickly, then use Claude Managed Agents to show how a PM or operator can reason about a first agent.
The promise is simple: before the demo, I will give you just enough of a mental model to understand what we are building and why the managed-agent layer matters.
-->

---

# My story

<div class="profile-grid">
  <div class="profile-card accent">
    <strong>Now</strong>
    <span>Applied AI Manager at Bit2Me</span>
    <small>Agents, apps, workflows, and internal tools with domain experts.</small>
  </div>
  <div class="profile-card">
    <strong>Before</strong>
    <span>Revolut + Amazon</span>
    <small>Internal product development, data, and process improvement at Revolut; logistics data at Amazon.</small>
  </div>
  <div class="profile-card">
    <strong>Training</strong>
    <span>Industrial Organization Engineering + Computer Science</span>
    <small>Engineering background across operations, systems, and software.</small>
  </div>
</div>

<p class="takeaway">I am not approaching agents as research. I am approaching them as operating systems for teams.</p>

<!--
Speaker notes:
My perspective comes from operational work, not only from AI tooling.
At Bit2Me I work with teams and domain experts to turn repeated work into agents, apps, workflows, and internal tools. Before that, at Revolut I was close to internal product development, data, and process improvement across growth and CX operations. At Amazon I worked with logistics data and operational tooling.
My training also combines Industrial Organization and Computer Science, so I tend to look at AI systems from both sides: how work actually happens, and how software can make that work more reliable.
That is the lens I want you to keep for the rest of the session: an agent is valuable when it helps a team close a workflow loop.
-->

---

# What I want to cover before the demo

<div class="timeline">
  <div><span>01</span><strong>Why pilots fail</strong><small>The MIT/NANDA signal</small></div>
  <div><span>02</span><strong>How problems move</strong><small>The water-cycle analogy</small></div>
  <div><span>03</span><strong>Why now</strong><small>Deployment companies + managed platforms</small></div>
  <div><span>04</span><strong>Demo structure</strong><small>Claude Managed Agents</small></div>
</div>

<p class="note">The goal is to get to the demo quickly. The framework is just the map.</p>

<!--
Speaker notes:
Before jumping into the live demo, I want to cover four things.
First, why so many GenAI pilots are not becoming business impact. Second, a simple analogy for how problems move from mysterious to operational as we understand them better. Third, why the market is changing now through deployment companies and managed platforms. And finally, how the demo will be structured.
The point of this section is not to add theory for its own sake. It is to give you the map so the demo feels like a product system, not just a cool API call.
-->

---
class: dark
---

<div class="stat-slide">
  <div class="source-pill">MIT / NANDA, The GenAI Divide, August 2025</div>
  <h1>95%</h1>
  <h2>of enterprise GenAI pilots showed no measurable P&amp;L impact</h2>
  <p>The report is a deployment warning: adoption and demos are high, but value appears only when systems integrate into real workflows.</p>
</div>

<!--
Speaker notes:
In August 2025, MIT/NANDA published The GenAI Divide. The headline people remember is that 95% of enterprise GenAI pilots showed no measurable P&L impact.
I do not want to over-argue the exact number. The useful signal is the gap between experimentation and deployment. Many teams can create impressive demos, but far fewer can change daily work in a measurable way.
That tells us the bottleneck is not only model intelligence. It is workflow integration, ownership, evaluation, and the ability to keep improving after the first prototype.
So when we build an agent, the question is not just "does it answer?" The question is "does it fit into a loop where work can be delegated, inspected, corrected, and improved?"
-->

---
layout: center
class: water
---

# The water-cycle analogy

<div class="water-steps">
  <div><b>Chaotic</b><span>Rain as mystery</span></div>
  <div><b>Complex</b><span>Patterns observed</span></div>
  <div><b>Complicated</b><span>Hydrology + meteorology</span></div>
  <div><b>Clear</b><span>Primary-school science</span></div>
</div>

<p class="center-copy">The phenomenon did not change. Our model of it changed.</p>

<!--
Speaker notes:
The water cycle is a useful analogy because the underlying phenomenon did not change. Rain, drought, clouds, evaporation, and rivers were always there.
What changed was our model of the system. Something that could once feel chaotic became observable. Then it became a subject for experts. Eventually, the basic version became clear enough to teach in primary school.
This is the transition I want to connect to agents. The work can still be complex, but as we develop better patterns, platforms, and operating models, more of that complexity becomes teachable and repeatable.
That does not mean every problem becomes simple. It means we can move some responsibilities out of improvisation and into better-designed systems.
-->

---

# Agents are becoming easier to operate

Not because the work became trivial, but because the stack is absorbing repeated decisions:

<div class="domain-grid">
  <div><b>Then</b><span>Custom loop, fragile tools, ad hoc memory, unclear runtime, separate inspection.</span></div>
  <div><b>Now</b><span>Stronger models, tool standards, hosted environments, event streams, reusable skills.</span></div>
  <div><b>Product shift</b><span>The PM question moves from "can it act?" to "what work should it own, under what constraints?"</span></div>
</div>

<p class="source">Concept reference: Anthropic, "Building effective agents" - workflows are predictable paths; agents decide process and tool use dynamically.</p>

<!--
Speaker notes:
Early agent projects were difficult because teams had to make many low-level decisions at once. You had to design the loop, connect tools, manage state, define memory, handle runtime, inspect events, and decide how to recover when something failed.
The shift now is that more of those repeated decisions are becoming part of the stack. Models are better at tool use, tools are becoming more standardized, hosted environments are available, and event streams make the loop easier to inspect.
For PMs, that changes the product question. The interesting question is less "can an agent act at all?" and more "what job should this agent own, what boundaries does it need, and how will we know if it is doing good work?"
-->

---
class: split-dark
---

# Two ways the market is reducing complexity

<div class="two-paths">
  <div>
    <span>Path 1</span>
    <h2>Deployment companies</h2>
    <p>OpenAI and Anthropic are moving closer to implementation because enterprise AI depends on context, workflow redesign, and adoption.</p>
    <small>Examples: Anthropic's enterprise AI services company and OpenAI's Deployment Company.</small>
  </div>
  <div>
    <span>Path 2</span>
    <h2>Managed platforms</h2>
    <p>Managed agent stacks collapse model, environment, tools, sessions, and events into one surface.</p>
    <small>Examples: Claude Managed Agents and Gemini Managed Agents.</small>
  </div>
</div>

<!--
Speaker notes:
The market is reducing complexity in two complementary ways.
The first path is deployment companies. OpenAI and Anthropic are both moving closer to implementation because enterprise AI is contextual. The hard part is often understanding the workflow, redesigning it, and helping teams adopt the system.
The second path is managed platforms. Instead of every team assembling the model, runtime, tools, session state, and event handling from scratch, managed platforms package more of that into a coherent product surface.
Today we are using the second path. The demo is about showing how a managed-agent product changes the builder experience.
-->

---

# What changes with managed agents

Claude Managed Agents packages the harness and infrastructure around a full execution loop:

<div class="stack-list">
  <div><b>Agent</b><span>model, system prompt, tools, MCP servers, and skills</span></div>
  <div><b>Environment</b><span>cloud sandbox or self-hosted sandbox configuration</span></div>
  <div><b>Session</b><span>a running agent instance for a specific task</span></div>
  <div><b>Events</b><span>user turns, tool results, status updates, and streamed responses</span></div>
  <div><b>State</b><span>persistent history, files, sandbox state, and outputs server-side</span></div>
</div>

<p class="source">Source: Claude Managed Agents overview, official Anthropic documentation.</p>

<!--
Speaker notes:
Claude Managed Agents is useful for this talk because it gives us a concrete vocabulary for the execution loop.
An agent is not just a prompt. In the official documentation, the agent includes the model, system prompt, tools, MCP servers, and skills. The environment defines where the work runs. A session is a running instance of the agent for a specific task. Events are the observable messages, tool results, status updates, and streamed responses.
The important product idea is observability. If we can see the loop, we can review the work, understand failures, and improve the agent contract.
That is why managed agents matter for PMs: they make the system easier to reason about as a workflow, not just as a chat interaction.
-->

---
class: demo-map
---

# Demo structure

<div class="demo-flow">
  <div><span>1</span><b>Create</b><small>agent + instructions</small></div>
  <div><span>2</span><b>Run</b><small>session + events</small></div>
  <div><span>3</span><b>Inspect</b><small>tools + memo</small></div>
  <div><span>4</span><b>Improve</b><small>constraints + output</small></div>
</div>

<div class="demo-card">
  <h2>Investment committee simulator</h2>
  <p>Educational analysis only. No personal financial advice. No buy/sell/hold recommendation.</p>
</div>

<!--
Speaker notes:
This is the structure of the demo.
First, we create the agent and define the job. Second, we run a session and watch the events. Third, we inspect what happened: tools, intermediate behavior, and the memo. Fourth, we improve the constraints or instructions based on what we observe.
The example is an investment committee simulator, but it is educational only. It is not financial advice and it is not a buy, sell, or hold recommendation.
As you watch the demo, focus less on the domain and more on the pattern: define the job, run the loop, inspect the output, then improve the system.
-->

---

# References

<div class="ref-groups">
  <div>
    <h2>Market signal</h2>
    <a href="https://www.artificialintelligence-news.com/wp-content/uploads/2025/08/ai_report_2025.pdf">MIT/NANDA - The GenAI Divide, August 2025</a>
    <a href="https://www.anthropic.com/news/enterprise-ai-services-company">Anthropic - Enterprise AI services company</a>
    <a href="https://openai.com/index/openai-launches-the-deployment-company/">OpenAI - Deployment Company</a>
  </div>
  <div>
    <h2>Agent concepts</h2>
    <a href="https://www.anthropic.com/engineering/building-effective-agents">Anthropic - Building effective agents</a>
    <a href="https://cynefin.io/index.php/Cynefin">Cynefin framework</a>
  </div>
  <div>
    <h2>Managed platforms</h2>
    <a href="https://platform.claude.com/docs/en/managed-agents/overview">Claude Managed Agents</a>
    <a href="https://ai.google.dev/gemini-api/docs/custom-agents">Gemini API - Building Managed Agents</a>
    <a href="https://github.com/anthropics/cwc-workshops/tree/main">Anthropic - Code with Claude workshops</a>
  </div>
</div>

<!--
Speaker notes:
These are the references behind the framing and the demo.
The MIT/NANDA report is the market signal for why pilots and business impact are not the same thing. The Anthropic and OpenAI deployment-company announcements support the point that frontier labs are moving closer to implementation. The agent-concepts references explain the distinction between workflows and agents, and the managed-platform references are the product surfaces behind the demo.
If someone wants to go deeper after the session, start with the Claude Managed Agents overview and the Anthropic Code with Claude workshops.
-->
