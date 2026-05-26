# PM Checklist For Agent Opportunities

Use this checklist before turning an AI idea into an agent project.

## 1. Diagnose The Problem Shape

Ask:

- Is the work clear, complicated, complex, or chaotic?
- Do we already know the path from input to output?
- Does the task need runtime judgment, or just a reliable workflow?
- Are failures easy to detect?

Rule of thumb:

- Clear work can often be automated with rules.
- Complicated work needs expert-designed workflows.
- Complex work may need experiments and agentic behavior.
- Chaotic work needs stabilization before automation.

## 2. Decide: Workflow Or Agent?

Use a workflow when:

- the steps are known;
- the output shape is stable;
- deterministic behavior matters;
- exceptions are rare.

Use an agent when:

- the path depends on what it discovers;
- the task requires tool choice;
- the work involves synthesis and judgment;
- the agent can expose uncertainty;
- there is a human review loop.

## 3. Define The Agent Contract

Before building, write:

- the job the agent owns;
- the decisions it can make;
- the decisions it cannot make;
- the tools it can use;
- the data it can access;
- the output format;
- the human approval point;
- the success metric.

## 4. Require Reviewable Outputs

Good agent outputs should separate:

- facts;
- assumptions;
- reasoning;
- uncertainty;
- next actions;
- missing evidence.

If a human cannot review the output, the workflow is not ready.

## 5. Build A Closed Loop

The system should be able to:

1. Receive a task.
2. Plan.
3. Act with tools.
4. Inspect results.
5. Correct mistakes.
6. Produce a structured output.
7. Feed learning into the next iteration.

No loop, no product.

## 6. Choose The Platform By Complexity Removed

The best platform is not the one with the most features. It is the one that removes the most accidental complexity from your team.

Look for:

- session state;
- tool execution;
- environment management;
- streaming events;
- output inspection;
- eval and monitoring paths;
- easy iteration.

## 7. Useful First Agent Projects

Good first candidates:

- structured research synthesis;
- support triage with human approval;
- internal operations copilots;
- QA over internal procedures;
- recurring reporting with evidence links;
- codebase analysis with tests and validation.

Avoid as first projects:

- high-risk autonomous decisions;
- unclear ownership;
- tasks with no review path;
- workflows where data access is not solved;
- broad "company assistant" concepts.

## Final Takeaway

Do not start with "we need an agent."

Start with:

> What loop in this workflow is repetitive, judgment-heavy, and reviewable enough for an agent to help?
