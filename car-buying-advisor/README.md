# car-buying-advisor

**中文** | [English](./README.en.md)

> 一个 **Agent Skill**：给我一个车型，产出可核验的**全渠道购车对比报告**。
> 覆盖新车与二手车全部销售渠道，每一条价格、车源、联系方式、公里数、车况信息都标注**证据等级与来源**。

[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-4B5563)](https://agentskills.io/specification)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Language](https://img.shields.io/badge/lang-zh--CN-blue)](./README.md)

---

## 它解决什么问题

买车时真正难的不是"找到价格"，而是**判断这个价格能不能信**。同一台车，4S 店报价、平台挂牌价、车主成交价可能差好几万，而事故记录、真实里程、出险历史恰恰是公开渠道查不到的。

这个 skill 不给"标准答案"，它做三件事：

1. **把渠道铺开** —— 新车 9 类渠道 + 二手车 7 类渠道，逐个检索而不是只报一个价。
2. **把证据分级** —— 每条数据标 `A`官方 / `B`平台挂牌 / `C`自媒体 / `D`未获取，附来源链接和抓取时间。
3. **把缺口写明** —— 拿不到的信息不编，集中列成"待人工确认项"，每条都写清**打哪个电话、查哪个平台、看哪份材料**。

> 设计立场：**一条编造的 400 电话，比十条"未获取"的危害大得多。**

## 输出长什么样

八节报告：结论先行 → 价格总览 → 渠道明细 → 车况核验清单 → 避坑提示 → 推荐路径 → **数据缺口** → 信息来源。

完整真实产出：[`examples/mercedes-e-coupe-2018-shanghai.md`](./examples/mercedes-e-coupe-2018-shanghai.md)
（一次真实运行的报告，联系方式已脱敏）

报告中会包含这类可直接拿去谈判的锚点：

| 车型 | 报价 | 当年指导价 | 残值率 | 表显里程 | 上牌 | 排放 |
|---|---|---|---|---|---|---|
| E 200 Coupe 2018 款 | 18.88 万 | 52.28 万 | **36.1%** | 5.0 万 km | 2018-07 | 欧5 |
| E 300 Coupe 2019 款 | 21.80 万 | 60.48 万 | **36.0%** | 15.0 万 km | 2018-12 | 欧6 |

以及这类会改变整个找车策略的发现：

> 上海属长三角，外牌二手车迁入需**国六 b**；而 2018 款 E200 Coupe 大量为"欧5"。
> 结论：**大概率只能买已上沪牌的本地车**，从外省买便宜车迁进来在排放这一关就会卡住。

## 安装

仓库根目录就是 skill 本体（`SKILL.md` 在根），克隆到对应目录即可。

### DeepSeek Harness / DSH

```bash
git clone https://github.com/<your-username>/car-buying-advisor.git ~/.dsh/skills/car-buying-advisor
```

### Claude Code

```bash
git clone https://github.com/<your-username>/car-buying-advisor.git ~/.claude/skills/car-buying-advisor
```

Claude.ai 用户可将仓库目录打包成 ZIP 后上传（ZIP 内需包含一层同名目录）。

### 其他 agent（Codex / Cursor / Zed / Jules 等）

见 [`adapters/`](./adapters)：

| 文件 | 安装位置 |
|---|---|
| `adapters/AGENTS.md.template` | 复制到项目根目录并重命名为 `AGENTS.md` |
| `adapters/cursor-car-buying-advisor.mdc` | 复制到 `.cursor/rules/` |
| `adapters/copilot-instructions.md` | 复制到 `.github/copilot-instructions.md` |

## 兼容性说明

**本 skill 不是"所有 AI agent 通用"的**，请按实际情况选择接入方式：

| 类别 | 情况 |
|---|---|
| ✅ **原生支持 `SKILL.md`** | Claude Code、Claude.ai、Anthropic Agent SDK、DeepSeek Harness，以及任何实现 [Agent Skills 规范](https://agentskills.io/specification) 的客户端 |
| ⚠️ **需要适配层** | Codex / Zed / Jules（读 `AGENTS.md`）、Cursor（读 `.cursor/rules/*.mdc`）、GitHub Copilot（读 `.github/copilot-instructions.md`）——使用 `adapters/` 下的文件 |
| ❌ **无法直接使用** | 无工具调用能力（不能联网检索、不能写文件）的纯对话模型 |

`SKILL.md` 的 frontmatter 严格遵循 Agent Skills 规范（`name` / `description` / `license` / `compatibility` / `metadata`），因此可跨客户端移植。仓库另提供的 `AGENTS.md` / `.mdc` / Copilot 指令是**精简等效版**，功能上接近但不含完整细则，细则仍需读 `SKILL.md` 与 `references/`。

## 目录结构

```
car-buying-advisor/
├── SKILL.md                          # 技能本体（Agent Skills 规范）
├── README.md                         # 中文
├── README.en.md                      # English
├── LICENSE
├── CHANGELOG.md
├── assets/
│   └── report-template.md            # 八节报告骨架
├── references/
│   ├── channel-guide.md              # 新车/二手车全渠道清单、风险、验车与合同条款
│   └── evidence-grading.md           # 证据分级细则、落地价公式、2026 补贴与限迁
├── examples/
│   └── mercedes-e-coupe-2018-shanghai.md   # 真实产出样例（已脱敏）
├── adapters/                         # 跨 agent 适配层
│   ├── AGENTS.md.template
│   ├── cursor-car-buying-advisor.mdc
│   └── copilot-instructions.md
├── scripts/
│   ├── validate_skill.py             # 规范校验
│   └── test_validate_skill.py        # 校验器自身的测试（14 项）
└── .github/workflows/validate.yml
```

## 内置的领域知识

这些是 skill 里已经固化、不需要每次重新检索的口径：

- **2026 年以旧换新补贴**：报废更新买新能源按售价 12% 最高 2 万、燃油按 10% 最高 1.5 万；置换更新买新能源 8% 最高 1.5 万、燃油 6% 最高 1.3 万。旧车须 2025-01-08 前登记在本人名下，每人限一次。
- **新能源购置税**：2026-01-01 至 2027-12-31 **减半征收（5%）**，每辆减税额 ≤ 1.5 万元。（2024–2025 的"免征"口径已过期，用错会把预算低估约 5%。）
- **排放限迁**：长三角、珠三角等重点区域只接受国六 b 迁入。
- **欧标 ≠ 国标**：平台标注的「欧5/欧6」不等于中国的「国五/国六」，必须按 VIN 查环保信息公开等级。
- **二手车三项隐藏成本**：牌照额度（可能同车价量级）、整备预算（8 年车龄 1–2 万）、过户服务费。
- **融资租赁陷阱**：还款期间车辆所有权不属于买家。

## 已知局限

- **依赖公开检索**：真实成交价、出险记录、维保记录、真实里程属于**付费或实名数据**，本 skill 明确不获取、不推测。这是设计选择，不是缺陷。
- **中文源为主**：面向中国市场，海外市场需自行替换检索源。
- **时效性**：补贴与购置税政策按 2026 年口径写入，跨年后需更新 `references/evidence-grading.md`。
- **平台标注不可尽信**：车源档案里的排放、里程字段由平台或卖家录入，报告会标注但无法代替实地核验。

## 校验

```bash
python3 scripts/validate_skill.py        # 校验 SKILL.md 是否符合规范
python3 scripts/test_validate_skill.py   # 校验器自身的测试（14 项）
```

`validate_skill.py` 检查 frontmatter 字段完整性、`name` 命名规则（长度/字符集/与目录名一致）、`description` 与 `compatibility` 长度上限、以及正文引用的每个相对路径是否真实存在。纯标准库实现，无第三方依赖。

`test_validate_skill.py` 为每条规则准备了必须失败的样例和必须通过的样例——**一个只会通过的校验脚本没有意义**。

CI 在每次 push 与 PR 时自动运行上述两项。

## License

[MIT](./LICENSE)
