# car-buying-advisor

[中文](./README.md) | **English**

> An **Agent Skill** that turns a car model name into a **verifiable, cross-channel purchase comparison report**.
> Covers every new-car and used-car sales channel, with every price, source, contact detail, mileage figure and
> condition claim tagged with an **evidence grade and a citation**.

[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-4B5563)](https://agentskills.io/specification)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Language](https://img.shields.io/badge/lang-zh--CN%20%7C%20en-blue)](./README.md)

---

## The problem it solves

When buying a car, the hard part is not *finding* a price — it is **deciding whether that price can be trusted**.
For the same vehicle, a franchised dealer quote, a platform listing and an actual owner's transaction price can
differ by tens of thousands. Meanwhile the things that matter most — accident history, odometer tampering,
insurance claims — are exactly what public sources cannot tell you.

This skill does not hand over a "correct answer". It does three things:

1. **Opens up the channel landscape** — 9 new-car channels and 7 used-car channels, researched individually
   rather than collapsed into a single number.
2. **Grades the evidence** — every data point is tagged `A` official / `B` platform listing / `C` third-party
   / `D` not obtained, with a source link and a retrieval timestamp.
3. **Names the gaps** — anything unobtainable is never invented. It is collected into a
   "gaps requiring manual confirmation" table, each row with a concrete action: *which number to call,
   which platform to query, which document to demand.*

> Design stance: **one fabricated phone number does far more damage than ten honest "not available" entries.**

## What the output looks like

An eight-section report: findings first → price overview → per-channel detail → inspection checklist →
red flags → recommended paths → **data gaps** → sources.

Full real-world output: [`examples/mercedes-e-coupe-2018-shanghai.md`](./examples/mercedes-e-coupe-2018-shanghai.md)
(a report produced by an actual run; contact details redacted).

It produces negotiation anchors like this:

| Model | Asking price | Original MSRP | Residual value | Odometer | Registered | Emissions |
|---|---|---|---|---|---|---|
| E 200 Coupe MY2018 | ¥188,800 | ¥522,800 | **36.1%** | 50,000 km | 2018-07 | Euro 5 |
| E 300 Coupe MY2019 | ¥218,000 | ¥604,800 | **36.0%** | 150,000 km | 2018-12 | Euro 6 |

And findings that change the entire search strategy:

> Shanghai sits in the Yangtze River Delta, where out-of-province used cars must meet **China Stage VI-b**
> to be transferred in — yet many MY2018 E200 Coupes are labelled "Euro 5".
> Conclusion: **you can realistically only buy a car already registered in Shanghai.** Importing a cheaper
> car from another province will fail at the emissions checkpoint.

## Installation

This skill lives in the `car-buying-advisor/` **subdirectory** of the
[`Rao-Zongxin`](https://github.com/N0V21/Rao-Zongxin) repository.

⚠️ Note: skill discovery requires `SKILL.md` to sit at the **root** of the install directory, and it does
**not** recurse into nested `SKILL.md` files. Cloning the whole repository into your skills directory will
therefore not work — extract the subdirectory first. Pick either method below.

### Option 1: Download the ZIP (simplest, no git required)

On the [repository page](https://github.com/N0V21/Rao-Zongxin), click **Code → Download ZIP**, unzip, then
copy the `Rao-Zongxin-main/car-buying-advisor` folder into the relevant skills directory.

### Option 2: Command line

**DeepSeek Harness / DSH**

```bash
git clone --depth 1 https://github.com/N0V21/Rao-Zongxin.git /tmp/rao-zongxin
mkdir -p ~/.dsh/skills
cp -R /tmp/rao-zongxin/car-buying-advisor ~/.dsh/skills/car-buying-advisor
rm -rf /tmp/rao-zongxin
```

**Claude Code**

```bash
git clone --depth 1 https://github.com/N0V21/Rao-Zongxin.git /tmp/rao-zongxin
mkdir -p ~/.claude/skills
cp -R /tmp/rao-zongxin/car-buying-advisor ~/.claude/skills/car-buying-advisor
rm -rf /tmp/rao-zongxin
```

After copying, confirm that `~/.dsh/skills/car-buying-advisor/SKILL.md` sits **directly in that
directory** (not one level deeper), otherwise the skill will not be discovered.

**Claude.ai**: zip the `car-buying-advisor` folder and upload it (the zip must contain a single top-level
directory with the same name as the skill).

### Other agents (Codex / Cursor / Zed / Jules …)

See [`adapters/`](./adapters):

| File | Where to install it |
|---|---|
| `adapters/AGENTS.md.template` | copy to your project root and rename to `AGENTS.md` |
| `adapters/cursor-car-buying-advisor.mdc` | copy to `.cursor/rules/` |
| `adapters/copilot-instructions.md` | copy to `.github/copilot-instructions.md` |

## Compatibility — read this before assuming it "just works"

**This skill is not universal across every AI agent.** Pick the right integration:

| Class | Details |
|---|---|
| ✅ **Native `SKILL.md` support** | Claude Code, Claude.ai, Anthropic Agent SDK, DeepSeek Harness, and any client implementing the [Agent Skills specification](https://agentskills.io/specification) |
| ⚠️ **Needs an adapter** | Codex / Zed / Jules (read `AGENTS.md`), Cursor (reads `.cursor/rules/*.mdc`), GitHub Copilot (reads `.github/copilot-instructions.md`) — use the files in `adapters/` |
| ❌ **Cannot be used** | Pure chat models with no tool use (no web search, no file writes) |

The `SKILL.md` frontmatter strictly follows the Agent Skills specification
(`name` / `description` / `license` / `compatibility` / `metadata`) so it ports across clients. The bundled
`AGENTS.md` / `.mdc` / Copilot files are **condensed equivalents** — close in behaviour, but the full rules
still live in `SKILL.md` and `references/`.

## Repository layout

```
car-buying-advisor/
├── SKILL.md                          # the skill itself (Agent Skills spec)
├── README.md                         # Chinese
├── README.en.md                      # English (this file)
├── LICENSE
├── CHANGELOG.md
├── assets/
│   └── report-template.md            # eight-section report skeleton
├── references/
│   ├── channel-guide.md              # all channels, risks, inspection & contract clauses
│   └── evidence-grading.md           # grading rules, landed-cost formula, 2026 subsidies, emissions
├── examples/
│   └── mercedes-e-coupe-2018-shanghai.md   # real output sample (redacted)
├── adapters/                         # cross-agent compatibility layer
│   ├── AGENTS.md.template
│   ├── cursor-car-buying-advisor.mdc
│   └── copilot-instructions.md
├── scripts/
│   ├── validate_skill.py             # specification validator
│   └── test_validate_skill.py        # tests for the validator (14 cases)
└── ci/
    └── car-buying-advisor.yml        # copy to the repo root's .github/workflows/
```

## Built-in domain knowledge

Facts baked in, so they are not re-researched on every run:

- **2026 trade-in subsidy**: scrappage renewal — 12% of the new car's price up to ¥20,000 for a NEV, 10% up
  to ¥15,000 for a ≤2.0L ICE; replacement renewal — 8% up to ¥15,000 for a NEV, 6% up to ¥13,000 for ICE.
  The old car must have been registered to the buyer before 2025-01-08, and the subsidy is once per person.
- **NEV purchase tax**: from 2026-01-01 to 2027-12-31 it is **halved (5% rate)**, capped at ¥15,000 of tax
  relief per vehicle. (The 2024–2025 "exempt" rule has expired; using it understates the budget by roughly 5%.)
- **Emissions relocation limits**: key regions such as the Yangtze River Delta and Pearl River Delta only
  accept China Stage VI-b vehicles.
- **Euro ≠ China standards**: a platform's "Euro 5 / Euro 6" label is **not** equivalent to China's
  Stage V / Stage VI environmental disclosure grade; it must be looked up separately by VIN.
- **Three hidden used-car costs**: licence plate quota (in Shanghai/Beijing this can rival the car's price),
  reconditioning budget (¥10,000–20,000 for an 8-year-old car), and transfer/service fees.
- **Financing-lease trap**: with a "lease-to-own" contract the buyer does not own the car during repayment.

## Known limitations

- **Depends on public search.** Actual transaction prices, insurance-claim records, service histories and
  true odometer readings are paid or identity-gated data. This skill explicitly does not obtain or infer them.
  That is a design choice, not a defect.
- **Chinese-language sources.** Built for the Chinese market; other markets need their own source set.
- **Time-sensitive.** Subsidy and purchase-tax figures are written for 2026 and need updating in
  `references/evidence-grading.md` in later years.
- **Platform labels are not gospel.** Emissions and mileage fields on listing pages are entered by the
  platform or the seller. The report flags them, but that does not replace physical verification.

## Validation

```bash
python3 scripts/validate_skill.py        # check SKILL.md against the specification
python3 scripts/test_validate_skill.py   # tests for the validator (14 cases)
```

`validate_skill.py` checks frontmatter completeness, `name` rules (length, character set, match with the
directory name), the `description` and `compatibility` length caps, and that every relative path referenced
from the body actually exists. Standard library only, no third-party dependencies.

`test_validate_skill.py` pairs every rule with a fixture that **must fail** and one that **must pass** —
a validator that only ever passes is worthless.

> ⚠️ **About CI**: GitHub Actions **only reads `.github/workflows/` at the repository root**; a workflow inside a
> subdirectory never runs. Because this skill lives in a monorepo subdirectory, `ci/car-buying-advisor.yml` must be
> **copied to the repo root's** `.github/workflows/` to take effect. The workflow is path-filtered so it only fires
> on `car-buying-advisor/**` changes and does not affect the other projects in the same repository.

## License

[MIT](./LICENSE)
