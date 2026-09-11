# -*- coding: utf-8 -*-
"""
AB 实验效果评估 —— 首页推荐位改版

一个完整的实验分析流程，覆盖数据分析岗面试最常问的几件事：
  1. 事前功效分析：这个实验到底需要多少人？
  2. 核心指标假设检验：两比例 z 检验（转化率）+ Welch t 检验（人均 GMV）
  3. 分层一致性检查：整体显著 ≠ 每个平台都显著（避免辛普森悖论）
  4. 新奇效应检查：提升是可持续的，还是前几天的假象？
  5. 结论与上线建议

数据说明：本项目使用**本地合成的模拟数据**（np.random.default_rng 固定随机种子），
不依赖任何外部数据集，clone 下来即可运行。真实业务中把 generate_data() 替换成
数仓 SQL 取数即可，分析逻辑完全复用。

运行：python ab_test_analysis.py
"""

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

RNG = np.random.default_rng(20260912)
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(ASSET_DIR, exist_ok=True)

ALPHA = 0.05
POWER = 0.80


# ---------------------------------------------------------------- 1. 事前功效分析
def required_sample_size(p0: float, mde_abs: float, alpha=ALPHA, power=POWER) -> int:
    """两比例检验所需每组样本量（绝对提升口径）。"""
    p1 = p0 + mde_abs
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    p_bar = (p0 + p1) / 2
    n = ((z_alpha * np.sqrt(2 * p_bar * (1 - p_bar)) + z_beta * np.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2) / (mde_abs ** 2)
    return int(np.ceil(n))


# ---------------------------------------------------------------- 2. 模拟实验数据
def generate_data(n_per_group: int = 30000, days: int = 14) -> pd.DataFrame:
    """
    模拟一次为期 14 天的首页推荐位改版实验。

    真实的业务设定（分析时未知，用于检验方法是否抓得住）：
      - Android 端确实有提升（+1.4pp），iOS 端几乎没有提升（+0.2pp）
      - 存在新奇效应：前 3 天提升约为稳态的 1.8 倍，之后逐日衰减
    """
    rows = []
    for group, lift_android, lift_ios in [("control", 0.0, 0.0), ("treatment", 0.020, 0.002)]:
        platform = RNG.choice(["Android", "iOS"], size=n_per_group, p=[0.55, 0.45])
        day = RNG.integers(1, days + 1, size=n_per_group)

        base_conv = np.where(platform == "Android", 0.115, 0.126)
        lift = np.where(platform == "Android", lift_android, lift_ios)
        # 新奇效应：lift 随时间衰减，Day1 为 2.0 倍，Day14 为 0.7 倍
        novelty = 2.0 - 1.3 * (day - 1) / (days - 1)
        conv = base_conv + lift * novelty

        converted = RNG.binomial(1, np.clip(conv, 0, 1))
        # GMV：仅转化用户有消费，实验组客单价小幅提升
        base_gmv = np.where(platform == "Android", 250, 285)
        gmv_boost = np.where(platform == "Android", 1.03, 1.005)
        gmv = np.where(converted == 1,
                       RNG.lognormal(mean=np.log(base_gmv), sigma=0.45, size=n_per_group) * gmv_boost,
                       0.0)

        rows.append(pd.DataFrame({
            "group": group, "platform": platform, "day": day,
            "converted": converted, "gmv": np.round(gmv, 2),
        }))
    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------- 3. 假设检验
def two_proportion_ztest(c_conv, c_n, t_conv, t_n, alpha=ALPHA):
    """两比例 z 检验，返回 (对照组率, 实验组率, 绝对提升, 相对提升, z, p, 是否显著, 绝对提升95%CI)。"""
    p1, p2 = c_conv / c_n, t_conv / t_n
    p_pool = (c_conv + t_conv) / (c_n + t_n)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / c_n + 1 / t_n))
    z = (p2 - p1) / se_pool
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    se_unpool = np.sqrt(p1 * (1 - p1) / c_n + p2 * (1 - p2) / t_n)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    diff = p2 - p1
    ci = (diff - z_crit * se_unpool, diff + z_crit * se_unpool)
    return p1, p2, diff, diff / p1, z, p_value, p_value < alpha, ci


def welch_ttest(a, b, alpha=ALPHA):
    """Welch t 检验，返回 (均值a, 均值b, 差值, 相对提升, t, p, 是否显著, 95%CI)。"""
    t, p = stats.ttest_ind(b, a, equal_var=False)
    ma, mb = a.mean(), b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    diff = mb - ma
    dof = len(a) + len(b) - 2
    t_crit = stats.t.ppf(1 - alpha / 2, dof)
    return ma, mb, diff, diff / ma, t, p, p < alpha, (diff - t_crit * se, diff + t_crit * se)


def main():
    print("=" * 70)
    print("AB 实验效果评估 —— 首页推荐位改版")
    print("=" * 70)

    # ---- 事前功效分析
    p0, mde = 0.12, 0.010
    n_need = required_sample_size(p0, mde)
    print(f"\n[1] 事前功效分析  baseline={p0:.1%}  MDE={mde:.1%}  alpha={ALPHA}  power={POWER}")
    print(f"    每组至少需要 {n_need:,} 人，两组合计 {2 * n_need:,} 人")

    df = generate_data()
    print(f"\n[2] 实验数据   对照组 {len(df[df.group=='control']):,} 人 / 实验组 {len(df[df.group=='treatment']):,} 人 / 实验周期 {df.day.max()} 天")

    # ---- 核心指标
    c = df[df.group == "control"]
    t = df[df.group == "treatment"]
    print("\n[3] 核心指标假设检验")
    res = {}
    p1, p2, diff, rel, z, pv, sig, ci = two_proportion_ztest(
        c.converted.sum(), len(c), t.converted.sum(), len(t))
    res["conversion"] = (p1, p2, diff, rel, pv, sig, ci)
    print(f"    转化率  {p1:.2%} -> {p2:.2%}  绝对提升 {diff:+.2%}  相对提升 {rel:+.2%}")
    print(f"            z={z:.3f}  p={pv:.4f}  {'显著' if sig else '不显著'}  95%CI [{ci[0]:+.2%}, {ci[1]:+.2%}]")

    ma, mb, d, r, tv, pv2, sig2, ci2 = welch_ttest(c.gmv.values, t.gmv.values)
    res["gmv"] = (ma, mb, d, r, pv2, sig2, ci2)
    print(f"    人均GMV  ¥{ma:.1f} -> ¥{mb:.1f}  绝对提升 ¥{d:+.1f}  相对提升 {r:+.2%}")
    print(f"            t={tv:.3f}  p={pv2:.4f}  {'显著' if sig2 else '不显著'}  95%CI [¥{ci2[0]:+.1f}, ¥{ci2[1]:+.1f}]")

    # ---- 分层一致性
    print("\n[4] 分层一致性检查（避免辛普森悖论）")
    seg_rows = []
    for plat in ["Android", "iOS"]:
        cc = df[(df.group == "control") & (df.platform == plat)]
        tt = df[(df.group == "treatment") & (df.platform == plat)]
        a1, a2, ad, ar, _, apv, asig, aci = two_proportion_ztest(
            cc.converted.sum(), len(cc), tt.converted.sum(), len(tt))
        seg_rows.append({"platform": plat, "control": a1, "treatment": a2,
                         "lift": ad, "rel": ar, "p": apv, "significant": asig,
                         "ci_low": aci[0], "ci_high": aci[1]})
        print(f"    {plat:<8} {a1:.2%} -> {a2:.2%}  {ad:+.2%} ({ar:+.1%})  p={apv:.4f}  {'显著' if asig else '不显著'}")
    seg = pd.DataFrame(seg_rows)

    # ---- 新奇效应
    print("\n[5] 新奇效应检查（按实验天数拆分提升）")
    daily = []
    for d in sorted(df.day.unique()):
        cc = df[(df.group == "control") & (df.day == d)]
        tt = df[(df.group == "treatment") & (df.day == d)]
        _, _, ad, _, _, _, _, _ = two_proportion_ztest(cc.converted.sum(), len(cc), tt.converted.sum(), len(tt))
        daily.append({"day": d, "lift": ad})
    daily = pd.DataFrame(daily)
    early = daily[daily.day <= 3].lift.mean()
    late = daily[daily.day > 3].lift.mean()
    print(f"    Day1-3 平均提升 {early:+.2%} ｜ Day4-14 平均提升 {late:+.2%} ｜ 衰减 {(early - late):+.2%}")

    # ------------------------------------------------ 可视化
    # 图1：指标对比
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    bars = ax.bar(["对照组", "实验组"], [p1 * 100, p2 * 100], color=["#9aa5b1", "#1f77b4"], width=0.5)
    for b, v in zip(bars, [p1, p2]):
        ax.text(b.get_x() + b.get_width() / 2, v * 100 + 0.15, f"{v:.2%}", ha="center", fontsize=11)
    ax.set_title(f"整体转化率  ({res['conversion'][3]:+.1%} 相对提升, p={pv:.4f})", fontsize=12)
    ax.set_ylabel("转化率 (%)")
    ax.set_ylim(0, max(p1, p2) * 100 * 1.25)
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    ax.bar(["对照组", "实验组"], [ma, mb], color=["#9aa5b1", "#1f77b4"], width=0.5)
    ax.set_title(f"人均 GMV（元，全体用户口径）  ({res['gmv'][3]:+.1%}, p={pv2:.4f})", fontsize=12)
    ax.set_ylabel("人均 GMV (元)")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(ASSET_DIR, "metrics_overall.png"), dpi=150)
    plt.close()

    # 图2：分层提升 + 95%CI
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    y = np.arange(len(seg))
    errs = [seg.lift - seg.ci_low, seg.ci_high - seg.lift]
    colors = ["#2ca02c" if s else "#d62728" for s in seg.significant]
    ax.barh(y, seg.lift * 100, xerr=[e * 100 for e in errs], color=colors,
            height=0.5, capsize=5)
    ax.set_yticks(y)
    ax.set_yticklabels(seg.platform)
    ax.axvline(0, color="#333", linewidth=0.8)
    ax.set_xlabel("转化率绝对提升 (pp)")
    ax.set_title("分层提升与 95% 置信区间（绿色=显著，红色=不显著）", fontsize=12)
    for i, (v, s, pval) in enumerate(zip(seg.lift, seg.significant, seg.p)):
        ax.text(v * 100 + 0.08, i, f"{v:+.2%} (p={pval:.3f})", va="center", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(ASSET_DIR, "segment_lift.png"), dpi=150)
    plt.close()

    # 图3：新奇效应趋势
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.plot(daily.day, daily.lift * 100, marker="o", color="#1f77b4", label="当日提升")
    ax.axhline(early * 100, linestyle="--", color="#2ca02c", label=f"Day1-3 均值 {early:+.2%}")
    ax.axhline(late * 100, linestyle="--", color="#ff7f0e", label=f"Day4-14 均值 {late:+.2%}")
    ax.axhline(0, color="#333", linewidth=0.8)
    ax.set_xlabel("实验天数")
    ax.set_ylabel("转化率提升 (pp)")
    ax.set_title("新奇效应检查：提升随时间衰减", fontsize=12)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(ASSET_DIR, "novelty_effect.png"), dpi=150)
    plt.close()

    # 图4：功效曲线
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ns = np.arange(1000, 26000, 500)
    powers = []
    for n in ns:
        se = np.sqrt(2 * p0 * (1 - p0) / n)
        zc = stats.norm.ppf(1 - ALPHA / 2)
        powers.append(1 - stats.norm.cdf(zc - mde / se) + stats.norm.cdf(-zc - mde / se))
    ax.plot(ns, np.array(powers), color="#1f77b4")
    ax.axhline(POWER, linestyle="--", color="#d62728", label="目标 power = 0.80")
    ax.axvline(n_need, linestyle="--", color="#2ca02c", label=f"所需样本量 = {n_need:,}")
    ax.set_xlabel("每组样本量")
    ax.set_ylabel("统计功效 (power)")
    ax.set_title("事前功效分析：样本量 vs 检验功效", fontsize=12)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(ASSET_DIR, "power_curve.png"), dpi=150)
    plt.close()

    print("\n[6] 图表已输出到 assets/")
    print("    metrics_overall.png / segment_lift.png / novelty_effect.png / power_curve.png")
    print("\n" + "=" * 70)
    print("结论：")
    print(f"  1. 整体转化率 {p1:.2%} -> {p2:.2%}，相对提升 {rel:+.1%}（p={pv:.4f}），{'达到' if sig else '未达到'}显著水平")
    print(f"  2. 分平台看，{'、'.join(seg[seg.significant].platform)} 端显著，"
          f"{'、'.join(seg[~seg.significant].platform) if (~seg.significant).any() else '无'} 端不显著 —— 整体显著由单一平台拉动，不建议盲目全量")
    decay_note = (f"提升随时间衰减（Day1-3 {early:+.2%} vs Day4-14 {late:+.2%}），"
                  f"当前窗口内尚未稳定，建议延长观察后再全量" if early - late > 0.002
                  else f"Day1-3 {early:+.2%} 与 Day4-14 {late:+.2%} 基本持平，"
                       f"未观察到明显的新奇效应衰减")
    print(f"  3. 新奇效应：{decay_note}")
    print("=" * 70)


if __name__ == "__main__":
    main()
