# Agents for PM Nova

Markdown-first talk materials for **From PM to AI Builder: Deploy Your First Agent with Anthropic**, a Nova online session for PMs and operators who want to understand when and how to build useful AI agents.

## What Is In This Repo

- [slides.md](./slides.md): Slidev presentation source.
- [docs/storyline.md](./docs/storyline.md): 60-minute narrative, timing, and transitions.
- [docs/speaker-profile.md](./docs/speaker-profile.md): speaker bio and intro variants.
- [docs/research.md](./docs/research.md): sourced claims and reference notes.
- [docs/demo-script.md](./docs/demo-script.md): Claude Managed Agents demo runbook and fallback.
- [docs/handout.md](./docs/handout.md): attendee checklist and takeaways.

All primary talk artifacts are Markdown. Generated exports such as PDFs should be treated as build outputs, not source of truth.

## Presentation Runtime

The deck uses [Slidev](https://sli.dev/guide/) because it keeps slides in Markdown while supporting:

- presenter mode and speaker notes;
- Mermaid diagrams directly in Markdown;
- live drawing and annotation;
- web preview and static build;
- PDF export.

## Setup

```bash
npm install
```

## Commands

```bash
npm run dev
npm run build
npm run export
```

`npm run dev` opens the deck locally. `npm run build` validates the Slidev site. `npm run export` creates a PDF if the required browser dependencies are available.

## Talk Thesis

Most AI pilots do not fail because the model is not magical enough. They fail because teams pick the wrong problem shape, underestimate workflow integration, and leave the system without a closed loop for learning and correction.

The talk moves through four ideas:

1. The 95% GenAI pilot failure claim from the 2025 MIT/NANDA report.
2. Cynefin as a practical way to diagnose complexity before choosing tools.
3. The two market responses: expert deployment services and simpler managed agent platforms.
4. Claude Managed Agents as a practical demo path for PMs.

## Demo Positioning

The demo is an educational investment-analysis workflow framed as an **investment committee simulator**, not financial advice. It demonstrates agent behavior, tool use, session state, and structured outputs without making buy/sell recommendations.

## Safety And Privacy

Do not commit API keys, credentials, browser data, cookies, or private LinkedIn exports. Speaker-profile facts are based only on the supplied PDF profile export and should be reviewed before public use.
