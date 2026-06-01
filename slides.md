---
theme: default
title: "From PM to AI Builder"
info: |
  Nova talk: From PM to AI Builder: Deploy Your First Agent with Anthropic.
  Speaker: Andres Santos Sanz.
author: "Andres Santos Sanz"
class: text-left
drawings:
  enabled: true
  persist: false
transition: fade
mdc: true
fonts:
  sans: "Inter"
---

<div class="hero">
  <div class="kicker">Nova Knowledge | 15 min setup + live demo</div>
  <h1>From PM to<br/>AI Builder</h1>
  <p class="subtitle">Deploy your first agent with Anthropic</p>
  <p class="byline">Andres Santos Sanz | Applied AI Lead at Bit2Me | ex-Revolut</p>
</div>

<!--
Set the contract immediately: the talk is short and practical. Theory is only here to make the demo easier to understand.
-->

---

# What I want to cover before the demo

<div class="timeline">
  <div><span>01</span><strong>Why pilots fail</strong><small>The 95% problem</small></div>
  <div><span>02</span><strong>How to diagnose</strong><small>Cynefin + water cycle</small></div>
  <div><span>03</span><strong>Why now</strong><small>Services + managed platforms</small></div>
  <div><span>04</span><strong>Demo structure</strong><small>Claude Managed Agents</small></div>
</div>

<p class="note">The goal is to get to the demo quickly. The framework is just the map.</p>

<!--
Keep this under one minute. It tells the audience that this will not be a long theory lecture.
-->

---
class: dark
---

<div class="stat-slide">
  <div class="source-pill">MIT / NANDA, State of AI in Business 2025</div>
  <h1>95%</h1>
  <h2>of GenAI pilots showed no visible return</h2>
  <p>That is not only a model problem. It is a deployment, workflow, and complexity problem.</p>
</div>

<!--
Do not spend time defending the exact number. Use it as the starting tension: demos are easy, deployed impact is hard.
-->

---

# My lens on this problem

<div class="profile-grid">
  <div class="profile-card accent">
    <strong>Now</strong>
    <span>Applied AI Lead at Bit2Me</span>
    <small>Agents, apps, workflows, and internal tools with domain experts.</small>
  </div>
  <div class="profile-card">
    <strong>Before</strong>
    <span>Revolut, Amazon, industrial operations</span>
    <small>Growth analytics, CX operations, logistics, process improvement.</small>
  </div>
  <div class="profile-card">
    <strong>Pattern</strong>
    <span>AI succeeds when it closes a loop</span>
    <small>Observe, act, inspect, correct, and improve the workflow.</small>
  </div>
</div>

<p class="takeaway">I am not approaching agents as research. I am approaching them as operating systems for teams.</p>

---
class: framed
---

# Diagnose before building

```mermaid
flowchart TB
  center(("Disorder<br/>what kind of problem is this?"))
  chaotic["Chaotic<br/>act first<br/>stabilize"]
  complex["Complex<br/>probe<br/>learn by experiment"]
  complicated["Complicated<br/>analyze<br/>use expertise"]
  clear["Clear<br/>categorize<br/>automate rules"]

  center --- chaotic
  center --- complex
  center --- complicated
  center --- clear
```

<div class="callout">Most failed agent projects start by choosing tools before diagnosing the problem shape.</div>

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
Use the "chamanes" example carefully: the point is not to mock early explanations, but to show how knowledge moves problems across domains.
-->

---

# Agents are moving domains too

Early agents were difficult because every layer was separate:

- weaker models;
- brittle tools;
- ad hoc memory;
- custom orchestration;
- fragile evals;
- unclear deployment path.

<p class="source">Concept reference: Anthropic, "Building effective agents" - augmented LLM.</p>

<!--
This image comes from the Anthropic reference. Use it to show that an agent is already a system, not a chat box.
-->

---
class: split-dark
---

# Two ways the market is reducing complexity

<div class="two-paths">
  <div>
    <span>Path 1</span>
    <h2>Expert deployment</h2>
    <p>OpenAI and Anthropic are moving closer to implementation because enterprise AI is contextual.</p>
    <small>Think: specialists working inside the workflow.</small>
  </div>
  <div>
    <span>Path 2</span>
    <h2>Managed platforms</h2>
    <p>Managed agent stacks collapse model, environment, tools, sessions, and events into one surface.</p>
    <small>Think: fewer moving parts for builders.</small>
  </div>
</div>

---

# What changes with managed agents

Claude Managed Agents lets us talk about a full execution loop:

<div class="stack-list">
  <div><b>Agent</b><span>role, instructions, boundaries</span></div>
  <div><b>Environment</b><span>where work happens</span></div>
  <div><b>Session</b><span>the running loop</span></div>
  <div><b>Events</b><span>observable progress</span></div>
  <div><b>Output</b><span>reviewable artifact</span></div>
</div>

<p class="source">Concept reference: Anthropic, autonomous agent loop.</p>

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
This is the last theory slide. After this, switch to terminal/browser demo.
-->

---

<div class="loop-card">
  <strong>Reference mental model</strong>
  <span>Coding agents work because they can close the loop against ground truth: edit, run, test, inspect, fix.</span>
</div>

---
layout: section
class: demo-section
---

# Live demo

## Claude Managed Agents

Create -> Run -> Inspect -> Improve

---

# What PMs should watch for

<div class="watch-grid">
  <div><b>Scope</b><span>What job does the agent own?</span></div>
  <div><b>Boundaries</b><span>What is it forbidden to do?</span></div>
  <div><b>Evidence</b><span>Where does context enter?</span></div>
  <div><b>Observability</b><span>Can we inspect the loop?</span></div>
  <div><b>Output</b><span>Can a human review it?</span></div>
  <div><b>Iteration</b><span>What do we improve next?</span></div>
</div>

---

# Steering the workshop

<div class="steer-grid">
  <div><b>Ship first</b><span>Keep the build linear: agent, environment, session, events, output.</span></div>
  <div><b>Then harden</b><span>Ask what changes before this becomes production: confirmations, outcomes, evals, monitoring.</span></div>
  <div><b>Decompose</b><span>Move responsibilities into tools, skills, or subagents instead of growing one large prompt.</span></div>
</div>

<p class="takeaway">The room should leave with a product habit: inspect the loop before trusting the agent.</p>

<!--
Use the Anthropic workshops as the backbone: Ship Your First Managed Agent for the linear build, Production-ready Agent for deployment concerns, and Agent Decomposition for the "tool, skill, or subagent?" discussion.
-->

---

# Fallback if the live demo fails

1. Show the agent contract.
2. Show the expected event stream.
3. Show the generated memo.
4. Ask the room to critique the output.
5. Improve the instruction live.

<div class="callout">A demo failure is still a product lesson: robust systems need visible loops and fallback paths.</div>

---

# Final takeaway

<div class="closing">
  <h2>Do not start with "we need an agent."</h2>
  <p>Start with the loop: what repetitive, judgment-heavy, reviewable workflow can the agent improve?</p>
</div>

<div class="mini-checklist">
  <span>Diagnose</span>
  <span>Constrain</span>
  <span>Run</span>
  <span>Inspect</span>
  <span>Improve</span>
</div>

---

# References

<div class="refs">
  <a href="https://www.artificialintelligence-news.com/wp-content/uploads/2025/08/ai_report_2025.pdf">MIT/NANDA - The GenAI Divide</a>
  <a href="https://cynefin.io/index.php/Cynefin">Cynefin framework</a>
  <a href="https://www.anthropic.com/engineering/building-effective-agents">Anthropic - Building effective agents</a>
  <a href="https://www.anthropic.com/news/enterprise-ai-services-company">Anthropic - Enterprise AI services company</a>
  <a href="https://openai.com/index/openai-launches-the-deployment-company/">OpenAI - Deployment Company</a>
  <a href="https://platform.claude.com/docs/en/agents-and-tools/managed-agents/overview">Claude Managed Agents</a>
  <a href="https://youtu.be/19HDQ9HppOA">Claude - Ship your first Managed Agent</a>
  <a href="https://youtu.be/jWWsLe4Gh5Y">Claude - Production-ready agent</a>
  <a href="https://youtu.be/mWvtOHlZM-I">Claude - Tool, skill, or subagent?</a>
  <a href="https://github.com/anthropics/cwc-workshops/tree/main">Anthropic - Code with Claude workshops</a>
</div>
