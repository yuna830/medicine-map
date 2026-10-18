
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import (
    ROOT,
    load_csv,
)


# ==========================================
# 경로 설정
# ==========================================

ANALYSIS_DIR = ROOT / "reports" / "analysis"
FIGURES_DIR = ROOT / "reports" / "figures"

DISTRICT_FILE = ANALYSIS_DIR / "district_analysis.csv"
SENSITIVITY_FILE = ANALYSIS_DIR / "sensitivity_analysis.csv"
DISPARITY_FILE = ANALYSIS_DIR / "disparity_analysis.csv"


# ==========================================
# 그래프 기본 설정
# ==========================================

def setup_style():

    # Windows 한글 폰트
    plt.rcParams["font.family"] = "Malgun Gothic"

    # 마이너스 기호 깨짐 방지
    plt.rcParams["axes.unicode_minus"] = False

    plt.rcParams["figure.dpi"] = 120
    plt.rcParams["savefig.dpi"] = 300

    plt.rcParams["font.size"] = 11

    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.spines.right"] = False

    plt.rcParams["axes.axisbelow"] = True


# ==========================================
# 데이터 불러오기
# ==========================================

def load_data():

    paths = [
        DISTRICT_FILE,
        SENSITIVITY_FILE,
        DISPARITY_FILE,
    ]

    for path in paths:
        if not path.exists():
            raise FileNotFoundError(
                f"분석 파일이 없습니다: {path}"
            )

    district = load_csv(DISTRICT_FILE)
    sensitivity = load_csv(SENSITIVITY_FILE)
    disparity = load_csv(DISPARITY_FILE)

    numeric_cols = [
        "facility_records",
        "population_total",
        "population_65_plus",
        "facilities_per_10000",
        "facilities_per_10000_seniors",
    ]

    for col in numeric_cols:
        district[col] = pd.to_numeric(
            district[col],
            errors="raise",
        )

    sensitivity_numeric = [
        "unweighted_mean_rate",
        "pooled_population_rate",
        "median_rate",
        "std_rate",
    ]

    for col in sensitivity_numeric:
        sensitivity[col] = pd.to_numeric(
            sensitivity[col],
            errors="raise",
        )

    for col in [
        "highest_value",
        "lowest_value",
        "max_min_ratio",
    ]:
        disparity[col] = pd.to_numeric(
            disparity[col],
            errors="raise",
        )

    if len(district) != 9:
        raise ValueError(
            "분석 대상 자치구가 9개가 아닙니다."
        )

    return district, sensitivity, disparity


# ==========================================
# 그래프 저장 공통 함수
# ==========================================

def save_figure(filename):

    FIGURES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = FIGURES_DIR / filename

    plt.savefig(
        path,
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )

    plt.close()

    print(f"그래프 저장 완료: {path}")


# ==========================================
# 1. 자치구별 시설 기록 수
# ==========================================

def plot_facility_counts(df):

    data = df.sort_values(
        "facility_records",
        ascending=True,
    )

    fig, ax = plt.subplots(
        figsize=(10, 6)
    )

    colors = [
        "#2563EB" if gu != "양천구"
        else "#F59E0B"
        for gu in data["district"]
    ]

    bars = ax.barh(
        data["district"],
        data["facility_records"],
        color=colors,
        height=0.65,
    )

    ax.bar_label(
        bars,
        padding=5,
        fmt="%.0f",
    )

    ax.set_xlim(
        0,
        data["facility_records"].max() * 1.2,
    )

    ax.set_xlabel("수거시설 기록 수 (건)")

    ax.set_title(
        "서울시 9개 자치구 폐의약품 수거시설 기록 수",
        fontsize=15,
        fontweight="bold",
        pad=20,
    )

    ax.grid(
        axis="x",
        alpha=0.15,
    )

    fig.text(
        0.13,
        0.01,
        "주: 원본 기록 수 기준. 양천구는 2020년 자료.",
        fontsize=9,
        color="#666666",
    )

    plt.tight_layout(rect=[0, 0.05, 1, 1])

    save_figure(
        "01_facility_counts.png"
    )


# ==========================================
# 2. 인구 1만 명당 시설 기록 수
# ==========================================

def plot_facilities_per_population(df):

    data = df.sort_values(
        "facilities_per_10000",
        ascending=True,
    )

    fig, ax = plt.subplots(
        figsize=(10, 6)
    )

    colors = [
        "#2563EB" if gu != "양천구"
        else "#F59E0B"
        for gu in data["district"]
    ]

    bars = ax.barh(
        data["district"],
        data["facilities_per_10000"],
        color=colors,
        height=0.65,
    )

    for bar in bars:
        width = bar.get_width()

        ax.text(
            width + 0.025,
            bar.get_y() + bar.get_height() / 2,
            f"{width:.3f}",
            va="center",
            fontsize=10,
        )

    ax.set_xlim(
        0,
        data["facilities_per_10000"].max() * 1.2,
    )

    ax.set_xlabel(
        "인구 1만 명당 시설 기록 수 (건)"
    )

    ax.set_title(
        "자치구별 인구 대비 폐의약품 수거시설 기록 수",
        fontsize=15,
        fontweight="bold",
        pad=20,
    )

    ax.grid(
        axis="x",
        alpha=0.15,
    )

    fig.text(
        0.13,
        0.01,
        "인구: 2026년 2분기 / 시설: 자치구별 자료 기준일 상이",
        fontsize=9,
        color="#666666",
    )

    plt.tight_layout(rect=[0, 0.05, 1, 1])

    save_figure(
        "02_facilities_per_10000.png"
    )


# ==========================================
# 3. 전체 인구와 고령인구 대비 비교
# ==========================================

def plot_population_comparison(df):

    data = df.sort_values(
        "facilities_per_10000",
        ascending=False,
    )

    x = np.arange(len(data))
    width = 0.36

    fig, ax = plt.subplots(
        figsize=(12, 6)
    )

    ax.bar(
        x - width / 2,
        data["facilities_per_10000"],
        width,
        label="전체 인구 1만 명당",
        color="#2563EB",
    )

    ax.bar(
        x + width / 2,
        data["facilities_per_10000_seniors"],
        width,
        label="65세 이상 인구 1만 명당",
        color="#0D9488",
    )

    ax.set_xticks(x)
    ax.set_xticklabels(data["district"])

    ax.set_ylabel(
        "인구 1만 명당 시설 기록 수 (건)"
    )

    ax.set_title(
        "전체 인구 및 고령인구 대비 수거시설 지표",
        fontsize=15,
        fontweight="bold",
        pad=20,
    )

    ax.legend(
        frameon=False,
        loc="upper right",
    )

    ax.grid(
        axis="y",
        alpha=0.15,
    )

    fig.text(
        0.1,
        0.01,
        "두 지표는 분모가 다르므로 크기 자체보다 지역별 상대적 패턴을 해석해야 함.",
        fontsize=9,
        color="#666666",
    )

    plt.tight_layout(rect=[0, 0.05, 1, 1])

    save_figure(
        "03_population_comparison.png"
    )


# ==========================================
# 4. 양천구 포함·제외 민감도 분석
# ==========================================

def plot_sensitivity(sensitivity, disparity):

    scenarios = [
        "all_9_districts",
        "exclude_yangcheon",
    ]

    labels = [
        "9개 구 전체",
        "양천구 제외",
    ]

    s = sensitivity.set_index("scenario")
    d = disparity.set_index("scenario")

    for scenario in scenarios:
        if scenario not in s.index or scenario not in d.index:
            raise ValueError(
                f"민감도 분석 시나리오 누락: {scenario}"
            )

    # 4-A: 인구 합산 기준 비율
    rates = [
        s.loc[scenario, "pooled_population_rate"]
        for scenario in scenarios
    ]

    fig, ax = plt.subplots(
        figsize=(8, 5)
    )

    bars = ax.bar(
        labels,
        rates,
        color=["#2563EB", "#0D9488"],
        width=0.45,
    )

    ax.bar_label(
        bars,
        padding=5,
        fmt="%.4f",
    )

    ax.set_ylim(
        0,
        max(rates) * 1.25,
    )

    ax.set_ylabel(
        "인구 1만 명당 시설 기록 수 (건)"
    )

    ax.set_title(
        "양천구 포함 여부에 따른 합산 비율 비교",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    ax.grid(
        axis="y",
        alpha=0.15,
    )

    plt.tight_layout()

    save_figure(
        "04_sensitivity_pooled_rate.png"
    )

    # 4-B: 최대 / 최소 비율 비교
    ratios = [
        d.loc[scenario, "max_min_ratio"]
        for scenario in scenarios
    ]

    fig, ax = plt.subplots(
        figsize=(8, 5)
    )

    bars = ax.bar(
        labels,
        ratios,
        color=["#2563EB", "#0D9488"],
        width=0.45,
    )

    ax.bar_label(
        bars,
        padding=5,
        fmt="%.2f배",
    )

    ax.set_ylim(
        0,
        max(ratios) * 1.25,
    )

    ax.set_ylabel("최대 / 최소 비율 (배)")

    ax.set_title(
        "양천구 포함 여부에 따른 지역 간 격차",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    ax.grid(
        axis="y",
        alpha=0.15,
    )

    fig.text(
        0.1,
        0.01,
        "최솟값 지역 제외에 따른 변화이며 자료 시점의 인과효과를 뜻하지 않음.",
        fontsize=9,
        color="#666666",
    )

    plt.tight_layout(rect=[0, 0.05, 1, 1])

    save_figure(
        "05_sensitivity_disparity.png"
    )


# ==========================================
# 메인 실행
# ==========================================

def main():

    setup_style()

    district, sensitivity, disparity = load_data()

    print()
    print("=" * 60)
    print("5단계: 폐의약품 수거시설 데이터 시각화")
    print("=" * 60)

    plot_facility_counts(district)

    plot_facilities_per_population(district)

    plot_population_comparison(district)

    plot_sensitivity(
        sensitivity,
        disparity,
    )

    print()
    print("총 5개 그래프 생성 완료")
    print(f"저장 위치: {FIGURES_DIR}")


if __name__ == "__main__":
    main()
