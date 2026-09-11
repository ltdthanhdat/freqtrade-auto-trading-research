# Strategy Research Control Room

Derived from OpenDesign's `mission-control` design system for the automated
strategy research dashboard.

## Direction

- Dark, information-dense operations console.
- Research evidence is primary; profit is never shown without stressed OOS and
  drawdown context.
- Color communicates state only. No gradients, glass effects, or decorative
  trading imagery.
- Corners are square or at most 4px. Panels use borders instead of shadows.

## Tokens

| Token | Value | Role |
|---|---|---|
| `--bg-default` | `#0B1120` | Page canvas |
| `--bg-surface` | `#111827` | Panels |
| `--bg-hover` | `#1A2535` | Interactive hover |
| `--border` | `#1E3A5F` | Panel boundaries |
| `--border-subtle` | `#162035` | Internal dividers |
| `--primary` | `#FFB800` | Key research telemetry |
| `--active` | `#00D4FF` | Current/selected state |
| `--success` | `#26DE81` | Passed gate |
| `--warning` | `#FF9F43` | Review/inconclusive |
| `--danger` | `#FF4757` | Failed gate |
| `--text` | `#E8F0FE` | Primary copy |
| `--text-muted` | `#8BA3C7` | Labels and supporting copy |
| `--text-faint` | `#6B83A5` | Non-critical metadata |

## Typography and spacing

- UI copy: Inter/system sans-serif.
- Numeric values, hashes, timestamps, and metrics: JetBrains Mono/system
  monospace.
- 4px baseline grid; 16px standard panel padding; 24px primary section gap.
- Labels are 10-12px uppercase with tracking. Body copy is 13-14px.

## Components

- Status badges combine color with a text label or symbol.
- KPI tiles show a label, tabular value, and factual qualifier.
- Tables keep headers visible and use aligned tabular numbers.
- Charts use labeled axes and never rely on color alone.
- Cycle history exposes append-only events, retries, window identity and review
  state; it does not expose trading start/stop controls.
- Dry-run eligibility is shown only after the SQLite hypothesis state, candidate
  hash, untouched holdout, WFO and runtime decay lock all agree.
- Focus-visible outlines use `--active` at 2px.

## Responsive and motion

- At less than 980px, hide the sidebar and stack main panels.
- At less than 640px, use one KPI column and allow tables to scroll.
- Disable transitions and animation under `prefers-reduced-motion`.
