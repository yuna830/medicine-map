
import pandas as pd

from common import (
    PROCESSED,
    INTERIM,
    ROOT,
    DISTRICTS,
    load_csv,
    save_csv,
)


# ==========================================
# 파일 경로
# ==========================================

DISTRICT_FILE = (
    PROCESSED
    / "district_facility_population_2026q2.csv"
)

VALIDATED_FILE = (
    INTERIM / "facilities_validated.csv"
)

ANALYSIS_DIR = ROOT / "reports" / "analysis"

# 오래된 양천구 데이터 제외 비교
EXCLUDED_DISTRICT = "양천구"


# ==========================================
# 1. 분석용 데이터 불러오기
# ==========================================

def load_analysis_data():

    for path in [DISTRICT_FILE, VALIDATED_FILE]:
        if not path.exists():
            raise FileNotFoundError(
                f"필요한 파일이 없습니다: {path}"
            )

    district = load_csv(DISTRICT_FILE)
    facilities = load_csv(VALIDATED_FILE)

    numeric_columns = [
        "facility_records",
        "population_total",
        "population_65_plus",
        "facilities_per_10000",
        "facilities_per_10000_seniors",
    ]

    for col in numeric_columns:

        if col not in district.columns:
            raise ValueError(
                f"분석 컬럼 누락: {col}"
            )

        district[col] = pd.to_numeric(
            district[col],
            errors="coerce",
        )

    district["district"] = (
        district["district"].astype(str).str.strip()
    )

    facilities["district"] = (
        facilities["district"].astype(str).str.strip()
    )

    if district["district"].duplicated().any():
        raise ValueError(
            "자치구별 데이터에 중복이 있습니다."
        )

    if (
        set(district["district"]) != set(DISTRICTS)
        or len(district) != len(DISTRICTS)
    ):
        raise ValueError(
            "분석 대상 9개 자치구가 일치하지 않습니다."
        )

    if (
        district[numeric_columns].isna().any().any()
        or (district["population_total"] <= 0).any()
        or (district["population_65_plus"] <= 0).any()
    ):
        raise ValueError(
            "인구 또는 시설 지표에 잘못된 값이 있습니다."
        )

    # 집계된 시설 기록 수가 실제 파일과 같은지 검증
    actual_counts = (
        facilities.groupby("district")
        .size()
        .to_dict()
    )

    for _, row in district.iterrows():

        actual = actual_counts.get(
            row["district"], 0
        )

        expected = int(
            row["facility_records"]
        )

        if actual != expected:
            raise ValueError(
                f"{row['district']} 시설 건수 불일치: "
                f"집계 {expected}, 실제 {actual}"
            )

    return district, facilities


# ==========================================
# 2. 자치구별 분석
# ==========================================

def analyze_districts(district):

    result = district.copy()

    # 인구 대비 지표 재계산
    result["facilities_per_10000"] = (
        result["facility_records"]
        / result["population_total"]
        * 10000
    )

    result["facilities_per_10000_seniors"] = (
        result["facility_records"]
        / result["population_65_plus"]
        * 10000
    )

    # 고령인구 비율
    result["senior_population_pct"] = (
        result["population_65_plus"]
        / result["population_total"]
        * 100
    )

    # 인구 대비 설치 기록 수 순위
    result["rank_per_10000"] = (
        result["facilities_per_10000"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    # 고령인구 대비 설치 기록 수 순위
    result["rank_per_10000_seniors"] = (
        result["facilities_per_10000_seniors"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    result = result.sort_values(
        "facilities_per_10000",
        ascending=False,
    ).reset_index(drop=True)

    return result


# ==========================================
# 3. 기초 통계량 계산
# ==========================================

def calculate_statistics(df, scenario):

    metrics = {
        "facility_records": "시설 기록 수",
        "population_total": "총인구",
        "population_65_plus": "65세 이상 인구",
        "facilities_per_10000": "인구 1만 명당 시설 기록 수",
        "facilities_per_10000_seniors":
            "65세 이상 인구 1만 명당 시설 기록 수",
        "senior_population_pct": "65세 이상 인구 비율",
    }

    rows = []

    for column, label in metrics.items():

        values = df[column].dropna()

        rows.append({
            "scenario": scenario,
            "metric": column,
            "metric_label": label,
            "district_count": len(values),
            "mean": values.mean(),
            "median": values.median(),
            "std": values.std(ddof=1),
            "min": values.min(),
            "max": values.max(),
            "range": values.max() - values.min(),
        })

    return pd.DataFrame(rows)


# ==========================================
# 4. 최대 / 최소 격차 분석
# ==========================================

def analyze_disparity(df, scenario):

    column = "facilities_per_10000"

    high = df.loc[
        df[column].idxmax()
    ]

    low = df.loc[
        df[column].idxmin()
    ]

    high_value = float(high[column])
    low_value = float(low[column])

    ratio = (
        high_value / low_value
        if low_value > 0
        else float("nan")
    )

    return {
        "scenario": scenario,
        "highest_district": high["district"],
        "highest_value": high_value,
        "lowest_district": low["district"],
        "lowest_value": low_value,
        "absolute_gap": high_value - low_value,
        "max_min_ratio": ratio,
    }


# ==========================================
# 5. 양천구 제외 민감도 분석
# ==========================================

def sensitivity_analysis(df):

    all_districts = df.copy()

    without_yangcheon = df[
        df["district"] != EXCLUDED_DISTRICT
    ].copy()

    datasets = {
        "all_9_districts": all_districts,
        "exclude_yangcheon": without_yangcheon,
    }

    statistics = []
    disparity = []
    sensitivity = []

    for scenario, subset in datasets.items():

        statistics.append(
            calculate_statistics(
                subset,
                scenario,
            )
        )

        disparity.append(
            analyze_disparity(
                subset,
                scenario,
            )
        )

        # 자치구별 지표의 단순 평균과
        # 인구를 가중치로 반영한 합산 비율 구분
        unweighted_mean = (
            subset["facilities_per_10000"].mean()
        )

        pooled_rate = (
            subset["facility_records"].sum()
            / subset["population_total"].sum()
            * 10000
        )

        sensitivity.append({
            "scenario": scenario,
            "district_count": len(subset),
            "total_facility_records": int(
                subset["facility_records"].sum()
            ),
            "total_population": int(
                subset["population_total"].sum()
            ),
            "unweighted_mean_rate": unweighted_mean,
            "pooled_population_rate": pooled_rate,
            "median_rate": (
                subset["facilities_per_10000"].median()
            ),
            "std_rate": (
                subset["facilities_per_10000"].std(ddof=1)
            ),
        })

    return (
        pd.concat(statistics, ignore_index=True),
        pd.DataFrame(disparity),
        pd.DataFrame(sensitivity),
    )


# ==========================================
# 6. 데이터 품질 관련 집계
# ==========================================

def analyze_quality(facilities):

    flag_columns = [
        "data_quality_review",
        "temporal_review",
        "count_analysis_candidate",
        "spatial_analysis_candidate",
        "same_coordinate",
        "same_address",
        "coordinate_needs_review",
    ]

    for col in flag_columns:

        if col not in facilities.columns:
            raise ValueError(
                f"검증 컬럼이 없습니다: {col}"
            )

        facilities[col] = (
            facilities[col]
            .astype("string")
            .str.lower()
            .map({
                "true": True,
                "false": False,
            })
        )

        if facilities[col].isna().any():
            raise ValueError(
                f"검증 상태 변환 실패: {col}"
            )

    result = (
        facilities.groupby("district")
        .agg(
            total_records=("record_id", "count"),
            quality_review_records=(
                "data_quality_review", "sum"
            ),
            temporal_review_records=(
                "temporal_review", "sum"
            ),
            count_candidates=(
                "count_analysis_candidate", "sum"
            ),
            spatial_candidates=(
                "spatial_analysis_candidate", "sum"
            ),
            same_coordinate_records=(
                "same_coordinate", "sum"
            ),
            same_address_records=(
                "same_address", "sum"
            ),
            coordinate_review_records=(
                "coordinate_needs_review", "sum"
            ),
        )
        .reset_index()
    )

    return result


# ==========================================
# 7. 결과 저장
# ==========================================

def save_analysis(
    district_results,
    statistics,
    disparity,
    sensitivity,
    quality,
):

    outputs = {
        "district_analysis.csv": district_results,
        "descriptive_statistics.csv": statistics,
        "disparity_analysis.csv": disparity,
        "sensitivity_analysis.csv": sensitivity,
        "quality_analysis.csv": quality,
    }

    for filename, dataframe in outputs.items():

        path = ANALYSIS_DIR / filename

        save_csv(
            dataframe,
            path,
        )

        print(f"저장 완료: {path}")


# ==========================================
# 8. 결과 출력
# ==========================================

def print_results(
    district_results,
    disparity,
    sensitivity,
):

    print()
    print("=" * 65)
    print("4단계: 폐의약품 수거시설 기초 통계 분석")
    print("=" * 65)

    print("\n[자치구별 인구 대비 시설 기록 수]")

    columns = [
        "district",
        "facility_records",
        "population_total",
        "facilities_per_10000",
        "facilities_per_10000_seniors",
        "rank_per_10000",
    ]

    print(
        district_results[columns]
        .round(4)
        .to_string(index=False)
    )

    print("\n[지역 간 격차]")

    print(
        disparity.round(4).to_string(index=False)
    )

    print("\n[양천구 제외 민감도 분석]")

    print(
        sensitivity.round(4).to_string(index=False)
    )

    print()
    print("주의사항:")
    print("- 시설 수는 원본 기록 수 기준입니다.")
    print("- 자치구별 시설 기준일이 서로 다릅니다.")
    print("- 인구 데이터는 2026년 2분기 기준입니다.")
    print("- 민감도 분석은 자료 시점 차이의 영향을")
    print("  탐색하기 위한 비교이며 인과 분석이 아닙니다.")


# ==========================================
# 메인 실행
# ==========================================

def main():

    district, facilities = load_analysis_data()

    district_results = analyze_districts(
        district
    )

    statistics, disparity, sensitivity = (
        sensitivity_analysis(
            district_results
        )
    )

    quality = analyze_quality(
        facilities
    )

    save_analysis(
        district_results,
        statistics,
        disparity,
        sensitivity,
        quality,
    )

    print_results(
        district_results,
        disparity,
        sensitivity,
    )


if __name__ == "__main__":
    main()
