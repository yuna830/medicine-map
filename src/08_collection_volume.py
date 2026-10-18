
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
# 1. 파일 및 분석 기준 설정
# ==========================================

SOURCE_FILE = (
    RAW / "자치구별 폐의약품 수거 처리량_2024년.csv"
)

DISTRICT_FILE = (
    PROCESSED
    / "district_facility_population_2026q2.csv"
)

OUTPUT_DIR = ROOT / "reports" / "collection_volume"

MONTH_COLUMNS = [
    f"{month}월"
    for month in range(1, 13)
]

# 월별 합계와 원본 연간 합계의 비교 기준
# 반올림 가능성을 검토하기 위한 값이며
# 차이를 자동 보정하는 기준이 아님
REVIEW_TOLERANCE = 0

SOURCE_YEAR = 2024


# ==========================================
# 2. 숫자 변환
# ==========================================

def numeric_series(series, name):

    cleaned = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    result = pd.to_numeric(
        cleaned,
        errors="coerce",
    )

    if result.isna().any():
        raise ValueError(
            f"숫자 변환 실패 또는 결측치: {name}"
        )

    if (result < 0).any():
        raise ValueError(
            f"음수 데이터 발견: {name}"
        )

    return result


# ==========================================
# 3. 원본 처리량 데이터 불러오기
# ==========================================

def load_collection_data():

    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {SOURCE_FILE}"
        )

    df = load_csv(SOURCE_FILE)

    required = [
        "자치구",
        *MONTH_COLUMNS,
        "합계",
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"필수 컬럼 누락: {missing}"
        )

    df = df[required].copy()

    df["자치구"] = (
        df["자치구"]
        .astype("string")
        .str.strip()
    )

    if df["자치구"].duplicated().any():
        raise ValueError(
            "자치구 중복 행이 있습니다."
        )

    for col in [*MONTH_COLUMNS, "합계"]:
        df[col] = numeric_series(
            df[col],
            col,
        )

    # 서울시 전체 합계 행과
    # 자치구별 자료를 분리
    seoul_total = df[
        df["자치구"] == "합계"
    ].copy()

    districts = df[
        df["자치구"] != "합계"
    ].copy()

    if len(seoul_total) != 1:
        raise ValueError(
            "서울시 전체 합계 행이 정확히 1개가 아닙니다."
        )

    if len(districts) != 25:
        raise ValueError(
            f"자치구가 25개가 아닙니다: "
            f"{len(districts)}개"
        )

    if not set(DISTRICTS).issubset(
        set(districts["자치구"])
    ):
        raise ValueError(
            "분석 대상 9개 자치구가 누락됐습니다."
        )

    return districts, seoul_total


# ==========================================
# 4. 원본 연간 합계 검증
# ==========================================

def validate_annual_totals(df):

    result = df.copy()

    # 원본 월별 수치를 직접 합산
    result["monthly_sum"] = (
        result[MONTH_COLUMNS].sum(axis=1)
    )

    # 월별 합계 - 제공된 연간 합계
    result["annual_gap"] = (
        result["monthly_sum"]
        - result["합계"]
    )

    result["annual_total_matches"] = (
        result["annual_gap"].abs()
        <= REVIEW_TOLERANCE
    )

    result["annual_total_needs_review"] = (
        ~result["annual_total_matches"]
    )

    # 공식 연간 합계는 원본 그대로 유지
    result["annual_total_reported"] = (
        result["합계"]
    )

    return result


# ==========================================
# 5. 서울시 전체 합계 행 검증
# ==========================================

def validate_seoul_total(
    districts,
    seoul_total,
):

    rows = []

    for col in [*MONTH_COLUMNS, "합계"]:

        calculated = districts[col].sum()

        reported = seoul_total.iloc[0][col]

        rows.append({
            "period": col,
            "district_sum": calculated,
            "seoul_reported": reported,
            "difference": calculated - reported,
            "matches": calculated == reported,
        })

    return pd.DataFrame(rows)


# ==========================================
# 6. 월별 분석 데이터 생성
# ==========================================

def create_monthly_data(df):

    monthly = df.melt(
        id_vars=["자치구"],
        value_vars=MONTH_COLUMNS,
        var_name="month_label",
        value_name="collection_value",
    )

    monthly = monthly.rename(
        columns={
            "자치구": "district",
        }
    )

    monthly["month"] = (
        monthly["month_label"]
        .str.replace("월", "", regex=False)
        .astype(int)
    )

    monthly["year"] = SOURCE_YEAR

    monthly["quarter"] = (
        (monthly["month"] - 1) // 3 + 1
    )

    monthly["period"] = (
        monthly["year"].astype(str)
        + "-"
        + monthly["month"].astype(str).str.zfill(2)
    )

    monthly = monthly.sort_values(
        ["district", "month"]
    ).reset_index(drop=True)

    return monthly[
        [
            "district",
            "year",
            "quarter",
            "month",
            "period",
            "collection_value",
        ]
    ]


# ==========================================
# 7. 분기별 처리량
# ==========================================

def create_quarterly_data(monthly):

    quarterly = (
        monthly.groupby(
            ["district", "year", "quarter"],
            as_index=False,
        )
        .agg(
            collection_value=(
                "collection_value",
                "sum",
            )
        )
    )

    quarterly["period"] = (
        quarterly["year"].astype(str)
        + "-Q"
        + quarterly["quarter"].astype(str)
    )

    return quarterly


# ==========================================
# 8. 9개 자치구만 추출
# ==========================================

def select_target_districts(df):

    result = df[
        df["자치구"].isin(DISTRICTS)
    ].copy()

    if (
        len(result) != 9
        or set(result["자치구"]) != set(DISTRICTS)
    ):
        raise ValueError(
            "9개 자치구 추출에 실패했습니다."
        )

    return result


# ==========================================
# 9. 자치구별 연간 처리량 비교
# ==========================================

def analyze_annual_volume(df):

    result = df[
        [
            "자치구",
            "annual_total_reported",
            "monthly_sum",
            "annual_gap",
            "annual_total_needs_review",
        ]
    ].copy()

    result = result.rename(
        columns={
            "자치구": "district",
        }
    )

    # 9개 구의 원본 연간 합계 총합
    combined_total = (
        result["annual_total_reported"].sum()
    )

    result["share_pct"] = (
        result["annual_total_reported"]
        / combined_total
        * 100
    )

    result["annual_rank"] = (
        result["annual_total_reported"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    return result.sort_values(
        "annual_rank"
    ).reset_index(drop=True)


# ==========================================
# 10. 월별 변동성 분석
# ==========================================

def analyze_monthly_variation(monthly):

    result = (
        monthly.groupby("district")
        .agg(
            monthly_mean=(
                "collection_value",
                "mean",
            ),
            monthly_median=(
                "collection_value",
                "median",
            ),
            monthly_std=(
                "collection_value",
                "std",
            ),
            monthly_min=(
                "collection_value",
                "min",
            ),
            monthly_max=(
                "collection_value",
                "max",
            ),
        )
        .reset_index()
    )

    result["monthly_cv_pct"] = (
        result["monthly_std"]
        / result["monthly_mean"]
        * 100
    )

    return result.round(4)


# ==========================================
# 11. 기존 시설 데이터와 결합
# ==========================================

def compare_facility_and_volume(annual):

    if not DISTRICT_FILE.exists():
        raise FileNotFoundError(
            f"시설·인구 파일 없음: {DISTRICT_FILE}"
        )

    facility = load_csv(DISTRICT_FILE)

    required = [
        "district",
        "facility_records",
        "population_total",
        "earliest_reference_date",
        "latest_reference_date",
    ]

    missing = [
        col for col in required
        if col not in facility.columns
    ]

    if missing:
        raise ValueError(
            f"시설 데이터 컬럼 누락: {missing}"
        )

    facility = facility[required].copy()

    facility["district"] = (
        facility["district"]
        .astype("string")
        .str.strip()
    )

    for col in [
        "facility_records",
        "population_total",
    ]:
        facility[col] = numeric_series(
            facility[col],
            col,
        )

    merged = annual.merge(
        facility,
        on="district",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    if not (merged["_merge"] == "both").all():
        raise ValueError(
            "시설 데이터 결합 실패"
        )

    merged = merged.drop(
        columns="_merge"
    )

    merged["volume_year"] = SOURCE_YEAR
    merged["population_period"] = "2026-Q2"

    # 서로 다른 기준 시점 비교임을 표시
    merged["cross_period_comparison"] = True

    # 주의:
    # 2024년 처리량을 2026년 인구나
    # 다른 기준일의 시설 수로 나눈 수치를
    # '2024년 시설 효율'로 계산하지 않음

    return merged


# ==========================================
# 12. 결과 저장
# ==========================================

def save_results(
    validated,
    seoul_check,
    annual,
    monthly,
    quarterly,
    variation,
    combined,
):

    outputs = {
        "annual_total_validation.csv":
            validated,
        "seoul_total_validation.csv":
            seoul_check,
        "annual_volume_9districts.csv":
            annual,
        "monthly_volume_9districts.csv":
            monthly,
        "quarterly_volume_9districts.csv":
            quarterly,
        "monthly_variation_9districts.csv":
            variation,
        "volume_facility_comparison.csv":
            combined,
    }

    for filename, dataframe in outputs.items():

        path = OUTPUT_DIR / filename

        save_csv(dataframe, path)

        print(
            f"저장 완료: {path}"
        )


# ==========================================
# 13. 분석 결과 출력
# ==========================================

def print_results(
    validated,
    seoul_check,
    annual,
    variation,
):

    print()
    print("=" * 65)
    print("8단계: 2024년 폐의약품 수거 처리량 분석")
    print("=" * 65)

    print()
    print("[원본 연간 합계 검증]")

    print(
        f"월별 합계와 연간 합계 불일치 자치구: "
        f"{int(validated['annual_total_needs_review'].sum())}개"
    )

    print(
        validated.loc[
            validated["annual_total_needs_review"],
            ["자치구", "monthly_sum", "합계", "annual_gap"],
        ].to_string(index=False)
    )

    print()
    print("[서울시 합계 검증]")

    print(
        seoul_check.to_string(index=False)
    )

    print()
    print("[9개 구 연간 처리량 순위]")

    print(
        annual[
            [
                "district",
                "annual_total_reported",
                "share_pct",
                "annual_rank",
            ]
        ].round(3).to_string(index=False)
    )

    print()
    print("[월별 변동성]")

    print(
        variation[
            [
                "district",
                "monthly_mean",
                "monthly_std",
                "monthly_cv_pct",
            ]
        ].round(3).to_string(index=False)
    )

    print()
    print("분석 완료")
    print(f"결과 저장 경로: {OUTPUT_DIR}")

    print()
    print("주의사항:")
    print("- 처리량 원본의 공식 측정 단위 확인 필요")
    print("- 원본 연간 합계와 월별 합계 차이 자동 보정 안 함")
    print("- 시설 기록과 처리량의 기준 시점이 다름")
    print("- 처리량을 개별 시설의 수거 실적으로 해석하지 않음")


# ==========================================
# 14. 메인 실행
# ==========================================

def main():

    districts, seoul_total = (
        load_collection_data()
    )

    validated = validate_annual_totals(
        districts
    )

    seoul_check = validate_seoul_total(
        districts,
        seoul_total,
    )

    target = select_target_districts(
        validated
    )

    annual = analyze_annual_volume(
        target
    )

    monthly_all = create_monthly_data(
        districts
    )

    monthly = monthly_all[
        monthly_all["district"].isin(DISTRICTS)
    ].copy()

    quarterly = create_quarterly_data(
        monthly
    )

    variation = analyze_monthly_variation(
        monthly
    )

    combined = compare_facility_and_volume(
        annual
    )

    save_results(
        validated,
        seoul_check,
        annual,
        monthly,
        quarterly,
        variation,
        combined,
    )

    print_results(
        validated,
        seoul_check,
        annual,
        variation,
    )


if __name__ == "__main__":
    main()
