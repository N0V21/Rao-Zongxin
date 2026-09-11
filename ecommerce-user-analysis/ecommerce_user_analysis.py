# -*- coding: utf-8 -*-
"""
电商用户行为分析 —— 漏斗转化 / 留存 / RFM 分层

覆盖数据分析岗最核心的三类分析题：
  1. 转化漏斗：浏览 → 加购/收藏 → 支付，定位流失最大的环节
  2. 留存分析：按首访日期分群（cohort），看次日 / 3日 / 7日 / 14日 留存
  3. RFM 用户分层：用最近一次消费、消费频次、消费金额把用户切开，看价值结构
  4. 帕累托检验：验证"20% 的用户贡献了大部分 GMV"在本数据集上是否成立

数据说明：项目使用**本地合成的模拟数据**（固定随机种子），clone 下来即可运行，
无需下载任何外部数据集。真实业务中把 generate_events() 换成数仓 SQL 即可，
下游分析逻辑完全复用。

运行：python ecommerce_user_analysis.py
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

RNG = np.random.default_rng(20260912)
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(ASSET_DIR, exist_ok=True)

N_USERS = 12000
DAYS = 30
START = pd.Timestamp("2026-08-01")


# ---------------------------------------------------------------- 1. 模拟行为日志
def generate_events() -> pd.DataFrame:
    """生成 30 天的用户行为日志：pv / fav / cart / buy。"""
    # 用户活跃度服从长尾分布：多数人低频，少数高活
    activity = RNG.lognormal(mean=1.6, sigma=0.75, size=N_USERS)
    activity = np.clip(activity, 1, 120).astype(int)

    records = []
    # 用户的购买倾向（用于制造真实的漏斗：约 35% 的浏览用户最终会买）
    propensity = RNG.beta(2, 6, size=N_USERS)

    for uid in range(N_USERS):
        n = activity[uid]
        first_day = RNG.integers(0, DAYS)
        day_offsets = np.sort(RNG.integers(0, DAYS - first_day if DAYS - first_day > 0 else 1,
                                           size=max(1, min(n, DAYS - first_day if DAYS - first_day > 0 else 1))))
        for off in day_offsets[:max(1, n // 3)]:
            ts = START + pd.Timedelta(days=int(first_day + off),
                                      hours=int(RNG.integers(0, 24)),
                                      minutes=int(RNG.integers(0, 60)))
            records.append((uid, "pv", ts, 0.0))
            r = RNG.random()
            if r < 0.18:
                records.append((uid, "fav", ts + pd.Timedelta(minutes=2), 0.0))
            if r < 0.30:
                records.append((uid, "cart", ts + pd.Timedelta(minutes=4), 0.0))
            if RNG.random() < propensity[uid] * 0.55:
                records.append((uid, "buy", ts + pd.Timedelta(minutes=8),
                                round(float(RNG.lognormal(np.log(180), 0.6)), 2)))
    df = pd.DataFrame(records, columns=["user_id", "behavior", "ts", "amount"])
    return df.sort_values("ts").reset_index(drop=True)


def funnel_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """浏览 → 收藏/加购 → 支付 的用户级漏斗。"""
    stages = {
        "浏览": set(df[df.behavior == "pv"].user_id),
        "收藏/加购": set(df[df.behavior.isin(["fav", "cart"])].user_id),
        "支付": set(df[df.behavior == "buy"].user_id),
    }
    base = len(stages["浏览"])
    rows = []
    prev = None
    for name, users in stages.items():
        n = len(users)
        rows.append({
            "环节": name, "用户数": n,
            "整体转化率": n / base,
            "环节转化率": np.nan if prev is None else n / prev,
        })
        prev = n
    return pd.DataFrame(rows)


def retention_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """按首访日期的次日 / 3日 / 7日 / 14日 留存。"""
    first = df.groupby("user_id").ts.min().dt.normalize().rename("first_day")
    d = df[["user_id", "ts"]].merge(first, on="user_id")
    d["day_diff"] = (d.ts.dt.normalize() - d.first_day).dt.days
    active = d.groupby(["first_day", "day_diff"]).user_id.nunique().rename("users").reset_index()
    cohort_size = active[active.day_diff == 0].set_index("first_day").users
    out = []
    for gap in [1, 3, 7, 14]:
        sub = active[active.day_diff == gap]
        if len(sub) == 0:
            continue
        rate = (sub.set_index("first_day").users / cohort_size).dropna()
        out.append({"留存天数": f"{gap}日", "平均留存率": rate.mean()})
    return pd.DataFrame(out)


def rfm_analysis(df: pd.DataFrame) -> tuple:
    """RFM 打分与分层。"""
    buy = df[df.behavior == "buy"]
    snapshot = df.ts.max()
    rfm = buy.groupby("user_id").agg(
        R=("ts", lambda s: (snapshot - s.max()).days),
        F=("ts", "count"),
        M=("amount", "sum"),
    ).reset_index()

    # 打分：R 越小越好，F / M 越大越好，按五分位打分
    rfm["R_score"] = pd.qcut(rfm.R, 5, labels=[5, 4, 3, 2, 1]).astype(int)
    rfm["F_score"] = pd.qcut(rfm.F.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["M_score"] = pd.qcut(rfm.M.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["RFM"] = rfm.R_score * 100 + rfm.F_score * 10 + rfm.M_score

    def seg(row):
        if row.R_score >= 4 and row.F_score >= 4:
            return "重要价值用户"
        if row.R_score >= 4 and row.F_score <= 2:
            return "潜力用户（新客）"
        if row.R_score <= 2 and row.F_score >= 4:
            return "重要挽留用户"
        if row.R_score <= 2 and row.F_score <= 2:
            return "流失用户"
        return "一般价值用户"

    rfm["分层"] = rfm.apply(seg, axis=1)
    return rfm, snapshot


def pareto(df: pd.DataFrame) -> tuple:
    """按消费金额排序，计算累计 GMV 占比。"""
    buy = df[df.behavior == "buy"]
    user_gmv = buy.groupby("user_id").amount.sum().sort_values(ascending=False)
    cum = user_gmv.cumsum() / user_gmv.sum()
    x = np.arange(1, len(user_gmv) + 1) / len(user_gmv)
    top20_share = cum.iloc[int(len(user_gmv) * 0.2) - 1]
    return x, cum.values, top20_share, len(user_gmv)


def main():
    print("=" * 70)
    print("电商用户行为分析 —— 漏斗 / 留存 / RFM")
    print("=" * 70)

    df = generate_events()
    print(f"\n[0] 数据概览")
    print(f"    行为记录 {len(df):,} 条 ｜ 用户 {df.user_id.nunique():,} 人 ｜ "
          f"时间跨度 {df.ts.min():%Y-%m-%d} ~ {df.ts.max():%Y-%m-%d}")
    print("    行为分布：" + "  ".join(f"{k}={v:,}" for k, v in df.behavior.value_counts().items()))

    # ---- 漏斗
    fun = funnel_analysis(df)
    print("\n[1] 转化漏斗")
    for _, r in fun.iterrows():
        step = "—" if pd.isna(r.环节转化率) else f"{r.环节转化率:.1%}"
        print(f"    {r.环节:<10} {r.用户数:>7,} 人   整体 {r.整体转化率:.1%}   环节 {step}")
    drop = fun.iloc[1].用户数 - fun.iloc[2].用户数
    print(f"    最大流失环节：收藏/加购 → 支付，流失 {drop:,} 人（占加购用户 {drop / fun.iloc[1].用户数:.1%}）")

    # ---- 留存
    ret = retention_analysis(df)
    print("\n[2] 留存分析（按首访日分群）")
    for _, r in ret.iterrows():
        print(f"    {r.留存天数}留存  {r.平均留存率:.1%}")

    # ---- RFM
    rfm, _ = rfm_analysis(df)
    seg_summary = rfm.groupby("分层").agg(人数=("user_id", "count"), 人均消费=("M", "mean")).reset_index()
    seg_summary["占比"] = seg_summary.人数 / seg_summary.人数.sum()
    seg_summary = seg_summary.sort_values("人数", ascending=False)
    print("\n[3] RFM 用户分层")
    for _, r in seg_summary.iterrows():
        print(f"    {r.分层:<14} {r.人数:>6,} 人（{r.占比:.1%}）  人均消费 ¥{r.人均消费:,.0f}")

    # ---- 帕累托
    x, cum, top20, n_buyers = pareto(df)
    print("\n[4] 价值集中度")
    print(f"    付费用户 {n_buyers:,} 人，Top 20% 贡献 {top20:.1%} 的 GMV")

    # ------------------------------------------------ 可视化
    # 图1：漏斗
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    colors = ["#1f77b4", "#4c9be8", "#2ca02c"]
    ax.bar(fun.环节, fun.用户数, color=colors, width=0.55)
    for i, r in fun.iterrows():
        ax.text(i, r.用户数 + 120, f"{r.用户数:,}\n({r.整体转化率:.1%})", ha="center", fontsize=10)
    ax.set_ylabel("用户数")
    ax.set_ylim(0, fun.用户数.max() * 1.25)
    ax.set_title("用户转化漏斗：浏览 → 收藏/加购 → 支付", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(ASSET_DIR, "funnel.png"), dpi=150)
    plt.close()

    # 图2：留存曲线
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    ax.plot(ret.留存天数, ret.平均留存率 * 100, marker="o", color="#1f77b4", linewidth=2)
    for i, r in ret.iterrows():
        ax.text(i, r.平均留存率 * 100 + 1.2, f"{r.平均留存率:.1%}", ha="center", fontsize=10)
    ax.set_ylabel("留存率 (%)")
    ax.set_ylim(0, ret.平均留存率.max() * 100 * 1.3)
    ax.set_title("用户留存曲线（按首访日分群）", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(ASSET_DIR, "retention.png"), dpi=150)
    plt.close()

    # 图3：RFM 分层
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    ax = axes[0]
    ax.barh(seg_summary.分层, seg_summary.人数, color="#1f77b4", height=0.55)
    for i, r in seg_summary.iterrows():
        ax.text(r.人数 + 40, i, f"{r.人数:,} ({r.占比:.1%})", va="center", fontsize=9.5)
    ax.set_xlabel("人数")
    ax.set_title("RFM 分层人数分布", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    ax.barh(seg_summary.分层, seg_summary.人均消费, color="#2ca02c", height=0.55)
    for i, r in seg_summary.iterrows():
        ax.text(r.人均消费 + 10, i, f"¥{r.人均消费:,.0f}", va="center", fontsize=9.5)
    ax.set_xlabel("人均消费 (元)")
    ax.set_title("各分层人均消费", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(ASSET_DIR, "rfm_segments.png"), dpi=150)
    plt.close()

    # 图4：帕累托 + 时段活跃
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    ax = axes[0]
    ax.plot(x * 100, cum * 100, color="#1f77b4", linewidth=2)
    ax.axvline(20, linestyle="--", color="#d62728")
    ax.axhline(top20 * 100, linestyle="--", color="#d62728")
    ax.set_xlabel("用户累计占比 (%)")
    ax.set_ylabel("GMV 累计占比 (%)")
    ax.set_title(f"价值集中度：Top 20% 用户贡献 {top20:.1%} GMV", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    hourly = df.groupby(df.ts.dt.hour).size()
    ax.bar(hourly.index, hourly.values, color="#4c9be8")
    ax.set_xlabel("小时")
    ax.set_ylabel("行为次数")
    ax.set_title("活跃时段分布", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(ASSET_DIR, "pareto_and_hourly.png"), dpi=150)
    plt.close()

    print("\n[5] 图表已输出到 assets/")
    print("    funnel.png / retention.png / rfm_segments.png / pareto_and_hourly.png")
    print("\n" + "=" * 70)
    print("核心结论：")
    print(f"  1. 浏览→加购 转化 {fun.iloc[1].环节转化率:.1%}，加购→支付 仅 {fun.iloc[2].环节转化率:.1%}，"
          f"支付环节是最大流失点（{drop:,} 人流失）")
    print(f"  2. 次日留存 {ret.iloc[0].平均留存率:.1%}，7日留存 {ret[ret.留存天数=='7日'].平均留存率.iloc[0]:.1%}，"
          f"中长期留存仍有提升空间")
    key = seg_summary[seg_summary.分层 == "重要价值用户"]
    if len(key):
        print(f"  3. 重要价值用户 {key.人数.iloc[0]:,} 人（{key.占比.iloc[0]:.1%}），人均消费 ¥{key.人均消费.iloc[0]:,.0f}，"
              f"是普通用户的 {key.人均消费.iloc[0] / seg_summary[seg_summary.分层=='一般价值用户'].人均消费.iloc[0]:.1f} 倍")
    print(f"  4. 收入高度集中：Top 20% 用户贡献 {top20:.1%} GMV，运营资源应向头部倾斜")
    print("=" * 70)


if __name__ == "__main__":
    main()
