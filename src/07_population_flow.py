
import numpy as np
import pandas as pd

from common import (
    RAW,
    PROCESSED,
    ROOT,
    DISTRICTS,
    load_csv,
    save_csv,
)


# ==========================================
# 1. 경로 및 분석 기준 설정
# ==========================================

FLOW_FILE = (
    RAW
    / "서울시 상권분석서비스(길단위인구-자치구).csv"
)

DISTRICT_FILE = (
    PROCESSED
    / "district_facility_population_2026q2.csv"
)

OUTPUT_DIR = ROOT / "reports" / "population_flow"

TARGET_QUARTER = "20262"

# 주민등록인구는 2026년 2분기
# 유동인구도 같은 분기만 활용


# ==========================================
# 2. 숫자 데이터 변환 함수
# ==========================================

def to_numeric(series, column_name):

    cleaned = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    numeric = pd.to_numeric(
        cleaned,
        errors="coerce",
    )

    if numeric.isna().any():
        raise ValueError(
            f"숫자 변환 실패: {column_name}"
        )

    return numeric


# ==========================================
# 3. 유동인구 데이터 불러오기
# ==========================================

def load_flow_population():

    if not FLOW_FILE.exists():
        raise FileNotFoundError(
            f"유동인구 파일 없음: {FLOW_FILE}"
        )

    df = load_csv(FLOW_FILE)

    required = [
        "기준_년분기_코드",
        "자치구_코드_명",
        "총_유동인구_수",
        "남성_유동인구_수",
        "여성_유동인구_수",
        "연령대_60_이상_유동인구_수",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"유동인구 컬럼 누락: {missing}"
        )

    # 2026년 2분기만 선택
    df = df[
        df["기준_년분기_코드"].astype(str).str.strip()
        == TARGET_QUARTER
    ].copy()

    if len(df) != 25:
        raise ValueError(
            f"2026년 2분기 데이터가 "
            f"25행이 아닙니다: {len(df)}행"
        )

    # 9개 분석 대상 자치구만 선택
    df["district"] = (
        df["자치구_코드_명"]
        .astype("string")
        .str.strip()
    )

    df = df[
        df["district"].isin(DISTRICTS)
    ].copy()

    if (
        len(df) != 9
        or df["district"].duplicated().any()
        or set(df["district"]) != set(DISTRICTS)
    ):
        raise ValueError(
            "9개 자치구 유동인구 추출에 문제가 있습니다."
        )

    rename_map = {
        "총_유동인구_수": "flow_total",
        "남성_유동인구_수": "flow_male",
        "여성_유동인구_수": "flow_female",
        "연령대_60_이상_유동인구_수":
            "flow_age_60_plus",
    }

    df = df.rename(columns=rename_map)

    numeric_columns = [
        "flow_total",
        "flow_male",
        "flow_female",
        "flow_age_60_plus",
    ]

    for col in numeric_columns:
        df[col] = to_numeric(
            df[col],
            col,
        )

    if (df[numeric_columns] < 0).any().any():
        raise ValueError(
            "유동인구에 음수 값이 있습니다."
        )

    # 성별 합계와 전체값 비교
    df["gender_sum"] = (
        df["flow_male"] + df["flow_female"]
    )

    df["gender_total_gap"] = (
        df["gender_sum"] - df["flow_total"]
    )

    # 60세 이상 유동인구 비중
    df["flow_age_60_plus_pct"] = np.where(
        df["flow_total"] > 0,
        df["flow_age_60_plus"]
        / df["flow_total"]
        * 100,
        np.nan,
    )

    df["flow_period"] = "2026-Q2"

    result_columns = [
        "district",
        "flow_period",
        "flow_total",
        "flow_male",
        "flow_female",
        "flow_age_60_plus",
        "flow_age_60_plus_pct",
        "gender_total_gap",
    ]

    return df[result_columns].copy()


# ==========================================
# 4. 주민등록인구 및 시설 데이터
# ==========================================

def load_district_population():

    if not DISTRICT_FILE.exists():
        raise FileNotFoundError(
            f"자치구 분석 파일 없음: {DISTRICT_FILE}"
        )

    df = load_csv(DISTRICT_FILE)

    required = [
        "district",
        "facility_records",
        "population_total",
        "population_65_plus",
    ]

    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"컬럼 누락: {col}"
            )

    df["district"] = (
        df["district"].astype("string").str.strip()
    )

    for col in required[1:]:
        df[col] = to_numeric(df[col], col)

    if (
        len(df) != 9
        or df["district"].duplicated().any()
        or set(df["district"]) != set(DISTRICTS)
    ):
        raise ValueError(
            "주민등록인구의 자치구 검증에 실패했습니다."
        )

    if (
        (df["population_total"] <= 0).any()
        or (df["population_65_plus"] <= 0).any()
    ):
        raise ValueError(
            "주민등록인구가 0 이하입니다."
        )

    return df[required].copy()


# ==========================================
# 5. 두 데이터 결합
# ==========================================

def merge_population_data(
    population,
    flow,
):

    merged = population.merge(
        flow,
        on="district",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    if not (merged["_merge"] == "both").all():
        raise ValueError(
            "주민등록인구와 유동인구 결합 실패"
        )

    merged = merged.drop(columns=["_merge"])

    if merged["flow_total"].isna().any():
        raise ValueError(
            "유동인구 누락 자치구 발견"
        )

    # 주민등록인구 내 65세 이상 비율
    merged["resident_senior_pct"] = (
        merged["population_65_plus"]
        / merged["population_total"]
        * 100
    )

    # 인구 1만 명당 수거시설 기록 수
    merged["facilities_per_10000"] = (
        merged["facility_records"]
        / merged["population_total"]
        * 10000
    )

    # 고령인구 1만 명당 수거시설 기록 수
    merged["facilities_per_10000_seniors"] = (
        merged["facility_records"]
        / merged["population_65_plus"]
        * 10000
    )

    # 유동인구 절대량 순위
    merged["flow_rank"] = (
        merged["flow_total"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    # 인구 대비 시설 지표 순위
    merged["facility_rate_rank"] = (
        merged["facilities_per_10000"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    return merged.sort_values(
        "facilities_per_10000",
        ascending=False,
    ).reset_index(drop=True)


# ==========================================
# 6. 탐색적 상관관계 분석
# ==========================================

def calculate_correlations(df):

    variables = {
        "population_total": "주민등록 총인구",
        "population_65_plus": "65세 이상 주민등록인구",
        "resident_senior_pct": "65세 이상 주민등록인구 비율",
        "flow_total": "길단위 유동인구",
        "flow_age_60_plus": "60세 이상 유동인구",
        "flow_age_60_plus_pct": "60세 이상 유동인구 비율",
        "facility_records": "시설 기록 수",
        "facilities_per_10000": "인구 1만 명당 시설 기록 수",
    }

    target = "facilities_per_10000"

    rows = []

    for col, label in variables.items():

        if col == target:
            continue

        paired = df[[col, target]].dropna()

        pearson = paired[col].corr(
            paired[target],
            method="pearson",
        )

        spearman = paired[col].corr(
            paired[target],
            method="spearman",
        )

        rows.append({
            "variable": col,
            "variable_label": label,
            "target": target,
            "district_count": len(paired),
            "pearson_r": pearson,
            "spearman_r": spearman,
        })

    return pd.DataFrame(rows)


# ==========================================
# 7. 지역별 비교 요약
# ==========================================

def create_comparison_summary(df):

    columns = [
        "district",
        "population_total",
        "population_65_plus",
        "resident_senior_pct",
        "flow_total",
        "flow_age_60_plus",
        "flow_age_60_plus_pct",
        "facility_records",
        "facilities_per_10000",
        "facilities_per_10000_seniors",
        "flow_rank",
        "facility_rate_rank",
    ]

    result = df[columns].copy()

    return result.sort_values(
        "facility_rate_rank"
    )


# ==========================================
# 8. 결과 저장
# ==========================================

def save_results(
    flow,
    merged,
    correlations,
    comparison,
):

    outputs = {
        "flow_population_2026q2.csv": flow,
        "district_population_flow_merged.csv": merged,
        "population_flow_correlations.csv": correlations,
        "district_comparison_summary.csv": comparison,
    }

    for filename, dataframe in outputs.items():

        path = OUTPUT_DIR / filename

        save_csv(
            dataframe,
            path,
        )

        print(
            f"저장 완료: {path}"
        )


# ==========================================
# 9. 실행 결과 출력
# ==========================================

def print_results(
    flow,
    merged,
    correlations,
    comparison,
):

    print()
    print("=" * 65)
    print("7단계: 주민등록인구 및 유동인구 분석")
    print("=" * 65)

    print(
        f"2026년 2분기 분석 자치구: {len(flow)}개"
    )

    print()
    print("[자치구별 비교]")

    print(
        comparison[
            [
                "district",
                "facility_records",
                "population_total",
                "flow_total",
                "resident_senior_pct",
                "facilities_per_10000",
            ]
        ]
        .round(4)
        .to_string(index=False)
    )

    print()
    print("[탐색적 상관관계]")

    print(
        correlations[
            [
                "variable_label",
                "pearson_r",
                "spearman_r",
            ]
        ]
        .round(4)
        .to_string(index=False)
    )

    print()
    print("[성별 유동인구 합계 검증]")

    print(
        flow[
            ["district", "gender_total_gap"]
        ].to_string(index=False)
    )

    print()
    print("분석 완료")
    print(f"결과 저장: {OUTPUT_DIR}")

    print()
    print("해석 시 주의사항")
    print("- 유동인구를 고유한 거주자 수로 취급하지 않습니다.")
    print("- 상관관계는 인과관계를 의미하지 않습니다.")
    print("- 분석 대상이 9개 구이므로 상관계수 해석에")
    print("  주의해야 합니다.")
    print("- 시설 데이터 기준일은 자치구별로 다릅니다.")
    print("- 실제 주민의 수거시설 이동거리는")
    print("  이번 분석에서 계산하지 않았습니다.")


# ==========================================
# 10. 메인 실행
# ==========================================

def main():

    flow = load_flow_population()

    population = load_district_population()

    merged = merge_population_data(
        population,
        flow,
    )

    correlations = calculate_correlations(
        merged
    )

    comparison = create_comparison_summary(
        merged
    )

    save_results(
        flow,
        merged,
        correlations,
        comparison,
    )

    print_results(
        flow,
        merged,
        correlations,
        comparison,
    )


if __name__ == "__main__":
    main()
