
import pandas as pd

from common import (
    INTERIM,
    AUDIT,
    DISTRICTS,
    load_csv,
    save_csv,
)


INPUT_FILE = INTERIM / "facilities_standardized.csv"

# 비교용 인구 통계 기준일
POPULATION_REFERENCE_DATE = pd.Timestamp("2026-06-30")

# 오래된 시설 데이터에 대한 별도 검토 기준
STALE_THRESHOLD = pd.Timestamp("2024-07-01")

# 서울시 주변의 대략적인 좌표 범위
SEOUL_LAT_MIN = 37.40
SEOUL_LAT_MAX = 37.75
SEOUL_LON_MIN = 126.75
SEOUL_LON_MAX = 127.25


def clean_text(series):
    return (
        series.astype("string")
        .str.strip()
        .replace({"": pd.NA, "-": pd.NA})
    )


def validate_basic(df):
    df = df.copy()

    required = [
        "record_id",
        "name",
        "district",
        "road_address",
        "latitude",
        "longitude",
        "reference_date",
        "source_file",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing}")

    if df["record_id"].isna().any():
        raise ValueError("record_id 결측치 발견")

    if df["record_id"].duplicated().any():
        raise ValueError("record_id 중복 발견")

    for col in ["name", "district", "road_address", "source_file"]:
        df[col] = clean_text(df[col])

    for col in ["latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["reference_date"] = pd.to_datetime(
        df["reference_date"],
        errors="coerce",
    )

    return df


def validate_quality(df):
    df = df.copy()

    # 1. 자치구 및 주소 검사
    df["valid_district"] = df["district"].isin(DISTRICTS)

    df["address_matches_district"] = [
        pd.notna(address)
        and pd.notna(district)
        and str(district) in str(address)
        for address, district in zip(
            df["road_address"],
            df["district"],
        )
    ]

    df["address_needs_review"] = (
        ~df["valid_district"]
        | ~df["address_matches_district"]
        | df["name"].isna()
    )

    # 2. 좌표 검사
    df["has_coordinates"] = (
        df["latitude"].notna()
        & df["longitude"].notna()
    )

    df["valid_global_coordinates"] = (
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
    )

    df["in_seoul_bbox"] = (
        df["latitude"].between(SEOUL_LAT_MIN, SEOUL_LAT_MAX)
        & df["longitude"].between(SEOUL_LON_MIN, SEOUL_LON_MAX)
    )

    df["coordinate_needs_review"] = (
        ~df["has_coordinates"]
        | ~df["valid_global_coordinates"]
        | ~df["in_seoul_bbox"]
    )

    # 3. 동일 좌표와 동일 주소 검사
    df["same_coordinate"] = False

    coordinate_mask = df["has_coordinates"]

    df.loc[coordinate_mask, "same_coordinate"] = (
        df.loc[coordinate_mask]
        .duplicated(
            subset=["latitude", "longitude"],
            keep=False,
        )
        .to_numpy()
    )

    # 주소가 없는 행끼리 중복으로 묶이지 않도록 처리
    df["same_address"] = False

    address_mask = df["road_address"].notna()

    df.loc[address_mask, "same_address"] = (
        df.loc[address_mask]
        .duplicated(
            subset=["district", "road_address"],
            keep=False,
        )
        .to_numpy()
    )

    # 4. 데이터 품질 검토 대상
    df["data_quality_review"] = (
        df["address_needs_review"]
        | df["coordinate_needs_review"]
        | df["same_coordinate"]
        | df["same_address"]
    )

    return df


def validate_time(df):
    df = df.copy()

    df["missing_reference_date"] = (
        df["reference_date"].isna()
    )

    df["stale_reference_date"] = (
        df["reference_date"] < STALE_THRESHOLD
    )

    df["after_population_period"] = (
        df["reference_date"] > POPULATION_REFERENCE_DATE
    )

    df["reference_gap_days"] = (
        df["reference_date"]
        - POPULATION_REFERENCE_DATE
    ).dt.days

    df["temporal_review"] = (
        df["missing_reference_date"]
        | df["stale_reference_date"]
        | df["after_population_period"]
    )

    return df


def classify_records(df):
    df = df.copy()

    # 시설 기록 수 집계 후보: 좌표가 없어도 집계 가능
    df["count_analysis_candidate"] = (
        df["valid_district"]
        & df["name"].notna()
        & df["road_address"].notna()
    )

    # 공간 분석 후보: 좌표가 유효한 기록만
    df["spatial_analysis_candidate"] = (
        df["count_analysis_candidate"]
        & df["valid_global_coordinates"]
        & df["in_seoul_bbox"]
        & ~df["address_needs_review"]
    )

    df["manual_review_required"] = (
        df["data_quality_review"]
        | df["temporal_review"]
    )

    def get_reasons(row):
        reasons = []

        checks = {
            "ADDRESS_REVIEW": "address_needs_review",
            "COORDINATE_REVIEW": "coordinate_needs_review",
            "SAME_COORDINATE": "same_coordinate",
            "SAME_ADDRESS": "same_address",
            "MISSING_DATE": "missing_reference_date",
            "OLD_REFERENCE_DATE": "stale_reference_date",
            "AFTER_POPULATION_PERIOD": "after_population_period",
        }

        for reason, column in checks.items():
            if bool(row[column]):
                reasons.append(reason)

        return ";".join(reasons)

    df["review_reasons"] = df.apply(
        get_reasons,
        axis=1,
    )

    return df


def create_summary(df):
    summary = (
        df.groupby("district", dropna=False)
        .agg(
            total_records=("record_id", "count"),
            coordinate_available=("has_coordinates", "sum"),
            quality_review_records=("data_quality_review", "sum"),
            temporal_review_records=("temporal_review", "sum"),
            count_candidates=("count_analysis_candidate", "sum"),
            spatial_candidates=("spatial_analysis_candidate", "sum"),
            manual_review_records=("manual_review_required", "sum"),
            oldest_reference_date=("reference_date", "min"),
            newest_reference_date=("reference_date", "max"),
        )
        .reset_index()
    )

    for col in [
        "oldest_reference_date",
        "newest_reference_date",
    ]:
        summary[col] = summary[col].dt.strftime("%Y-%m-%d")

    summary["coordinate_coverage_pct"] = (
        summary["coordinate_available"]
        / summary["total_records"]
        * 100
    ).round(2)

    return summary


def save_results(df, summary):
    save_csv(
        df,
        INTERIM / "facilities_validated.csv",
    )

    save_csv(
        summary,
        AUDIT / "district_validation_summary.csv",
    )

    exports = {
        "data_quality_review.csv": df["data_quality_review"],
        "temporal_review.csv": df["temporal_review"],
        "manual_review_required.csv": df["manual_review_required"],
        "same_coordinate_facilities.csv": df["same_coordinate"],
        "same_address_facilities.csv": df["same_address"],
        "address_review.csv": df["address_needs_review"],
        "coordinate_review.csv": df["coordinate_needs_review"],
        "reference_date_review.csv": df["temporal_review"],
    }

    for filename, mask in exports.items():
        save_csv(
            df.loc[mask],
            AUDIT / filename,
        )


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"전처리 파일을 찾을 수 없습니다: {INPUT_FILE}"
        )

    df = load_csv(INPUT_FILE)
    df = validate_basic(df)
    df = validate_quality(df)
    df = validate_time(df)
    df = classify_records(df)

    summary = create_summary(df)

    save_results(df, summary)

    print("\n=== 3단계 데이터 검증 결과 ===")
    print(f"전체 기록: {len(df)}건")

    metrics = {
        "좌표 보유": "has_coordinates",
        "데이터 품질 검토": "data_quality_review",
        "기준일 검토": "temporal_review",
        "수동 검토 전체": "manual_review_required",
        "시설 수 분석 후보": "count_analysis_candidate",
        "공간 분석 후보": "spatial_analysis_candidate",
    }

    for label, column in metrics.items():
        print(f"{label}: {int(df[column].sum())}건")

    print("\n=== 자치구별 검증 결과 ===")
    print(
        summary[
            [
                "district",
                "total_records",
                "quality_review_records",
                "temporal_review_records",
                "spatial_candidates",
            ]
        ].to_string(index=False)
    )

    print(f"\n결과 저장: {AUDIT}")


if __name__ == "__main__":
    main()
