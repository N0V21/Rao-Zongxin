# Changelog

All notable changes to this skill are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-20

Initial public release.

### Added

- `SKILL.md` — full operating procedure for generating a cross-channel car
  purchase comparison report, conforming to the
  [Agent Skills specification](https://agentskills.io/specification).
- `references/channel-guide.md` — all 9 new-car channels (authorised 4S,
  OEM direct, franchise/partner, secondary dealers, auto malls, parallel
  imports, e-commerce, official apps, financing leases) and all 7 used-car
  channels, each with reliability rating, risk profile and verification steps.
- `references/evidence-grading.md` — the A/B/C/D evidence grading scheme,
  landed-cost formula, 2026 trade-in subsidy rules, NEV purchase-tax change,
  and emission/relocation checks.
- `assets/report-template.md` — the eight-section report skeleton.
- `examples/mercedes-e-coupe-2018-shanghai.md` — a real report produced by the
  skill (contact details redacted).
- `README.en.md` — full English README, with language switchers on both READMEs.
- `adapters/` — equivalents for agents that do not read `SKILL.md`:
  `AGENTS.md.template`, a Cursor `.mdc` rule, and Copilot instructions.
- `scripts/validate_skill.py` plus a GitHub Actions workflow that checks
  spec compliance on every push.

### Design decisions worth recording

- **Refuse to fabricate.** The skill forbids inventing phone numbers, prices,
  mileage or accident history. Unobtainable data is marked `D` and collected
  into a "gaps" table with a concrete action for closing each one. A fabricated
  contact number is far more harmful than an honest "not available".
- **Board price is never presented as transaction price.** Platform listings
  are always labelled as asking prices requiring phone confirmation.
- **Distinguish "model year" from "registration year".** A 2018 model year car
  may have been registered in 2018 or a 2017 model year car registered in 2018;
  the skill forces this to be resolved before research starts.
- **European emission labels are not Chinese ones.** Platform labels such as
  "Euro 5 / Euro 6" are explicitly flagged as not equivalent to China's
  Stage V / Stage VI environmental disclosure grades, which must be looked up
  by VIN.
- **`adapters/AGENTS.md` ships as `AGENTS.md.template`** so that cloning this
  repository does not silently inject agent instructions into the host project.
