# Storyline

## Talk Shape

**Title:** From PM to AI Builder: Deploy Your First Agent with Anthropic  
**Audience:** PMs and operators who are curious about AI but do not need to be expert engineers.  
**Language:** English.  
**Duration:** 60 minutes.

The talk should feel practical and fast. The theory exists only to help the audience make better product decisions before seeing the demo.

## Core Message

Most AI pilots do not fail because the model is not intelligent enough. They fail because teams misunderstand the shape of the problem, underestimate workflow integration, and do not create closed loops for learning, execution, and correction.

## Narrative Arc

### 1. Hook: The 95% Problem

Open with the 2025 MIT/NANDA claim that 95% of enterprise GenAI pilots were not producing visible returns. Use it as a signal that the industry has moved past experimentation and into deployment quality.

Transition:

> If almost everyone can create impressive demos, but almost nobody gets business impact, the bottleneck is not access to models. The bottleneck is turning messy work into reliable systems.

### 2. Diagnose Before Building

Introduce Cynefin as a product-thinking tool, not as an academic framework. The audience should leave with one behavior: before asking "what agent should we build?", ask "what kind of problem are we dealing with?"

Use the water-cycle analogy:

- At one point, rain and drought could feel chaotic and mystical.
- Over time, people observed patterns.
- Science made the system complicated but explainable by experts.
- Today, the basic water cycle is clear enough for primary school.

Transition:

> The work did not become simpler because nature changed. It became simpler because we learned how to observe, model, and teach it. Agents are going through a similar transition.

### 3. Why Early Agent Projects Were Hard

Explain that early agent systems sat in a complex or chaotic domain:

- models had weaker planning and tool-use ability;
- orchestration was custom;
- memory and session state were ad hoc;
- tools were fragile;
- evals and monitoring were separate;
- teams used generic assistants where specialized agents were needed.

Transition:

> The industry is responding in two directions: bring in specialists, or make the platform simple enough that more builders can operate safely.

### 4. Two Industry Responses

First response: expert deployment services. OpenAI and Anthropic are moving closer to enterprise implementation because large companies have contextual complexity that generic products cannot remove by themselves.

Second response: managed platforms. Claude Managed Agents is an example of stack simplification: agent definition, environment, session, event stream, tool execution, and output handling become one coherent product surface.

Transition:

> Today we are going to use the second path. We will use a managed platform to build something that would have required a much more fragmented stack not long ago.

### 5. Speaker Context

Keep this to 2-3 minutes.

Positioning:

> I build practical AI systems with operational teams: agents, apps, workflows, and internal tools. At Bit2Me I co-create AI solutions with domain experts. Before that, I worked across growth analytics and CX operations at Revolut, logistics at Amazon, and industrial operations.

The credibility point is not "I do AI." It is "I have spent years turning operational problems into data, automation, and product systems."

### 6. Demo

Frame the demo as an educational investment committee simulator. It should not be positioned as financial advice.

The audience should watch for:

- how the job is scoped;
- what the agent can and cannot do;
- where evidence enters the system;
- how output quality is made reviewable;
- how the next iteration becomes obvious.

### 7. Closed-Loop Behavior

Close the conceptual loop by connecting the demo to coding agents.

The key line:

> The productivity jump comes when the agent can close the loop: plan, act, run, inspect, and fix.

For PMs, the equivalent loop is:

business need -> agent hypothesis -> prototype -> evaluation -> workflow integration -> monitoring -> next iteration.

## Timing

| Segment | Time | Goal |
| --- | ---: | --- |
| Opening and 95% problem | 5 min | Establish urgency |
| Cynefin and water-cycle analogy | 10 min | Give a diagnosis framework |
| Why agents used to be hard | 8 min | Explain historical complexity |
| Two industry responses | 7 min | Set up Claude Managed Agents |
| Speaker context | 3 min | Build credibility quickly |
| Demo | 20 min | Show the build loop |
| Closed-loop takeaway and Q&A | 7 min | Convert demo into PM behavior |

## Key Transitions

- From 95% failure to Cynefin:
  > The failure rate tells us that many teams are building before diagnosing.

- From water cycle to agents:
  > The same thing happens in technology: once we understand the system, what looked chaotic becomes teachable.

- From consulting to managed platforms:
  > One path is to bring experts into the mess. The other is to make the stack small enough that more teams can build correctly.

- From demo to takeaway:
  > The point is not that everyone should build this exact agent. The point is that you can now reason about agent systems as products.
