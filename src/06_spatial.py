
import numpy as np
import pandas as pd

from common import (
    INTERIM,
    ROOT,
    DISTRICTS,
    load_csv,
    save_csv,
)


# ==========================================
# 기본 설정
# ==========================================

INPUT_FILE = INTERIM / "facilities_validated.csv"

OUTPUT_DIR = ROOT / "reports" / "spatial"

EARTH_RADIUS_KM = 6371.0088

# 최근접 시설 직선거리가 1km 이상인 기록 탐색
# 공식 접근성 기준이 아닌 탐색용 임계값
DISTANCE_REVIEW_KM = 1.0


# ==========================================
# 1. 데이터 불러오기
# ==========================================

def load_facilities():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"검증 데이터 없음: {INPUT_FILE}"
        )

    df = load_csv(INPUT_FILE)

    required = [
        "record_id",
        "district",
        "name",
        "road_address",
        "latitude",
        "longitude",
        "reference_date",
        "spatial_analysis_candidate",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"필수 컬럼 누락: {missing}"
        )

    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce",
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce",
    )

    df["district"] = (
        df["district"].astype("string").str.strip()
    )

    df["spatial_analysis_candidate"] = (
        df["spatial_analysis_candidate"]
        .astype("string")
        .str.lower()
        .map({
            "true": True,
            "false": False,
        })
    )

    if df["spatial_analysis_candidate"].isna().any():
        raise ValueError(
            "공간 분석 후보 상태에 잘못된 값이 있습니다."
        )

    if df["record_id"].duplicated().any():
        raise ValueError(
            "record_id가 중복되어 있습니다."
        )

    # 좌표가 형식상 유효한 기록만 활용
    df = df[
        df["spatial_analysis_candidate"]
    ].copy()

    if not df["district"].isin(DISTRICTS).all():
        raise ValueError(
            "분석 대상 외 자치구가 포함되었습니다."
        )

    if (
        df["latitude"].isna().any()
        or df["longitude"].isna().any()
    ):
        raise ValueError(
            "분석 대상에 좌표 결측치가 있습니다."
        )

    return df.reset_index(drop=True)


# ==========================================
# 2. Haversine 거리 행렬 계산
# ==========================================

def haversine_matrix(latitudes, longitudes):

    lat = np.radians(
        np.asarray(latitudes, dtype=float)
    )

    lon = np.radians(
        np.asarray(longitudes, dtype=float)
    )

    lat1 = lat[:, None]
    lat2 = lat[None, :]

    lon1 = lon[:, None]
    lon2 = lon[None, :]

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    a = np.clip(a, 0, 1)

    distance = (
        2
        * EARTH_RADIUS_KM
        * np.arcsin(np.sqrt(a))
    )

    # 자기 자신과의 비교 제외
    np.fill_diagonal(
        distance,
        np.inf,
    )

    return distance


# ==========================================
# 3. 최근접 시설 정보 계산
# ==========================================

def add_nearest_facilities(
    df,
    distance_matrix,
):

    result = df.copy()

    # 모든 자치구를 포함한 최근접 시설
    nearest_idx = np.argmin(
        distance_matrix,
        axis=1,
    )

    nearest_distance = np.min(
        distance_matrix,
        axis=1,
    )

    result["nearest_record_id"] = (
        df.iloc[nearest_idx]["record_id"]
        .to_numpy()
    )

    result["nearest_name"] = (
        df.iloc[nearest_idx]["name"]
        .to_numpy()
    )

    result["nearest_district"] = (
        df.iloc[nearest_idx]["district"]
        .to_numpy()
    )

    result["nearest_distance_km"] = (
        nearest_distance
    )

    # 같은 자치구 안에서의 최근접 시설
    same_district_matrix = (
        distance_matrix.copy()
    )

    district_values = (
        df["district"].to_numpy()
    )

    same_district = (
        district_values[:, None]
        == district_values[None, :]
    )

    same_district_matrix[
        ~same_district
    ] = np.inf

    nearest_same_idx = np.argmin(
        same_district_matrix,
        axis=1,
    )

    nearest_same_dist = np.min(
        same_district_matrix,
        axis=1,
    )

    result["nearest_same_district_km"] = (
        nearest_same_dist
    )

    result["nearest_same_district_name"] = (
        df.iloc[nearest_same_idx]["name"]
        .to_numpy()
    )

    # 같은 구 안에 다른 시설이 없는 경우
    invalid = ~np.isfinite(
        nearest_same_dist
    )

    result.loc[
        invalid,
        "nearest_same_district_km",
    ] = np.nan

    result.loc[
        invalid,
        "nearest_same_district_name",
    ] = pd.NA

    # 다른 시설과 완전히 같은 좌표인지
    result["colocated_coordinate"] = (
        result["nearest_distance_km"] < 0.000001
    )

    # 서로 다른 좌표에 있는 최근접 시설
    # 동일 좌표 쌍이 거리 0으로 집계되는 영향을 분리
    distinct_matrix = distance_matrix.copy()

    distinct_matrix[
        distinct_matrix < 0.000001
    ] = np.inf

    distinct_min = np.min(
        distinct_matrix,
        axis=1,
    )

    result["nearest_distinct_km"] = (
        np.where(
            np.isfinite(distinct_min),
            distinct_min,
            np.nan,
        )
    )

    # 탐색용 거리 기준
    result["distance_review_candidate"] = (
        result["nearest_distinct_km"]
        >= DISTANCE_REVIEW_KM
    )

    # 단위 변환
    result["nearest_distance_m"] = (
        result["nearest_distance_km"] * 1000
    )

    result["nearest_same_district_m"] = (
        result["nearest_same_district_km"] * 1000
    )

    result["nearest_distinct_m"] = (
        result["nearest_distinct_km"] * 1000
    )

    return result


# ==========================================
# 4. 자치구별 공간 통계
# ==========================================

def calculate_district_statistics(df):

    summary = (
        df.groupby("district")
        .agg(
            facility_records=(
                "record_id",
                "count",
            ),
            mean_nearest_km=(
                "nearest_distance_km",
                "mean",
            ),
            median_nearest_km=(
                "nearest_distance_km",
                "median",
            ),
            max_nearest_km=(
                "nearest_distance_km",
                "max",
            ),
            mean_nearest_same_district_km=(
                "nearest_same_district_km",
                "mean",
            ),
            median_nearest_same_district_km=(
                "nearest_same_district_km",
                "median",
            ),
            max_nearest_same_district_km=(
                "nearest_same_district_km",
                "max",
            ),
            mean_nearest_distinct_km=(
                "nearest_distinct_km",
                "mean",
            ),
            colocated_records=(
                "colocated_coordinate",
                "sum",
            ),
            distance_review_records=(
                "distance_review_candidate",
                "sum",
            ),
        )
        .reset_index()
    )

    distance_cols = [
        col for col in summary.columns
        if col.endswith("_km")
    ]

    summary[distance_cols] = (
        summary[distance_cols].round(4)
    )

    return summary.sort_values(
        "mean_nearest_km",
        ascending=False,
    )


# ==========================================
# 5. 전체 공간 통계
# ==========================================

def calculate_overall_statistics(df):

    rows = []

    metrics = {
        "nearest_distance_km":
            "전체 최근접 시설 직선거리",
        "nearest_same_district_km":
            "동일 자치구 내 최근접 직선거리",
        "nearest_distinct_km":
            "서로 다른 좌표의 최근접 직선거리",
    }

    for col, label in metrics.items():

        values = df[col].dropna()

        rows.append({
            "metric": col,
            "label": label,
            "count": len(values),
            "mean_km": values.mean(),
            "median_km": values.median(),
            "std_km": values.std(ddof=1),
            "min_km": values.min(),
            "max_km": values.max(),
        })

    return pd.DataFrame(rows).round(4)


# ==========================================
# 6. 분석 결과 저장
# ==========================================

def save_results(
    facilities,
    district_summary,
    overall_summary,
):

    save_csv(
        facilities,
        OUTPUT_DIR / "facility_nearest_distances.csv",
    )

    save_csv(
        district_summary,
        OUTPUT_DIR / "district_spatial_summary.csv",
    )

    save_csv(
        overall_summary,
        OUTPUT_DIR / "overall_spatial_statistics.csv",
    )

    # 동일 좌표 기록
    save_csv(
        facilities[
            facilities["colocated_coordinate"]
        ],
        OUTPUT_DIR / "colocated_facilities.csv",
    )

    # 최근접 다른 좌표의 시설까지
    # 1km 이상인 기록
    save_csv(
        facilities[
            facilities["distance_review_candidate"]
        ].sort_values(
            "nearest_distinct_km",
            ascending=False,
        ),
        OUTPUT_DIR / "distance_review_candidates.csv",
    )


# ==========================================
# 7. 결과 출력
# ==========================================

def print_results(
    facilities,
    district_summary,
    overall_summary,
):

    print()
    print("=" * 65)
    print("6단계: 폐의약품 수거시설 공간 분석")
    print("=" * 65)

    print(
        f"공간 분석 기록: {len(facilities)}건"
    )

    print(
        "동일 좌표 기록:",
        int(
            facilities["colocated_coordinate"].sum()
        ),
    )

    print(
        f"최근접 다른 좌표의 시설까지 "
        f"{DISTANCE_REVIEW_KM}km 이상:",
        int(
            facilities[
                "distance_review_candidate"
            ].sum()
        ),
    )

    print()
    print("[자치구별 공간 통계]")

    print(
        district_summary[
            [
                "district",
                "facility_records",
                "mean_nearest_km",
                "median_nearest_km",
                "max_nearest_km",
            ]
        ].to_string(index=False)
    )

    print()
    print("[전체 공간 통계]")

    print(
        overall_summary.to_string(
            index=False
        )
    )

    print()
    print(f"분석 결과 저장 완료: {OUTPUT_DIR}")

    print()
    print("주의사항:")
    print("- 거리는 직선거리이며 도보거리가 아닙니다.")
    print("- 시설 기준 거리이므로 주민 접근성을")
    print("  직접 측정한 지표가 아닙니다.")
    print("- 양천구는 좌표가 없어 이번 분석에서 제외됐습니다.")
    print("- 좌표 정확성과 운영 여부는 별도 검증이 필요합니다.")


# ==========================================
# 메인 실행
# ==========================================

def main():

    facilities = load_facilities()

    # 분석 대상이 충분한지 검사
    if len(facilities) < 2:
        raise ValueError(
            "거리 분석에 최소 2개 시설이 필요합니다."
        )

    # 전체 시설 간 거리 행렬
    distance_matrix = haversine_matrix(
        facilities["latitude"],
        facilities["longitude"],
    )

    # 최근접 거리 계산
    spatial_result = add_nearest_facilities(
        facilities,
        distance_matrix,
    )

    # 자치구별 결과
    district_summary = (
        calculate_district_statistics(
            spatial_result
        )
    )

    # 전체 결과
    overall_summary = (
        calculate_overall_statistics(
            spatial_result
        )
    )

    # CSV 저장
    save_results(
        spatial_result,
        district_summary,
        overall_summary,
    )

    # 결과 출력
    print_results(
        spatial_result,
        district_summary,
        overall_summary,
    )


if __name__ == "__main__":
    main()
