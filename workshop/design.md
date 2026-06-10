---
version: alpha
name: restrained-gallery-interface
description: A photography-first, low-chrome interface for a conservative portfolio product. Full-width sections alternate light, parchment, and near-black canvases. Typography is calm and precise, UI controls are minimal, and a single blue accent identifies interactive elements. The product experience should feel premium, quiet, and operational rather than promotional.

colors:
  primary: "#0066cc"
  primary-focus: "#0071e3"
  primary-on-dark: "#2997ff"
  ink: "#1d1d1f"
  body: "#1d1d1f"
  body-on-dark: "#ffffff"
  body-muted: "#cccccc"
  ink-muted-80: "#333333"
  ink-muted-48: "#7a7a7a"
  divider-soft: "#f0f0f0"
  hairline: "#e0e0e0"
  canvas: "#ffffff"
  canvas-parchment: "#f5f5f7"
  surface-pearl: "#fafafc"
  surface-tile-1: "#272729"
  surface-tile-2: "#2a2a2c"
  surface-tile-3: "#252527"
  surface-black: "#000000"
  surface-chip-translucent: "#d2d2d7"
  on-primary: "#ffffff"
  on-dark: "#ffffff"

typography:
  hero-display:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 56px
    fontWeight: 600
    lineHeight: 1.07
    letterSpacing: 0
  display-lg:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 40px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: 0
  display-md:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 34px
    fontWeight: 600
    lineHeight: 1.24
    letterSpacing: 0
  lead:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 24px
    fontWeight: 400
    lineHeight: 1.35
    letterSpacing: 0
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 17px
    fontWeight: 400
    lineHeight: 1.47
    letterSpacing: 0
  body-strong:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 17px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: 0
  caption:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.43
    letterSpacing: 0
  caption-strong:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.29
    letterSpacing: 0
  fine-print:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.35
    letterSpacing: 0
  nav-link:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1
    letterSpacing: 0

rounded:
  none: 0px
  xs: 5px
  sm: 8px
  md: 11px
  lg: 18px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 17px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 80px

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: 11px 22px
  button-secondary-pill:
    backgroundColor: transparent
    textColor: "{colors.primary}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: 11px 22px
    border: "1px solid {colors.primary}"
  button-dark-utility:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-dark}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: 8px 15px
  button-icon-circular:
    backgroundColor: "{colors.surface-chip-translucent}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    size: 44px
  text-link:
    backgroundColor: transparent
    textColor: "{colors.primary}"
    typography: "{typography.body}"
  text-link-on-dark:
    backgroundColor: transparent
    textColor: "{colors.primary-on-dark}"
    typography: "{typography.body}"
  global-nav:
    backgroundColor: "{colors.surface-black}"
    textColor: "{colors.on-dark}"
    typography: "{typography.nav-link}"
    height: 44px
  sub-nav-frosted:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink}"
    typography: "{typography.caption-strong}"
    height: 52px
  tile-light:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.display-lg}"
    rounded: "{rounded.none}"
    padding: 80px
  tile-parchment:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink}"
    typography: "{typography.display-lg}"
    rounded: "{rounded.none}"
    padding: 80px
  tile-dark:
    backgroundColor: "{colors.surface-tile-1}"
    textColor: "{colors.on-dark}"
    typography: "{typography.display-lg}"
    rounded: "{rounded.none}"
    padding: 80px
  utility-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.lg}"
    padding: 24px
    border: "1px solid {colors.hairline}"
  option-chip:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: 12px 16px
  option-chip-selected:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    border: "2px solid {colors.primary-focus}"
  search-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: 12px 20px
    height: 44px
  floating-sticky-bar:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    height: 64px
    padding: 12px 32px
  footer:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink-muted-80}"
    typography: "{typography.fine-print}"
    padding: 64px
---

## Overview

This design system is a restrained, photography-first interface for a serious
financial product. The UI should feel quiet, premium, and focused on the
portfolio state. It must not feel like a marketing page, a trading game, or a
decorative dashboard.

The interface is built from full-width surfaces, precise typography, minimal
chrome, and one blue action color. Product imagery, market imagery, or clean
data visualizations may carry the visual weight. Controls should recede until
the user needs to act.

## Core Principles

- Use one interactive accent color: `#0066cc`.
- Use white, parchment, and near-black surfaces to create section rhythm.
- Keep UI chrome minimal: no decorative gradients, no bokeh, no ornamental
  shapes, and no shadows on cards or controls.
- Use shadows only for meaningful media or product imagery that needs visual
  grounding.
- Prefer full-width bands and unframed layouts over nested cards.
- Use cards only for repeated items, modals, and genuinely framed tools.
- Keep controls dense, legible, and operational.
- Make safety, confidence, source freshness, and blocked states visible.
- Avoid promotional copy. The first screen should be the actual product
  experience.

## Product Fit

The target app is a conservative portfolio manager. The first screen should show
the working portfolio experience:

- risk profile slider when no profile exists;
- target allocation and cash allocation;
- active and blocked assets;
- research freshness and source coverage;
- risk constraints and validation status;
- agent workflow and event logs;
- clear confirmation states before any exchange-changing action.

## Color Use

`primary` is the only action color. It is used for links, primary buttons,
selected controls, focus rings, and key interactive affordances.

Light surfaces use `ink` for text and `primary` for actions. Dark surfaces use
white text and `primary-on-dark` for links. Parchment surfaces provide soft
separation without adding borders or decoration.

Avoid introducing additional accent colors. If status colors are needed, keep
them subtle and secondary to text labels such as `validated`, `blocked`, or
`pending_approval`.

## Typography

Use system UI fonts with Inter as the preferred open-source face. Keep
letter-spacing at `0` across the system.

Headlines use weight `600`, body text uses `400`, and emphasis uses `600`.
Avoid heavy weights for normal UI. Body copy should usually be 17px with
comfortable line-height.

Use display sizes only for true top-level views. Compact panels, allocation
rows, tables, and sidebars should use smaller headings that fit their available
space.

## Layout

Use an 8px spacing rhythm. Full-width sections can use 80px vertical padding on
desktop and tighter spacing on mobile.

Recommended layout:

- top navigation at 44px height;
- optional frosted sub-navigation at 52px height;
- main portfolio workspace in full-width bands;
- constrained inner content for readable tables and controls;
- no cards inside cards;
- stable dimensions for allocation rows, charts, sliders, and icon buttons.

## Components

Primary actions use blue pill buttons. Secondary actions can use text links,
ghost pills, or compact utility buttons depending on density.

Inputs should be rounded pills or compact controls with clear labels. Use a
slider for the initial risk-profile question and avoid adding extra onboarding
questions.

Asset rows should show canonical market ID, display label, category, active or
blocked state, source freshness, target allocation, and validation result.

Logs and agent traces should be readable, dense, and placed where operators can
inspect them without interrupting the portfolio workflow.

## Motion And Interaction

Use restrained micro-interactions. Buttons may scale to `0.95` on active press.
Focus states must be visible. Avoid decorative animation.

If live market data updates, preserve layout stability. Dynamic numbers should
not resize rows, buttons, charts, or controls.

## Responsive Behavior

On mobile, reduce section padding, stack portfolio panels, keep the risk slider
usable, and preserve the allocation table as a readable card or row list.

On desktop, use side-by-side views for target allocation, current allocation,
research sources, and validation. Keep the primary workflow visible without
requiring a marketing-style hero section.

## Do

- Use a calm, premium, low-chrome interface.
- Use full-width light, parchment, and dark bands for rhythm.
- Keep the portfolio and risk state visible above secondary content.
- Use one blue action color consistently.
- Use readable data tables, sliders, segmented controls, toggles, and compact
  buttons.
- Show blocked states and safety constraints plainly.

## Do Not

- Do not include brand references, product references, or brand-specific copy.
- Do not create a landing page.
- Do not use decorative gradients, orbs, bokeh, or ornamental illustrations.
- Do not add shadows to cards, buttons, text, or navigation.
- Do not nest cards inside cards.
- Do not use oversized hero typography inside compact portfolio panels.
- Do not let dynamic text overlap, resize controls, or break the layout.
