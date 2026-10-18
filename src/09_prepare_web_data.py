
import json
import math

from pathlib import Path
from collections import Counter

import pandas as pd

from common import (
    ROOT,
    DISTRICTS,
    load_csv,
)


# ==========================================
# 1. 파일 경로
# ==========================================

# 기존 검증 데이터
# record_id와 데이터 품질 정보를 유지하기 위해 사용
BASE_FACILITY_FILE = (
    ROOT / "data" / "interim"
    / "facilities_validated.csv"
)

# 12단계에서 양천구 좌표 6건을 병합한 파일
FACILITY_FILE = (
    ROOT / "data" / "processed"
    / "facilities_geocoded.csv"
)

# 14단계에서 233건으로 재계산한 공간 분석
SPATIAL_FILE = (
    ROOT / "reports" / "spatial"
    / "facility_nearest_distances.csv"
)

DISTRICT_FILE = (
    ROOT / "reports" / "analysis"
    / "district_analysis.csv"
)

QUALITY_FILE = (
    ROOT / "reports" / "analysis"
    / "quality_analysis.csv"
)

FLOW_FILE = (
    ROOT / "reports" / "population_flow"
    / "district_population_flow_merged.csv"
)

VOLUME_FILE = (
    ROOT / "reports" / "collection_volume"
    / "annual_volume_9districts.csv"
)

MONTHLY_FILE = (
    ROOT / "reports" / "collection_volume"
    / "monthly_volume_9districts.csv"
)

OUTPUT_DIR = ROOT / "data" / "web"

EXPECTED_FACILITIES = 233
EXPECTED_DISTRICTS = 9
EXPECTED_MONTHLY = 108


# ==========================================
# 2. 공통 함수
# ==========================================

def read_required(path, columns):

    if not path.exists():
        raise FileNotFoundError(
            f"필요한 파일이 없습니다: {path}"
        )

    df = load_csv(path)

    missing = [
        col
        for col in columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"{path.name} 필수 컬럼 누락: {missing}"
        )

    return df


def to_number(df, columns):

    df = df.copy()

    for col in columns:
        df[col] = pd.to_numeric(
            df[col],
            errors="raise",
        )

    return df


def to_boolean(df, columns):

    df = df.copy()

    for col in columns:

        values = (
            df[col]
            .astype("string")
            .str.strip()
            .str.lower()
        )

        invalid = (
            values.notna()
            & ~values.isin(["true", "false"])
        )

        if invalid.any():
            raise ValueError(
                f"Boolean 변환 실패: {col}"
            )

        df[col] = values.map({
            "true": True,
            "false": False,
        })

    return df


def verify_unique(df, key, label):

    if df[key].isna().any():
        raise ValueError(
            f"{label}: {key} 결측치"
        )

    if df[key].duplicated().any():
        raise ValueError(
            f"{label}: {key} 중복"
        )


def verify_districts(df, label):

    actual = set(df["district"])
    expected = set(DISTRICTS)

    if actual != expected:
        raise ValueError(
            f"{label} 자치구 불일치: "
            f"누락={expected - actual}, "
            f"추가={actual - expected}"
        )


def merge_one_to_one(left, right, key):

    merged = left.merge(
        right,
        on=key,
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    if not (
        merged["_merge"] == "both"
    ).all():

        missing = merged.loc[
            merged["_merge"] != "both",
            key,
        ].tolist()

        raise ValueError(
            f"{key} 연결 실패: {missing}"
        )

    return merged.drop(
        columns=["_merge"]
    )


def save_json(dataframe_or_object, filename):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = OUTPUT_DIR / filename

    if isinstance(
        dataframe_or_object,
        pd.DataFrame,
    ):

        content = json.loads(
            dataframe_or_object.to_json(
                orient="records",
                force_ascii=False,
                date_format="iso",
            )
        )

    else:
        content = dataframe_or_object

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            content,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

    print(f"저장 완료: {path}")


def normalize_identity(value):

    return (
        str(value)
        .strip()
        .replace(" ", "")
    )


def haversine_km(lat1, lon1, lat2, lon2):

    radius = 6371.0088

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(delta_lon / 2) ** 2
    )

    a = min(1.0, max(0.0, a))

    return (
        2
        * radius
        * math.asin(math.sqrt(a))
    )


# ==========================================
# 3. 시설별 웹 데이터 생성
# ==========================================

def prepare_facilities():

    # 기존 데이터의 record_id 및 품질 정보를 유지
    facility_columns = [
        "record_id",
        "district",
        "name",
        "road_address",
        "latitude",
        "longitude",
        "reference_date",
        "source_file",
        "data_quality_review",
        "temporal_review",
        "count_analysis_candidate",
        "spatial_analysis_candidate",
        "same_coordinate",
        "same_address",
        "review_reasons",
    ]

    facilities = read_required(
        BASE_FACILITY_FILE,
        facility_columns,
    ).copy()

    # 좌표 병합 결과
    geocoded = read_required(
        FACILITY_FILE,
        [
            "district",
            "latitude",
            "longitude",
        ],
    ).copy()

    # 14단계 공간 분석 결과
    spatial_columns = [
        "record_number",
        "district",
        "facility_name",
        "latitude",
        "longitude",
        "nearest_record_number",
        "nearest_facility",
        "nearest_district",
        "nearest_distance_km",
        "nearest_distinct_distance_km",
    ]

    spatial = read_required(
        SPATIAL_FILE,
        spatial_columns,
    ).copy()

    # ======================================
    # 기록 수 검사
    # ======================================

    if len(facilities) != EXPECTED_FACILITIES:
        raise ValueError(
            "기존 검증 시설 수가 233건이 아닙니다."
        )

    if len(geocoded) != EXPECTED_FACILITIES:
        raise ValueError(
            "좌표 병합 시설 수가 233건이 아닙니다."
        )

    if len(spatial) != EXPECTED_FACILITIES:
        raise ValueError(
            "공간 분석 기록 수가 233건이 아닙니다."
        )

    verify_unique(
        facilities,
        "record_id",
        "시설",
    )

    verify_unique(
        spatial,
        "record_number",
        "공간 분석",
    )

    # ======================================
    # 숫자 및 Boolean 변환
    # ======================================

    facilities = to_number(
        facilities,
        ["record_id"],
    )

    facilities = to_boolean(
        facilities,
        [
            "data_quality_review",
            "temporal_review",
            "count_analysis_candidate",
            "spatial_analysis_candidate",
            "same_coordinate",
            "same_address",
        ],
    )

    geocoded = to_number(
        geocoded,
        [
            "latitude",
            "longitude",
        ],
    )

    spatial = to_number(
        spatial,
        [
            "record_number",
            "nearest_record_number",
            "latitude",
            "longitude",
            "nearest_distance_km",
            "nearest_distinct_distance_km",
        ],
    )

    # ======================================
    # 시설명 컬럼 확인
    # ======================================

    if "name" in geocoded.columns:
        geocoded_name_col = "name"

    elif "facility_name" in geocoded.columns:
        geocoded_name_col = "facility_name"

    else:
        raise ValueError(
            "facilities_geocoded.csv에 "
            "시설명 컬럼이 없습니다."
        )

    # ======================================
    # 공간 분석 행 번호 검사
    # ======================================

    spatial = spatial.sort_values(
        "record_number"
    ).reset_index(drop=True)

    expected_numbers = list(
        range(1, EXPECTED_FACILITIES + 1)
    )

    actual_numbers = (
        spatial["record_number"]
        .astype(int)
        .tolist()
    )

    if actual_numbers != expected_numbers:
        raise ValueError(
            "14단계 record_number가 "
            "1~233의 연속 번호가 아닙니다."
        )

    # ======================================
    # 병합 파일과 기존 기록 일치 검사
    # ======================================

    # 12단계 병합과 14단계 분석은
    # 기존 standardized 데이터의 행 순서를 유지함.
    #
    # 여기서는 validated 파일도 같은 순서인지
    # 자치구와 시설명으로 검증합니다.
    #
    # 순서가 다르면 잘못된 좌표를 연결하지 않고
    # 작업을 중단합니다.

    for index in range(EXPECTED_FACILITIES):

        base = facilities.iloc[index]
        geo = geocoded.iloc[index]
        spa = spatial.iloc[index]

        base_district = normalize_identity(
            base["district"]
        )

        base_name = normalize_identity(
            base["name"]
        )

        geo_district = normalize_identity(
            geo["district"]
        )

        geo_name = normalize_identity(
            geo[geocoded_name_col]
        )

        spa_district = normalize_identity(
            spa["district"]
        )

        spa_name = normalize_identity(
            spa["facility_name"]
        )

        if (
            base_district != geo_district
            or base_district != spa_district
            or base_name != geo_name
            or base_name != spa_name
        ):
            raise ValueError(
                f"{index + 1}행 시설 정보 불일치.\n"
                "facilities_validated.csv와 "
                "facilities_geocoded.csv의 "
                "행 순서 또는 시설명이 다릅니다.\n"
                "잘못된 좌표 병합을 방지하기 위해 "
                "작업을 중단합니다."
            )

        # 새 좌표와 공간 분석 좌표 비교
        for col in [
            "latitude",
            "longitude",
        ]:

            geo_value = float(
                geo[col]
            )

            spatial_value = float(
                spa[col]
            )

            if not math.isclose(
                geo_value,
                spatial_value,
                rel_tol=0,
                abs_tol=1e-6,
            ):
                raise ValueError(
                    f"{index + 1}행 좌표 불일치: {col}"
                )

    print(
        "시설 식별 정보와 공간 분석 좌표 일치"
    )

    # ======================================
    # 검증된 좌표 반영
    # ======================================

    result = facilities.copy()

    result["latitude"] = (
        geocoded["latitude"].to_numpy()
    )

    result["longitude"] = (
        geocoded["longitude"].to_numpy()
    )

    if result[
        ["latitude", "longitude"]
    ].isna().any().any():
        raise ValueError(
            "보정 후 좌표 누락이 있습니다."
        )

    # 양천구를 포함한 233건 모두
    # 공간 분석 및 지도 표시 대상
    result["spatial_analysis_candidate"] = True

    result["map_marker_available"] = True

    result["operation_verified"] = False

    result["location_status"] = (
        "COORDINATES_AVAILABLE"
    )

    result["data_notice"] = (
        "공공데이터에 기록된 시설입니다. "
        "현재 운영 여부는 별도로 확인해야 합니다."
    )

    # ======================================
    # 14단계 공간 분석 ID 연결
    # ======================================

    # 14단계 record_number는 행 번호이며
    # 기존 record_id와 다를 수 있음.
    #
    # 기존 웹사이트의 ID를 유지하도록
    # 행 번호 -> record_id로 변환합니다.

    id_by_row_number = dict(
        enumerate(
            result["record_id"].astype(int),
            start=1,
        )
    )

    result["nearest_record_id"] = (
        spatial["nearest_record_number"]
        .map(id_by_row_number)
    )

    if result["nearest_record_id"].isna().any():
        raise ValueError(
            "최근접 시설 ID 연결 실패"
        )

    result["nearest_record_id"] = (
        result["nearest_record_id"].astype(int)
    )

    result["nearest_name"] = (
        spatial["nearest_facility"].to_numpy()
    )

    result["nearest_district"] = (
        spatial["nearest_district"].to_numpy()
    )

    result["nearest_distance_km"] = (
        spatial["nearest_distance_km"].to_numpy()
    )

    result["nearest_distinct_km"] = (
        spatial[
            "nearest_distinct_distance_km"
        ].to_numpy()
    )

    # ======================================
    # 자치구 내부 최근접 거리 계산
    # ======================================

    # 기존 웹 JSON의
    # nearest_same_district_km 필드를 유지.
    #
    # 전체 9개 구에서 찾은 최근접 시설과
    # 같은 자치구 안에서 찾은 최근접 시설은
    # 서로 다를 수 있습니다.

    same_district_distances = []

    records = result.to_dict(
        orient="records"
    )

    for index, current in enumerate(records):

        nearest = math.inf

        for other_index, other in enumerate(records):

            if index == other_index:
                continue

            if (
                current["district"]
                != other["district"]
            ):
                continue

            distance = haversine_km(
                current["latitude"],
                current["longitude"],
                other["latitude"],
                other["longitude"],
            )

            if distance < nearest:
                nearest = distance

        if not math.isfinite(nearest):
            same_district_distances.append(
                float("nan")
            )
        else:
            same_district_distances.append(
                nearest
            )

    result["nearest_same_district_km"] = (
        same_district_distances
    )

    # ======================================
    # 거리 m 단위 추가
    # ======================================

    for col in [
        "nearest_distance_km",
        "nearest_same_district_km",
        "nearest_distinct_km",
    ]:

        new_col = col.replace(
            "_km",
            "_m",
        )

        result[new_col] = (
            result[col] * 1000
        ).round(1)

    # ======================================
    # 동일 좌표 여부 재계산
    # ======================================

    coordinate_keys = list(
        zip(
            result["latitude"].round(7),
            result["longitude"].round(7),
        )
    )

    coordinate_counts = Counter(
        coordinate_keys
    )

    result["same_coordinate"] = [
        coordinate_counts[key] > 1
        for key in coordinate_keys
    ]

    # ======================================
    # 좌표 보완 출처
    # ======================================

    if "coordinate_source" in geocoded.columns:

        result["coordinate_source"] = (
            geocoded[
                "coordinate_source"
            ].to_numpy()
        )

    else:

        result["coordinate_source"] = ""

    if (
        "coordinate_validation_status"
        in geocoded.columns
    ):

        result["coordinate_validation_status"] = (
            geocoded[
                "coordinate_validation_status"
            ].to_numpy()
        )

    else:

        result[
            "coordinate_validation_status"
        ] = ""

    # ======================================
    # 웹사이트 기존 ID 유지
    # ======================================

    result = result.rename(
        columns={
            "record_id": "id",
        }
    )

    result = result.sort_values(
        ["district", "id"]
    ).reset_index(drop=True)

    if len(result) != EXPECTED_FACILITIES:
        raise ValueError(
            "웹 시설 기록 수 오류"
        )

    if result["id"].duplicated().any():
        raise ValueError(
            "웹 시설 ID 중복"
        )

    return result


# ==========================================
# 4. 자치구별 웹 데이터 생성
# ==========================================

def prepare_districts(facilities):

    district = read_required(
        DISTRICT_FILE,
        [
            "district",
            "facility_records",
            "population_total",
            "population_65_plus",
            "facilities_per_10000",
            "facilities_per_10000_seniors",
            "rank_per_10000",
        ],
    )

    quality = read_required(
        QUALITY_FILE,
        [
            "district",
            "quality_review_records",
            "temporal_review_records",
            "spatial_candidates",
        ],
    )

    flow = read_required(
        FLOW_FILE,
        [
            "district",
            "flow_total",
            "flow_age_60_plus",
            "flow_age_60_plus_pct",
            "resident_senior_pct",
        ],
    )

    volume = read_required(
        VOLUME_FILE,
        [
            "district",
            "annual_total_reported",
            "annual_total_needs_review",
        ],
    )

    # ======================================
    # 필요한 컬럼 선택
    # ======================================

    district = district[
        [
            "district",
            "facility_records",
            "population_total",
            "population_65_plus",
            "facilities_per_10000",
            "facilities_per_10000_seniors",
            "rank_per_10000",
        ]
    ].copy()

    quality = quality[
        [
            "district",
            "quality_review_records",
            "temporal_review_records",
            "spatial_candidates",
        ]
    ].copy()

    flow = flow[
        [
            "district",
            "flow_total",
            "flow_age_60_plus",
            "flow_age_60_plus_pct",
            "resident_senior_pct",
        ]
    ].copy()

    volume = volume[
        [
            "district",
            "annual_total_reported",
            "annual_total_needs_review",
        ]
    ].copy()

    # ======================================
    # 자치구명 정리 및 검증
    # ======================================

    datasets = {
        "district_analysis": district,
        "quality_analysis": quality,
        "population_flow": flow,
        "collection_volume": volume,
    }

    for label, df in datasets.items():

        df["district"] = (
            df["district"]
            .astype("string")
            .str.strip()
        )

        verify_unique(
            df,
            "district",
            label,
        )

        verify_districts(
            df,
            label,
        )

    # ======================================
    # 숫자 변환
    # ======================================

    district = to_number(
        district,
        [
            "facility_records",
            "population_total",
            "population_65_plus",
            "facilities_per_10000",
            "facilities_per_10000_seniors",
            "rank_per_10000",
        ],
    )

    quality = to_number(
        quality,
        [
            "quality_review_records",
            "temporal_review_records",
            "spatial_candidates",
        ],
    )

    flow = to_number(
        flow,
        [
            "flow_total",
            "flow_age_60_plus",
            "flow_age_60_plus_pct",
            "resident_senior_pct",
        ],
    )

    volume = to_number(
        volume,
        [
            "annual_total_reported",
        ],
    )

    volume = to_boolean(
        volume,
        [
            "annual_total_needs_review",
        ],
    )

    # ======================================
    # 데이터 병합
    # ======================================

    result = merge_one_to_one(
        district,
        quality,
        "district",
    )

    result = merge_one_to_one(
        result,
        flow,
        "district",
    )

    result = merge_one_to_one(
        result,
        volume,
        "district",
    )

    # ======================================
    # 공간 분석 대상 수 갱신
    # ======================================

    # 기존 quality_analysis.csv에는
    # 양천구 좌표 보완 전 통계가 들어 있음.
    #
    # 이제 시설 데이터를 기준으로
    # 자치구별 공간 분석 대상 수를 갱신합니다.

    actual_spatial_counts = (
        facilities.groupby("district")[
            "map_marker_available"
        ]
        .sum()
        .to_dict()
    )

    result["spatial_candidates"] = (
        result["district"]
        .map(actual_spatial_counts)
        .astype(int)
    )

    # ======================================
    # 데이터 기준 시점
    # ======================================

    result["population_period"] = "2026-Q2"

    result["flow_period"] = "2026-Q2"

    result["collection_volume_year"] = 2024

    # 공식 측정 단위 확인 전까지
    # 임의로 kg 등을 사용하지 않음
    result["collection_volume_unit"] = pd.NA

    result["comparison_warning"] = (
        "시설·인구·처리량의 기준 시점이 "
        "서로 다르므로 직접적인 운영 효율 "
        "비교에는 사용할 수 없습니다."
    )

    return result.sort_values(
        "rank_per_10000"
    ).reset_index(drop=True)


# ==========================================
# 5. 월별 수거 처리량 데이터
# ==========================================

def prepare_monthly():

    monthly = read_required(
        MONTHLY_FILE,
        [
            "district",
            "year",
            "month",
            "period",
            "collection_value",
        ],
    )

    monthly["district"] = (
        monthly["district"]
        .astype("string")
        .str.strip()
    )

    verify_districts(
        monthly,
        "월별 처리량",
    )

    monthly = to_number(
        monthly,
        [
            "year",
            "month",
            "collection_value",
        ],
    )

    if len(monthly) != EXPECTED_MONTHLY:
        raise ValueError(
            "월별 처리량은 108행이어야 합니다."
        )

    if monthly.duplicated(
        ["district", "year", "month"]
    ).any():
        raise ValueError(
            "월별 처리량 중복"
        )

    if not (
        (monthly["year"] == 2024).all()
        and monthly["month"].between(1, 12).all()
    ):
        raise ValueError(
            "월별 처리량 기간이 잘못되었습니다."
        )

    monthly["unit_verified"] = False

    return monthly.sort_values(
        ["district", "month"]
    ).reset_index(drop=True)


# ==========================================
# 6. 최종 무결성 검사
# ==========================================

def validate_web_data(
    facilities,
    districts,
    monthly,
):

    if len(facilities) != EXPECTED_FACILITIES:
        raise ValueError(
            "시설 수가 233건과 일치하지 않습니다."
        )

    if len(districts) != EXPECTED_DISTRICTS:
        raise ValueError(
            "자치구 수가 9개가 아닙니다."
        )

    if len(monthly) != EXPECTED_MONTHLY:
        raise ValueError(
            "월별 자료가 108건이 아닙니다."
        )

    # ======================================
    # 자치구별 시설 기록 수 확인
    # ======================================

    facility_counts = (
        facilities.groupby("district")
        .size()
        .to_dict()
    )

    for _, row in districts.iterrows():

        district = row["district"]

        expected = int(
            row["facility_records"]
        )

        actual = facility_counts.get(
            district,
            0,
        )

        if actual != expected:
            raise ValueError(
                f"{district} 시설 수 불일치: "
                f"예상 {expected}, 실제 {actual}"
            )

        # 공간 분석 대상 수 확인
        spatial_expected = int(
            row["spatial_candidates"]
        )

        spatial_actual = int(
            facilities.loc[
                facilities["district"] == district,
                "map_marker_available",
            ].sum()
        )

        if spatial_expected != spatial_actual:
            raise ValueError(
                f"{district} 공간 분석 수 불일치"
            )

    # ======================================
    # 최근접 시설 참조 ID 검사
    # ======================================

    spatial_ids = set(
        facilities.loc[
            facilities["map_marker_available"],
            "id",
        ].astype(int)
    )

    nearest_ids = set(
        facilities[
            "nearest_record_id"
        ].dropna().astype(int)
    )

    if not nearest_ids.issubset(spatial_ids):
        raise ValueError(
            "존재하지 않는 최근접 시설 ID 발견"
        )

    # ======================================
    # 최종 좌표 수 검증
    # ======================================

    marker_count = int(
        facilities[
            "map_marker_available"
        ].sum()
    )

    if marker_count != EXPECTED_FACILITIES:
        raise ValueError(
            f"지도 마커 수 오류: {marker_count}"
        )

    missing_coordinates = (
        facilities[
            ["latitude", "longitude"]
        ].isna().any(axis=1).sum()
    )

    if missing_coordinates != 0:
        raise ValueError(
            f"좌표 누락 기록: {missing_coordinates}"
        )

    print()
    print("최종 데이터 무결성 검사 통과")


# ==========================================
# 7. 메타데이터
# ==========================================


def create_metadata(
    facilities,
    districts,
    monthly,
):
    return {
        "project": "medicine-map",

        "coverage": {
            "city": "서울특별시",
            "districts": DISTRICTS,
            "district_count": len(districts),
            "not_seoul_wide": True,
        },

        "records": {
            "facility_count": len(facilities),

            "map_marker_count": int(
                facilities[
                    "map_marker_available"
                ].sum()
            ),

            "missing_coordinate_count": int(
                (~facilities[
                    "map_marker_available"
                ]).sum()
            ),

            "monthly_volume_records": len(monthly),
        },

        "periods": {
            "population": "2026-Q2",
            "flow_population": "2026-Q2",
            "collection_volume": "2024",
            "facility_reference_dates_vary": True,
        },

        "limitations": [
            "서울시 전체가 아닌 9개 자치구를 대상으로 분석했습니다.",

            "시설 자료의 기준일은 자치구별로 다르며, 현재 운영 여부는 확인되지 않았습니다.",

            "양천구 6건은 2020년 공개 자료의 주소를 기반으로 좌표를 보완했습니다.",

            "시설 간 거리는 직선거리 기준으로 실제 이동거리와 다를 수 있습니다.",

            "2024년 수거 처리량은 공식 측정 단위 확인이 필요합니다.",

            "서로 다른 기준 시점의 자료를 직접 비교하여 운영 효율로 해석하기는 어렵습니다.",
        ],
    }



# ==========================================
# 8. 메인 실행
# ==========================================

def main():

    print()
    print("=" * 60)
    print("9단계: 웹사이트용 데이터 생성")
    print("=" * 60)

    facilities = prepare_facilities()

    districts = prepare_districts(
        facilities
    )

    monthly = prepare_monthly()

    validate_web_data(
        facilities,
        districts,
        monthly,
    )

    metadata = create_metadata(
        facilities,
        districts,
        monthly,
    )

    save_json(
        facilities,
        "facilities.json",
    )

    save_json(
        districts,
        "districts.json",
    )

    save_json(
        monthly,
        "collection_monthly.json",
    )

    save_json(
        metadata,
        "metadata.json",
    )

    print()
    print("=== 웹 데이터 생성 결과 ===")

    print(
        f"시설 기록: {len(facilities)}건"
    )

    print(
        "지도 마커 가능:",
        int(
            facilities[
                "map_marker_available"
            ].sum()
        ),
    )

    print(
        f"자치구 통계: {len(districts)}개"
    )

    print(
        f"월별 처리량: {len(monthly)}건"
    )

    print()
    print(f"저장 폴더: {OUTPUT_DIR}")

    print()
    print(
        "웹사이트용 데이터 생성 완료"
    )


if __name__ == "__main__":
    main()
