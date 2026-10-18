
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


# ==========================================
# 1. 경로 및 설정
# ==========================================

ROOT = Path(__file__).resolve().parents[1]

SOURCE_PATH = (
    ROOT / "data" / "interim"
    / "facilities_standardized.csv"
)

VERIFIED_PATH = (
    ROOT / "data" / "geocoded"
    / "yangcheon_verified.csv"
)

OUTPUT_PATH = (
    ROOT / "data" / "processed"
    / "facilities_geocoded.csv"
)

REPORT_DIR = ROOT / "reports" / "geocoding"

REPORT_PATH = (
    REPORT_DIR / "yangcheon_merge_report.json"
)

DETAIL_PATH = (
    REPORT_DIR / "yangcheon_merge_details.csv"
)

KST = ZoneInfo("Asia/Seoul")

EXPECTED_TOTAL = 233
EXPECTED_YANGCHEON = 6

# 이번 작업에서는 주소 검증을 통과한
# 양천구 기록만 병합
REQUIRED_STATUS = "ADDRESS_VERIFIED"


# ==========================================
# 2. 공통 함수
# ==========================================

def now_kst() -> str:
    return datetime.now(KST).isoformat(
        timespec="seconds"
    )


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def normalize_name(value: object) -> str:
    text = unicodedata.normalize(
        "NFKC",
        clean_text(value),
    )

    return re.sub(r"\s+", "", text).lower()


def normalize_address(value: object) -> str:
    text = unicodedata.normalize(
        "NFKC",
        clean_text(value),
    )

    # 괄호 안 참고 표기 제거
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"（[^）]*）", "", text)

    # 행정구역 명칭 통일
    text = re.sub(
        r"^서울특별시\s*",
        "서울 ",
        text,
    )

    text = re.sub(
        r"^서울시\s*",
        "서울 ",
        text,
    )

    # 공백 표기 차이 제거
    text = re.sub(r"\s+", "", text)

    return text.lower()


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
    required: bool = True,
) -> str | None:
    lookup = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for name in candidates:
        found = lookup.get(name.strip().lower())

        if found is not None:
            return found

    if required:
        raise ValueError(
            "필요한 컬럼을 찾지 못했습니다.\n"
            f"후보: {candidates}\n"
            f"실제 컬럼: {list(df.columns)}"
        )

    return None


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"파일이 없습니다: {path}"
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
        f"CSV 인코딩 확인 실패: {path}"
    )


def parse_coordinate(value: object) -> float | None:
    text = clean_text(value)

    if not text:
        return None

    try:
        number = float(text)
    except ValueError:
        return None

    if not math.isfinite(number):
        return None

    return number


def make_key(
    district: object,
    name: object,
    address: object,
) -> tuple[str, str, str]:
    return (
        normalize_name(district),
        normalize_name(name),
        normalize_address(address),
    )


def validate_lat_lon(
    latitude: float | None,
    longitude: float | None,
) -> bool:
    if latitude is None or longitude is None:
        return False

    # 서울 주변의 넓은 좌표 범위.
    # 행정경계 검사를 대체하지 않음.
    return (
        37.40 <= latitude <= 37.70
        and 126.70 <= longitude <= 127.20
    )


# ==========================================
# 3. 기존 시설 데이터 로드
# ==========================================

def load_facilities():
    df = read_csv(SOURCE_PATH)

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

    address_col = find_column(
        df,
        [
            "road_address",
            "address",
            "도로명주소",
            "소재지도로명주소",
            "주소",
        ],
    )

    latitude_col = find_column(
        df,
        ["latitude", "lat", "위도"],
        required=False,
    )

    longitude_col = find_column(
        df,
        ["longitude", "lon", "lng", "경도"],
        required=False,
    )

    if len(df) != EXPECTED_TOTAL:
        raise ValueError(
            f"전체 시설 기록 수가 예상과 다릅니다. "
            f"예상 {EXPECTED_TOTAL}, 실제 {len(df)}"
        )

    yangcheon_count = (
        df[district_col]
        .map(clean_text)
        .eq("양천구")
        .sum()
    )

    if yangcheon_count != EXPECTED_YANGCHEON:
        raise ValueError(
            "양천구 시설 기록 수 불일치: "
            f"{yangcheon_count}건"
        )

    # 위도/경도 컬럼이 없을 경우에만 생성
    if latitude_col is None:
        latitude_col = "latitude"
        df[latitude_col] = ""

    if longitude_col is None:
        longitude_col = "longitude"
        df[longitude_col] = ""

    return (
        df,
        district_col,
        name_col,
        address_col,
        latitude_col,
        longitude_col,
    )


# ==========================================
# 4. 검증된 양천구 좌표 로드
# ==========================================

def load_verified() -> pd.DataFrame:
    df = read_csv(VERIFIED_PATH)

    required = [
        "geocode_facility_name",
        "geocode_input_address",
        "verified_latitude",
        "verified_longitude",
        "address_validation_status",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"검증 파일 필수 컬럼 누락: {missing}"
        )

    if len(df) != EXPECTED_YANGCHEON:
        raise ValueError(
            "검증 파일 기록 수가 6건이 아닙니다."
        )

    unverified = df[
        df["address_validation_status"]
        != REQUIRED_STATUS
    ]

    if not unverified.empty:
        raise ValueError(
            "주소 검증을 통과하지 않은 기록이 있습니다.\n"
            + unverified[
                [
                    "geocode_facility_name",
                    "address_validation_status",
                ]
            ].to_string(index=False)
        )

    return df


# ==========================================
# 5. 원본 데이터 보존 및 병합
# ==========================================

def merge_coordinates(
    facilities: pd.DataFrame,
    verified: pd.DataFrame,
    district_col: str,
    name_col: str,
    address_col: str,
    latitude_col: str,
    longitude_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    result = facilities.copy(deep=True)

    # 좌표의 출처를 구분할 수 있도록
    # 별도 컬럼 추가
    if "coordinate_source" not in result.columns:
        result["coordinate_source"] = ""

    if "coordinate_validation_status" not in result.columns:
        result["coordinate_validation_status"] = ""

    if "coordinate_updated_at" not in result.columns:
        result["coordinate_updated_at"] = ""

    if "facility_operation_verified" not in result.columns:
        result["facility_operation_verified"] = ""

    # 기존 시설을 식별할 키 생성
    facility_keys = {}

    for index, row in result.iterrows():
        key = make_key(
            row[district_col],
            row[name_col],
            row[address_col],
        )

        facility_keys.setdefault(key, []).append(index)

    # 검증 데이터 자체에도 동일한
    # 시설 식별자가 중복되어 있으면 중단
    verified_keys = []

    for _, row in verified.iterrows():
        key = make_key(
            "양천구",
            row["geocode_facility_name"],
            row["geocode_input_address"],
        )
        verified_keys.append(key)

    if len(set(verified_keys)) != len(verified_keys):
        raise ValueError(
            "검증 파일에서 중복된 시설 식별자가 발견됐습니다."
        )

    details = []
    matched_indexes = set()

    for _, row in verified.iterrows():
        facility_name = clean_text(
            row["geocode_facility_name"]
        )

        key = make_key(
            "양천구",
            facility_name,
            row["geocode_input_address"],
        )

        matches = facility_keys.get(key, [])

        if len(matches) != 1:
            raise ValueError(
                f"시설 매칭 오류: {facility_name}\n"
                f"일치 기록 수: {len(matches)}\n"
                "시설명·자치구·주소를 확인해 주세요."
            )

        target_index = matches[0]

        if target_index in matched_indexes:
            raise ValueError(
                f"중복 병합 시도: {facility_name}"
            )

        latitude = parse_coordinate(
            row["verified_latitude"]
        )

        longitude = parse_coordinate(
            row["verified_longitude"]
        )

        if not validate_lat_lon(latitude, longitude):
            raise ValueError(
                f"좌표 검증 실패: {facility_name}"
            )

        old_lat = parse_coordinate(
            result.at[target_index, latitude_col]
        )

        old_lon = parse_coordinate(
            result.at[target_index, longitude_col]
        )

        # 좌표가 부분적으로만 있거나
        # 이미 들어 있다면 덮어쓰지 않음
        if old_lat is not None or old_lon is not None:
            raise ValueError(
                f"기존 좌표가 존재합니다: {facility_name}\n"
                "기존 좌표를 자동으로 덮어쓰지 않습니다."
            )

        result.at[
            target_index,
            latitude_col,
        ] = f"{latitude:.8f}"

        result.at[
            target_index,
            longitude_col,
        ] = f"{longitude:.8f}"

        result.at[
            target_index,
            "coordinate_source",
        ] = "Kakao Local API (address geocoding)"

        result.at[
            target_index,
            "coordinate_validation_status",
        ] = "ADDRESS_VERIFIED"

        result.at[
            target_index,
            "coordinate_updated_at",
        ] = now_kst()

        # 주소 검증과 현재 시설 운영 검증은 별개
        result.at[
            target_index,
            "facility_operation_verified",
        ] = "False"

        matched_indexes.add(target_index)

        details.append({
            "facility_name": facility_name,
            "district": "양천구",
            "original_address": clean_text(
                result.at[target_index, address_col]
            ),
            "latitude": latitude,
            "longitude": longitude,
            "match_status": "MATCHED",
            "coordinate_source": "Kakao Local API",
            "address_validation_status":
                "ADDRESS_VERIFIED",
            "operation_verified": False,
        })

    if len(matched_indexes) != EXPECTED_YANGCHEON:
        raise ValueError(
            "병합 완료 건수가 6건이 아닙니다."
        )

    return result, pd.DataFrame(details)


# ==========================================
# 6. 최종 무결성 검사
# ==========================================

def validate_merged(
    original: pd.DataFrame,
    merged: pd.DataFrame,
    district_col: str,
    latitude_col: str,
    longitude_col: str,
) -> dict:

    if len(original) != len(merged):
        raise ValueError(
            "병합 전후 시설 기록 수가 달라졌습니다."
        )

    # 자치구별 기록 수가 유지되는지 확인
    original_counts = (
        original[district_col]
        .value_counts()
        .sort_index()
    )

    merged_counts = (
        merged[district_col]
        .value_counts()
        .sort_index()
    )

    if not original_counts.equals(merged_counts):
        raise ValueError(
            "자치구별 시설 기록 수가 변경됐습니다."
        )

    def count_coordinates(df: pd.DataFrame) -> int:
        total = 0

        for _, row in df.iterrows():
            lat = parse_coordinate(
                row[latitude_col]
            )

            lon = parse_coordinate(
                row[longitude_col]
            )

            if lat is not None and lon is not None:
                total += 1

        return total

    before = count_coordinates(original)
    after = count_coordinates(merged)

    if after - before != EXPECTED_YANGCHEON:
        raise ValueError(
            "좌표 보유 증가 건수가 6건이 아닙니다.\n"
            f"병합 전 {before}, 병합 후 {after}"
        )

    if after != EXPECTED_TOTAL:
        raise ValueError(
            "좌표 보유 기록이 233건이 아닙니다.\n"
            f"현재 {after}건"
        )

    return {
        "total_records": len(merged),
        "coordinate_before": before,
        "coordinate_after": after,
        "coordinate_added": after - before,
        "coordinate_missing_after": len(merged) - after,
        "district_count": int(
            merged[district_col].nunique()
        ),
    }


# ==========================================
# 7. 결과 저장
# ==========================================

def save_results(
    merged: pd.DataFrame,
    details: pd.DataFrame,
    summary: dict,
) -> None:

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 다른 분석 파일을 덮어쓰지 않음
    merged.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    details.to_csv(
        DETAIL_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    report = {
        "project": "medicine-map",
        "step": 12,
        "description":
            "양천구 검증 좌표의 시설 데이터 병합",
        "generated_at": now_kst(),
        "source_file": str(SOURCE_PATH),
        "geocoding_file": str(VERIFIED_PATH),
        "output_file": str(OUTPUT_PATH),
        "summary": summary,
        "coordinate_source": "Kakao Local API",
        "address_reference_year": 2020,
        "operation_verified": False,
        "notes": [
            "원본 및 기존 전처리 파일은 수정하지 않았습니다.",
            "자치구, 시설명, 주소를 사용해 정확히 매칭했습니다.",
            "기존 좌표가 있는 기록은 덮어쓰지 않았습니다.",
            "ADDRESS_VERIFIED는 현재 운영 여부 확인을 의미하지 않습니다.",
            "공간 분석과 웹 JSON은 아직 다시 생성하지 않았습니다.",
        ],
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ==========================================
# 8. 메인
# ==========================================

def main() -> None:
    print("=" * 65)
    print("12단계: 양천구 검증 좌표 병합")
    print("=" * 65)

    (
        facilities,
        district_col,
        name_col,
        address_col,
        latitude_col,
        longitude_col,
    ) = load_facilities()

    verified = load_verified()

    print(f"기존 시설 기록: {len(facilities)}건")
    print(f"검증된 양천구 좌표: {len(verified)}건")

    merged, details = merge_coordinates(
        facilities,
        verified,
        district_col,
        name_col,
        address_col,
        latitude_col,
        longitude_col,
    )

    summary = validate_merged(
        facilities,
        merged,
        district_col,
        latitude_col,
        longitude_col,
    )

    # 검증까지 모두 통과했을 때만 저장
    save_results(
        merged,
        details,
        summary,
    )

    print()
    print("=== 좌표 병합 결과 ===")

    print(
        "전체 시설 기록:",
        summary["total_records"],
    )

    print(
        "병합 전 좌표 보유:",
        summary["coordinate_before"],
    )

    print(
        "병합 후 좌표 보유:",
        summary["coordinate_after"],
    )

    print(
        "추가 좌표:",
        summary["coordinate_added"],
    )

    print(
        "남은 좌표 누락:",
        summary["coordinate_missing_after"],
    )

    print()
    print("=== 양천구 병합 상세 ===")

    print(
        details[
            [
                "facility_name",
                "latitude",
                "longitude",
                "match_status",
            ]
        ].to_string(index=False)
    )

    print()
    print("병합 파일:", OUTPUT_PATH)
    print("검증 보고서:", REPORT_PATH)
    print("상세 결과:", DETAIL_PATH)

    print()
    print(
        "좌표 병합 완료. "
        "기존 분석 파일은 변경하지 않았습니다."
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print(
            f"\n작업 실패: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
