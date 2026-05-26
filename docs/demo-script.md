# Claude Managed Agents Demo Script

## Demo Goal

Build and run an educational **investment committee simulator** using Claude Managed Agents.

The demo should show PMs how to think about an agent as a product surface:

- job definition;
- context and constraints;
- tools and environment;
- session loop;
- reviewable output;
- next iteration.

## Safety Framing

Say this before the demo:

> This is an educational analysis assistant. It is not financial advice, and it will not produce buy, sell, or hold recommendations. The output is a structured memo that highlights evidence, assumptions, risks, and open questions.

## Demo Story

The agent simulates a lightweight investment committee. It reviews a company through multiple reasoning lenses and produces a memo that a human can challenge.

Suggested prompt:

```text
Analyze MercadoLibre as if preparing an educational investment committee memo.

Do not provide financial advice or a buy/sell/hold recommendation.
Focus on business quality, growth drivers, risks, missing evidence, and follow-up questions.
Use the available files and tools. If evidence is missing, say so clearly.
Return a structured memo with:
1. Executive summary
2. Business model
3. Bull case
4. Bear case
5. Key risks
6. Evidence gaps
7. Next research questions
```

## Live Flow

### 1. Explain The Product Boundary

Before touching the API, state the agent contract:

- It owns analysis synthesis.
- It does not own investment decisions.
- It can inspect provided context.
- It must expose uncertainty.
- It must produce a reviewable memo.

### 2. Create Or Select The Agent

Show the concept, not every line:

- name: `investment-committee-simulator`;
- instruction: educational analysis only;
- tools/environment: file access or controlled research context;
- output: structured memo.

### 3. Start A Session

Explain that the session is the working loop. It is where the agent receives a task, acts, and returns events.

### 4. Stream Events

Point out what PMs should watch:

- planning behavior;
- tool calls;
- evidence gathering;
- uncertainty handling;
- whether the output follows the required shape.

### 5. Inspect The Memo

Use the output to discuss product acceptance criteria:

- Did it answer the task?
- Did it show evidence?
- Did it separate facts from assumptions?
- Did it avoid financial advice?
- Are the next research questions useful?

### 6. Iterate

Improve one thing live:

- stricter output schema;
- better risk section;
- more explicit evidence gaps;
- shorter executive summary;
- clearer disclaimer.

The point is to show the closed loop.

## Fallback Plan

If the live API or network fails, switch to the prepared transcript:

1. Show the agent definition conceptually.
2. Show a saved event stream excerpt.
3. Show the final memo.
4. Ask the audience to critique the output.
5. Improve the instruction live in Markdown.

Fallback line:

> The implementation detail failed, which is exactly why the product loop matters. We can still inspect the agent contract, the events we expected, and the output quality.

## Expected Output Shape

```markdown
# Investment Committee Memo

## Executive Summary

Short, neutral summary of the company and analysis stance.

## Business Model

How the company creates and captures value.

## Bull Case

The strongest evidence-backed positive view.

## Bear Case

The strongest evidence-backed negative view.

## Key Risks

Operational, financial, regulatory, competitive, and execution risks.

## Evidence Gaps

What the agent could not verify from the available context.

## Next Research Questions

Concrete questions a human analyst should answer next.
```

## PM Debrief

After the demo, ask:

- Was this agent specialized enough?
- Did it know what not to do?
- Was the output reviewable?
- Where would you put human approval?
- What workflow would this plug into?
- What would you measure after deployment?

## Rehearsal Checklist

- Confirm Claude Managed Agents beta access.
- Confirm API key exists locally but is not committed.
- Confirm no secrets appear in terminal history screenshots.
- Prepare sample company context file if live web research is unavailable.
- Prepare a saved output memo.
- Run through the fallback path once.
