
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    ROOT / "data" / "processed" / "facilities_geocoded.csv"
)

VALIDATION_PATH = (
    ROOT / "reports" / "geocoding"
    / "final_validation_summary.json"
)

REPORT_DIR = ROOT / "reports" / "spatial"
WEB_DIR = ROOT / "data" / "web"

DETAIL_PATH = REPORT_DIR / "facility_nearest_distances.csv"
DISTRICT_PATH = REPORT_DIR / "district_spatial_summary.csv"
SUMMARY_PATH = REPORT_DIR / "spatial_summary_233.json"
WEB_PATH = WEB_DIR / "spatial_analysis.json"

EXPECTED_RECORDS = 233
EXPECTED_DISTRICTS = 9

EARTH_RADIUS_KM = 6371.0088
SAME_POSITION_TOLERANCE_KM = 1e-7

KST = ZoneInfo("Asia/Seoul")


def timestamp() -> str:
    return datetime.now(KST).isoformat(
        timespec="seconds"
    )


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"입력 파일을 찾을 수 없습니다: {path}"
        )

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "cp949",
        "euc-kr",
    ):
        try:
            return pd.read_csv(
                path,
                encoding=encoding,
                dtype=str,
                keep_default_na=False,
            )
        except UnicodeDecodeError:
            continue

    raise ValueError(
        f"CSV 인코딩을 확인할 수 없습니다: {path}"
    )


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
    required: bool = True,
) -> str | None:
    lookup = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:
        found = lookup.get(candidate.strip().lower())

        if found is not None:
            return found

    if required:
        raise ValueError(
            "필수 컬럼을 찾지 못했습니다.\n"
            f"후보: {candidates}\n"
            f"실제 컬럼: {list(df.columns)}"
        )

    return None


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
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
        * EARTH_RADIUS_KM
        * math.asin(math.sqrt(a))
    )


def load_facilities() -> list[dict]:
    df = read_csv(INPUT_PATH)

    if len(df) != EXPECTED_RECORDS:
        raise ValueError(
            "시설 수가 예상과 다릅니다. "
            f"예상 {EXPECTED_RECORDS}, 실제 {len(df)}"
        )

    district_col = find_column(
        df,
        ["district", "자치구", "시군구명"],
    )

    name_col = find_column(
        df,
        [
            "facility_name",
            "name",
            "시설명",
            "수거함명",
            "설치장소명",
            "설치장소",
        ],
    )

    latitude_col = find_column(
        df,
        ["latitude", "lat", "위도"],
    )

    longitude_col = find_column(
        df,
        ["longitude", "lon", "lng", "경도"],
    )

    address_col = find_column(
        df,
        [
            "road_address",
            "address",
            "도로명주소",
            "소재지도로명주소",
            "주소",
        ],
        required=False,
    )

    facilities = []

    for index, row in df.iterrows():
        district = str(row[district_col]).strip()
        name = str(row[name_col]).strip()

        try:
            lat = float(row[latitude_col])
            lon = float(row[longitude_col])
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"{index + 1}번째 시설의 좌표가 잘못됐습니다."
            ) from error

        if not (
            math.isfinite(lat)
            and math.isfinite(lon)
            and 37.40 <= lat <= 37.70
            and 126.70 <= lon <= 127.20
        ):
            raise ValueError(
                f"좌표 범위 오류: {name} ({lat}, {lon})"
            )

        facilities.append({
            "record_number": index + 1,
            "district": district,
            "facility_name": name,
            "address": (
                str(row[address_col]).strip()
                if address_col is not None
                else ""
            ),
            "latitude": lat,
            "longitude": lon,
            "coordinate_source": str(
                row.get("coordinate_source", "")
            ).strip(),
        })

    count_districts = len({
        f["district"] for f in facilities
    })

    if count_districts != EXPECTED_DISTRICTS:
        raise ValueError(
            f"9개 자치구가 필요하지만 {count_districts}개입니다."
        )

    return facilities


def verify_previous_validation() -> None:
    if not VALIDATION_PATH.exists():
        raise FileNotFoundError(
            "13단계 검증 보고서가 없습니다.\n"
            f"{VALIDATION_PATH}"
        )

    summary = json.loads(
        VALIDATION_PATH.read_text(encoding="utf-8")
    )

    if (
        summary.get("validation_passed") is not True
        or summary.get("coordinate_valid") != EXPECTED_RECORDS
    ):
        raise ValueError(
            "13단계 품질 검증 결과가 통과 상태가 아닙니다."
        )


def analyze_nearest(
    facilities: list[dict],
) -> pd.DataFrame:
    rows = []

    for i, current in enumerate(facilities):
        nearest_index = None
        nearest_km = math.inf

        distinct_index = None
        distinct_km = math.inf

        for j, other in enumerate(facilities):
            if i == j:
                continue

            distance = haversine_km(
                current["latitude"],
                current["longitude"],
                other["latitude"],
                other["longitude"],
            )

            # 다른 기록이라면 같은 좌표여도 포함
            if distance < nearest_km:
                nearest_km = distance
                nearest_index = j

            # 보조 지표: 서로 다른 좌표만 탐색
            if (
                distance > SAME_POSITION_TOLERANCE_KM
                and distance < distinct_km
            ):
                distinct_km = distance
                distinct_index = j

        if nearest_index is None:
            raise ValueError(
                "가장 가까운 다른 시설을 찾지 못했습니다."
            )

        nearest = facilities[nearest_index]

        distinct = (
            facilities[distinct_index]
            if distinct_index is not None
            else None
        )

        rows.append({
            **current,
            "nearest_facility": nearest["facility_name"],
            "nearest_district": nearest["district"],
            "nearest_record_number": nearest["record_number"],
            "nearest_distance_km": nearest_km,
            "nearest_distance_m": nearest_km * 1000,
            "nearest_same_coordinate": (
                nearest_km <= SAME_POSITION_TOLERANCE_KM
            ),
            "nearest_other_district": (
                current["district"]
                != nearest["district"]
            ),
            "nearest_distinct_facility": (
                distinct["facility_name"]
                if distinct is not None
                else ""
            ),
            "nearest_distinct_distance_km": (
                distinct_km
                if distinct is not None
                else None
            ),
            "nearest_distinct_distance_m": (
                distinct_km * 1000
                if distinct is not None
                else None
            ),
        })

    return pd.DataFrame(rows)


def summarize_districts(
    detail: pd.DataFrame,
) -> pd.DataFrame:
    grouped = (
        detail
        .groupby("district", as_index=False)
        .agg(
            facility_records=(
                "record_number",
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
            min_nearest_km=(
                "nearest_distance_km",
                "min",
            ),
            max_nearest_km=(
                "nearest_distance_km",
                "max",
            ),
            mean_distinct_km=(
                "nearest_distinct_distance_km",
                "mean",
            ),
            same_coordinate_records=(
                "nearest_same_coordinate",
                "sum",
            ),
            nearest_other_district_records=(
                "nearest_other_district",
                "sum",
            ),
        )
    )

    for field in (
        "mean_nearest",
        "median_nearest",
        "min_nearest",
        "max_nearest",
        "mean_distinct",
    ):
        grouped[f"{field}_m"] = (
            grouped[f"{field}_km"] * 1000
        )

    return grouped.sort_values(
        "mean_nearest_km",
        ascending=False,
    ).reset_index(drop=True)


def build_summary(
    detail: pd.DataFrame,
    district_df: pd.DataFrame,
) -> dict:
    mean_km = float(
        detail["nearest_distance_km"].mean()
    )

    median_km = float(
        detail["nearest_distance_km"].median()
    )

    distinct_mean_km = float(
        detail["nearest_distinct_distance_km"].mean()
    )

    maximum_km = float(
        detail["nearest_distance_km"].max()
    )

    over_one_km = int(
        (
            detail["nearest_distance_km"] >= 1.0
        ).sum()
    )

    distinct_over_one_km = int(
        (
            detail["nearest_distinct_distance_km"] >= 1.0
        ).sum()
    )

    return {
        "generated_at": timestamp(),
        "source_file": str(INPUT_PATH),
        "method": "haversine",
        "earth_radius_km": EARTH_RADIUS_KM,
        "scope": (
            "전체 9개 자치구의 233개 기록 중 "
            "가장 가까운 다른 시설 검색"
        ),
        "total_records": int(len(detail)),
        "district_count": int(len(district_df)),
        "coordinate_records": int(len(detail)),
        "missing_coordinates": 0,
        "mean_nearest_km": mean_km,
        "mean_nearest_m": mean_km * 1000,
        "median_nearest_km": median_km,
        "median_nearest_m": median_km * 1000,
        "max_nearest_km": maximum_km,
        "max_nearest_m": maximum_km * 1000,
        "nearest_over_1km_records": over_one_km,
        "same_coordinate_records": int(
            detail["nearest_same_coordinate"].sum()
        ),
        "mean_distinct_nearest_km": distinct_mean_km,
        "mean_distinct_nearest_m": (
            distinct_mean_km * 1000
        ),
        "distinct_nearest_over_1km_records": (
            distinct_over_one_km
        ),
        "nearest_other_district_records": int(
            detail["nearest_other_district"].sum()
        ),
        "districts": [
            {
                "district": str(row["district"]),
                "facility_records": int(
                    row["facility_records"]
                ),
                "mean_nearest_km": float(
                    row["mean_nearest_km"]
                ),
                "mean_nearest_m": float(
                    row["mean_nearest_m"]
                ),
                "median_nearest_m": float(
                    row["median_nearest_m"]
                ),
                "max_nearest_m": float(
                    row["max_nearest_m"]
                ),
                "mean_distinct_nearest_m": float(
                    row["mean_distinct_m"]
                ),
                "same_coordinate_records": int(
                    row["same_coordinate_records"]
                ),
            }
            for _, row in district_df.iterrows()
        ],
        "cautions": [
            "가장 가까운 다른 시설 기록까지의 직선거리입니다.",
            "주민의 실제 이동거리 또는 시설 접근시간이 아닙니다.",
            "동일 좌표의 다른 시설 기록은 거리 0으로 집계됩니다.",
            "자치구 경계를 넘어 가까운 시설을 찾을 수 있습니다.",
            "시설 자료의 기준일은 자치구마다 다릅니다.",
            "양천구 6건은 2020년 주소를 지오코딩한 기록입니다.",
            "시설의 현재 운영 여부는 검증하지 않았습니다.",
        ],
    }


def save_results(
    detail: pd.DataFrame,
    district_df: pd.DataFrame,
    summary: dict,
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(parents=True, exist_ok=True)

    detail.to_csv(
        DETAIL_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    district_df.to_csv(
        DISTRICT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    json_text = json.dumps(
        summary,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )

    SUMMARY_PATH.write_text(
        json_text,
        encoding="utf-8",
    )

    WEB_PATH.write_text(
        json_text,
        encoding="utf-8",
    )


def main() -> None:
    print("=" * 65)
    print("14단계: 233건 공간 분석 재계산")
    print("=" * 65)

    verify_previous_validation()

    facilities = load_facilities()

    print(f"전체 시설: {len(facilities)}건")
    print("최근접 시설 거리 계산 중...")

    detail = analyze_nearest(facilities)
    district_df = summarize_districts(detail)
    summary = build_summary(detail, district_df)

    if summary["total_records"] != EXPECTED_RECORDS:
        raise ValueError("분석 대상 기록 수가 다릅니다.")

    if summary["district_count"] != EXPECTED_DISTRICTS:
        raise ValueError("분석 대상 자치구 수가 다릅니다.")

    save_results(detail, district_df, summary)

    print()
    print("=== 전체 공간 분석 ===")
    print(
        "평균 최근접 다른 기록 거리:",
        f'{summary["mean_nearest_m"]:.1f}m',
    )
    print(
        "중앙값:",
        f'{summary["median_nearest_m"]:.1f}m',
    )
    print(
        "최대:",
        f'{summary["max_nearest_m"]:.1f}m',
    )
    print(
        "최근접 다른 기록 1km 이상:",
        summary["nearest_over_1km_records"],
        "건",
    )
    print(
        "동일 좌표로 최근접 거리 0m인 기록:",
        summary["same_coordinate_records"],
        "건",
    )
    print(
        "평균 최근접 서로 다른 위치 거리:",
        f'{summary["mean_distinct_nearest_m"]:.1f}m',
    )
    print(
        "자치구 밖의 시설이 가장 가까운 기록:",
        summary["nearest_other_district_records"],
        "건",
    )

    print()
    print("=== 자치구별 평균 최근접 거리 ===")
    print(
        district_df[
            [
                "district",
                "facility_records",
                "mean_nearest_m",
                "mean_distinct_m",
            ]
        ].round(2).to_string(index=False)
    )

    print()
    print("=== 저장된 파일 ===")
    print(DETAIL_PATH)
    print(DISTRICT_PATH)
    print(SUMMARY_PATH)
    print(WEB_PATH)

    print()
    print(
        "14단계 완료. "
        "분석 결과를 웹사이트에 반영하기 전에 "
        "기존 분석 방법과 수치를 비교하세요."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"\n분석 실패: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
