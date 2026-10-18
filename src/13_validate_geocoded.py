
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


# ==========================================
# 1. 경로
# ==========================================

ROOT = Path(__file__).resolve().parents[1]

ORIGINAL_PATH = (
    ROOT / "data" / "interim"
    / "facilities_standardized.csv"
)

MERGED_PATH = (
    ROOT / "data" / "processed"
    / "facilities_geocoded.csv"
)

REPORT_DIR = ROOT / "reports" / "geocoding"

VALIDATION_CSV = (
    REPORT_DIR / "final_coordinate_validation.csv"
)

DUPLICATES_CSV = (
    REPORT_DIR / "duplicate_coordinates.csv"
)

DISTRICT_CSV = (
    REPORT_DIR / "district_coordinate_summary.csv"
)

SUMMARY_JSON = (
    REPORT_DIR / "final_validation_summary.json"
)

KST = ZoneInfo("Asia/Seoul")

EXPECTED_RECORDS = 233
EXPECTED_DISTRICTS = 9
EXPECTED_ADDED = 6

EXPECTED_COUNTS = {
    "강동구": 21,
    "관악구": 21,
    "구로구": 22,
    "마포구": 35,
    "서초구": 41,
    "성북구": 42,
    "양천구": 6,
    "중구": 29,
    "중랑구": 16,
}


# ==========================================
# 2. 공통 함수
# ==========================================

def now_kst() -> str:
    return datetime.now(KST).isoformat(
        timespec="seconds"
    )


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {path}"
        )

    for encoding in [
        "utf-8-sig",
        "utf-8",
        "cp949",
        "euc-kr",
    ]:
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
        f"CSV 인코딩을 확인하지 못했습니다: {path}"
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
        result = lookup.get(candidate.lower())

        if result is not None:
            return result

    if required:
        raise ValueError(
            f"필수 컬럼을 찾지 못했습니다.\n"
            f"후보: {candidates}\n"
            f"실제: {list(df.columns)}"
        )

    return None


def numeric(value: object) -> float | None:
    text = str(value).strip()

    if not text:
        return None

    try:
        result = float(text)
    except (ValueError, TypeError):
        return None

    return result if math.isfinite(result) else None


def has_coordinate(
    row: pd.Series,
    lat_col: str,
    lon_col: str,
) -> bool:

    latitude = numeric(row[lat_col])
    longitude = numeric(row[lon_col])

    return latitude is not None and longitude is not None


def valid_seoul_coordinate(
    latitude: float | None,
    longitude: float | None,
) -> bool:

    if latitude is None or longitude is None:
        return False

    # 서울 주변 넓은 범위의 이상값 검사.
    # 정확한 자치구 경계 검사는 아님.
    return (
        37.40 <= latitude <= 37.70
        and 126.70 <= longitude <= 127.20
    )


# ==========================================
# 3. 컬럼 정보
# ==========================================

def get_columns(df: pd.DataFrame) -> dict:

    return {
        "district": find_column(
            df,
            ["district", "자치구", "시군구명"],
        ),

        "name": find_column(
            df,
            [
                "facility_name",
                "name",
                "시설명",
                "수거함명",
                "설치장소명",
                "설치장소",
            ],
        ),

        "address": find_column(
            df,
            [
                "road_address",
                "address",
                "도로명주소",
                "소재지도로명주소",
                "주소",
            ],
        ),

        "latitude": find_column(
            df,
            ["latitude", "lat", "위도"],
        ),

        "longitude": find_column(
            df,
            ["longitude", "lon", "lng", "경도"],
        ),
    }


# ==========================================
# 4. 개별 좌표 검사
# ==========================================

def validate_records(
    df: pd.DataFrame,
    columns: dict,
) -> pd.DataFrame:

    results = []

    for index, row in df.iterrows():

        district = str(
            row[columns["district"]]
        ).strip()

        name = str(
            row[columns["name"]]
        ).strip()

        address = str(
            row[columns["address"]]
        ).strip()

        lat = numeric(
            row[columns["latitude"]]
        )

        lon = numeric(
            row[columns["longitude"]]
        )

        coordinate_available = (
            lat is not None and lon is not None
        )

        coordinate_valid = valid_seoul_coordinate(
            lat,
            lon,
        )

        source = str(
            row.get("coordinate_source", "")
        ).strip()

        status = str(
            row.get(
                "coordinate_validation_status",
                "",
            )
        ).strip()

        if not coordinate_available:
            quality = "MISSING_COORDINATE"
        elif not coordinate_valid:
            quality = "INVALID_COORDINATE"
        else:
            quality = "VALID_COORDINATE"

        issues = []

        if quality != "VALID_COORDINATE":
            issues.append(quality)

        if not district:
            issues.append("EMPTY_DISTRICT")

        if not name:
            issues.append("EMPTY_FACILITY_NAME")

        if not address:
            issues.append("EMPTY_ADDRESS")

        if district == "양천구":
            if source != (
                "Kakao Local API (address geocoding)"
            ):
                issues.append(
                    "GEOCODING_SOURCE_MISSING"
                )

            if status != "ADDRESS_VERIFIED":
                issues.append(
                    "ADDRESS_VALIDATION_MISSING"
                )

        results.append({
            "record_number": index + 1,
            "district": district,
            "facility_name": name,
            "road_address": address,
            "latitude": lat,
            "longitude": lon,
            "coordinate_available": coordinate_available,
            "coordinate_valid": coordinate_valid,
            "coordinate_quality": quality,
            "coordinate_source": source,
            "coordinate_validation_status": status,
            "issues": "; ".join(issues),
            "requires_manual_review": bool(issues),
        })

    return pd.DataFrame(results)


# ==========================================
# 5. 기존 좌표 보존 검사
# ==========================================

def validate_preservation(
    original: pd.DataFrame,
    merged: pd.DataFrame,
    original_columns: dict,
    merged_columns: dict,
) -> dict:

    if len(original) != len(merged):
        raise ValueError(
            "원본과 병합 결과의 기록 수가 다릅니다."
        )

    identity_fields = [
        ("district", "자치구"),
        ("name", "시설명"),
        ("address", "주소"),
    ]

    # 12단계에서 행 순서를 보존하므로
    # 동일한 행의 식별 정보를 검사.
    for field, label in identity_fields:

        original_values = (
            original[original_columns[field]]
            .astype(str)
            .str.strip()
            .reset_index(drop=True)
        )

        merged_values = (
            merged[merged_columns[field]]
            .astype(str)
            .str.strip()
            .reset_index(drop=True)
        )

        if not original_values.equals(merged_values):
            raise ValueError(
                f"병합 전후 {label} 또는 행 순서가 변경됐습니다."
            )

    added = 0
    preserved = 0
    changed = []

    for index in range(len(original)):

        old_lat = numeric(
            original.iloc[index][
                original_columns["latitude"]
            ]
        )
        old_lon = numeric(
            original.iloc[index][
                original_columns["longitude"]
            ]
        )

        new_lat = numeric(
            merged.iloc[index][
                merged_columns["latitude"]
            ]
        )
        new_lon = numeric(
            merged.iloc[index][
                merged_columns["longitude"]
            ]
        )

        district = str(
            merged.iloc[index][
                merged_columns["district"]
            ]
        ).strip()

        had_coordinate = (
            old_lat is not None
            and old_lon is not None
        )

        has_new_coordinate = (
            new_lat is not None
            and new_lon is not None
        )

        if had_coordinate:

            if (
                not has_new_coordinate
                or not math.isclose(
                    old_lat,
                    new_lat,
                    abs_tol=1e-7,
                )
                or not math.isclose(
                    old_lon,
                    new_lon,
                    abs_tol=1e-7,
                )
            ):
                changed.append(index + 1)
            else:
                preserved += 1

        elif has_new_coordinate:

            if district != "양천구":
                changed.append(index + 1)
            else:
                added += 1

    if changed:
        raise ValueError(
            "기존 좌표 또는 예상 외 기록이 변경됐습니다.\n"
            f"행 번호: {changed}"
        )

    if added != EXPECTED_ADDED:
        raise ValueError(
            "추가된 양천구 좌표 수가 다릅니다. "
            f"예상 {EXPECTED_ADDED}, 실제 {added}"
        )

    return {
        "preserved_coordinates": preserved,
        "added_yangcheon_coordinates": added,
        "unexpected_changes": len(changed),
    }


# ==========================================
# 6. 중복 좌표 분석
# ==========================================

def find_duplicate_coordinates(
    validated: pd.DataFrame,
) -> pd.DataFrame:

    valid = validated[
        validated["coordinate_valid"]
    ].copy()

    # 미세한 소수점 표현 차이를 제거하고
    # 좌표 기준 중복을 탐지.
    valid["coordinate_key"] = (
        valid["latitude"].round(7).astype(str)
        + ","
        + valid["longitude"].round(7).astype(str)
    )

    duplicated = valid[
        valid.duplicated(
            subset=["coordinate_key"],
            keep=False,
        )
    ].copy()

    if not duplicated.empty:
        duplicated = duplicated.sort_values(
            ["coordinate_key", "district"]
        )

    return duplicated


# ==========================================
# 7. 자치구별 요약
# ==========================================

def district_summary(
    validated: pd.DataFrame,
) -> pd.DataFrame:

    summary = (
        validated
        .groupby("district", as_index=False)
        .agg(
            total_records=(
                "record_number",
                "count",
            ),
            coordinate_available=(
                "coordinate_available",
                "sum",
            ),
            coordinate_valid=(
                "coordinate_valid",
                "sum",
            ),
            manual_review_records=(
                "requires_manual_review",
                "sum",
            ),
        )
    )

    summary["coordinate_missing"] = (
        summary["total_records"]
        - summary["coordinate_available"]
    )

    summary["coordinate_coverage_pct"] = (
        summary["coordinate_valid"]
        / summary["total_records"]
        * 100
    ).round(2)

    return summary.sort_values(
        "district"
    ).reset_index(drop=True)


# ==========================================
# 8. 최종 검증
# ==========================================

def final_validation(
    validated: pd.DataFrame,
    districts: pd.DataFrame,
    preservation: dict,
    duplicates: pd.DataFrame,
) -> dict:

    total = len(validated)

    available = int(
        validated["coordinate_available"].sum()
    )

    valid = int(
        validated["coordinate_valid"].sum()
    )

    manual_review = int(
        validated["requires_manual_review"].sum()
    )

    if total != EXPECTED_RECORDS:
        raise ValueError(
            f"시설 기록 수 오류: {total}"
        )

    if len(districts) != EXPECTED_DISTRICTS:
        raise ValueError(
            f"자치구 수 오류: {len(districts)}"
        )

    for district, expected in EXPECTED_COUNTS.items():

        row = districts[
            districts["district"] == district
        ]

        if len(row) != 1:
            raise ValueError(
                f"자치구 누락: {district}"
            )

        actual = int(
            row.iloc[0]["total_records"]
        )

        if actual != expected:
            raise ValueError(
                f"{district} 시설 수 불일치: "
                f"예상 {expected}, 실제 {actual}"
            )

    if available != EXPECTED_RECORDS:
        raise ValueError(
            f"좌표 누락 존재: {total - available}건"
        )

    if valid != EXPECTED_RECORDS:
        raise ValueError(
            f"좌표 범위 검사 미통과: {total - valid}건"
        )

    if manual_review:
        raise ValueError(
            f"품질 검토 필요 기록: {manual_review}건"
        )

    return {
        "validation_passed": True,
        "generated_at": now_kst(),
        "total_records": total,
        "district_count": len(districts),
        "coordinate_available": available,
        "coordinate_valid": valid,
        "coordinate_missing": total - available,
        "coordinate_coverage_pct": round(
            valid / total * 100,
            2,
        ),
        "coordinate_preservation": preservation,
        "duplicate_coordinate_record_count": int(
            len(duplicates)
        ),
        "duplicate_coordinate_group_count": int(
            duplicates["coordinate_key"].nunique()
        ) if not duplicates.empty else 0,
        "manual_review_records": manual_review,
        "address_geocoded_yangcheon_records": 6,
        "facility_operation_verified": False,
        "notes": [
            "좌표 범위 검사는 정확한 자치구 경계 검사가 아닙니다.",
            "동일 좌표 기록은 자동 삭제하지 않았습니다.",
            "양천구 자료는 2020년 자료에 지오코딩 좌표를 추가했습니다.",
            "주소 검증은 시설의 현재 운영 여부 검증이 아닙니다.",
            "공간 분석은 시설 간 직선거리 기준입니다.",
        ],
    }


# ==========================================
# 9. 메인 실행
# ==========================================

def main() -> None:

    print("=" * 65)
    print("13단계: 좌표 병합 데이터 재검증")
    print("=" * 65)

    original = read_csv(ORIGINAL_PATH)
    merged = read_csv(MERGED_PATH)

    original_columns = get_columns(original)
    merged_columns = get_columns(merged)

    print("기존 시설 기록:", len(original))
    print("병합 시설 기록:", len(merged))

    preservation = validate_preservation(
        original,
        merged,
        original_columns,
        merged_columns,
    )

    validated = validate_records(
        merged,
        merged_columns,
    )

    duplicates = find_duplicate_coordinates(
        validated
    )

    districts = district_summary(
        validated
    )

    summary = final_validation(
        validated,
        districts,
        preservation,
        duplicates,
    )

    # 모든 핵심 검증을 통과한 후 결과 저장
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    validated.to_csv(
        VALIDATION_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    duplicates.to_csv(
        DUPLICATES_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    districts.to_csv(
        DISTRICT_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    SUMMARY_JSON.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=== 전체 검증 결과 ===")

    for key in [
        "total_records",
        "district_count",
        "coordinate_available",
        "coordinate_valid",
        "coordinate_missing",
        "coordinate_coverage_pct",
        "duplicate_coordinate_record_count",
        "duplicate_coordinate_group_count",
        "manual_review_records",
    ]:
        print(f"{key}: {summary[key]}")

    print()
    print("=== 자치구별 결과 ===")

    print(
        districts[
            [
                "district",
                "total_records",
                "coordinate_valid",
                "coordinate_missing",
                "coordinate_coverage_pct",
            ]
        ].to_string(index=False)
    )

    print()
    print("=== 기존 좌표 보존 ===")

    print(
        "기존 좌표 유지:",
        preservation["preserved_coordinates"],
    )

    print(
        "양천구 좌표 추가:",
        preservation["added_yangcheon_coordinates"],
    )

    print()
    print("검증 결과 저장 완료:")
    print(VALIDATION_CSV)
    print(DUPLICATES_CSV)
    print(DISTRICT_CSV)
    print(SUMMARY_JSON)

    print()
    print(
        "13단계 검증 통과. "
        "14단계 공간 분석을 진행할 수 있습니다."
    )


if __name__ == "__main__":

    try:
        main()

    except Exception as error:
        print(
            f"\n검증 실패: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
