
from __future__ import annotations

import json
import math
import re
import sys

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    ROOT / "data" / "geocoded" /
    "yangcheon_geocoded.csv"
)

OUTPUT_PATH = (
    ROOT / "data" / "geocoded" /
    "yangcheon_verified.csv"
)

REPORT_PATH = (
    ROOT / "reports" / "geocoding" /
    "yangcheon_verification.json"
)

KST = ZoneInfo("Asia/Seoul")

REQUIRED_COLUMNS = [
    "geocode_facility_name",
    "geocode_input_address",
    "geocode_returned_address",
    "geocode_latitude",
    "geocode_longitude",
]

# 양천구를 포함하는 넓은 범위의
# 이상 좌표 탐지용 경계.
# 실제 행정구역 경계 검사를 대체하지 않음.
LAT_MIN = 37.45
LAT_MAX = 37.60
LON_MIN = 126.78
LON_MAX = 126.92


def normalize_address(value: object) -> str:
    if pd.isna(value):
        return ""

    address = str(value).strip()

    # 괄호 안의 행정동 참고 표기 제거
    address = re.sub(
        r"\([^)]*\)",
        "",
        address,
    )

    address = re.sub(
        r"（[^）]*）",
        "",
        address,
    )

    # 서울시와 서울특별시 표기 통일
    address = re.sub(
        r"^서울특별시\s*",
        "서울 ",
        address,
    )

    address = re.sub(
        r"^서울시\s*",
        "서울 ",
        address,
    )

    address = re.sub(
        r"\s+",
        " ",
        address,
    ).strip()

    return address


def parse_road_address(
    address: str,
) -> tuple[str, str, str] | None:
    normalized = normalize_address(address)

    # 서울 양천구 도로명 건물번호 형식
    pattern = (
        r"^서울\s+양천구\s+"
        r"(.+?(?:대로|로|길))\s+"
        r"(\d+(?:-\d+)?)"
        r"(?:\s+.*)?$"
    )

    match = re.match(pattern, normalized)

    if not match:
        return None

    return (
        "서울 양천구",
        match.group(1).replace(" ", ""),
        match.group(2),
    )


def validate_coordinate(
    latitude: float,
    longitude: float,
) -> tuple[bool, str]:
    if not (
        math.isfinite(latitude)
        and math.isfinite(longitude)
    ):
        return False, "좌표가 유효한 숫자가 아님"

    if not (
        LAT_MIN <= latitude <= LAT_MAX
        and LON_MIN <= longitude <= LON_MAX
    ):
        return False, "좌표가 예상 범위를 벗어남"

    return True, "좌표 범위 검사 통과"


def main() -> None:
    print("=" * 65)
    print("11단계: 양천구 지오코딩 결과 재검증")
    print("=" * 65)

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"입력 파일 없음: {INPUT_PATH}"
        )

    df = pd.read_csv(
        INPUT_PATH,
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )

    missing = [
        col for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"필수 컬럼 누락: {missing}"
        )

    if len(df) != 6:
        raise ValueError(
            f"예상 기록 6건, 실제 {len(df)}건"
        )

    # 좌표 중복 여부 확인
    coordinate_keys = []

    for _, row in df.iterrows():
        lat = pd.to_numeric(
            row["geocode_latitude"],
            errors="coerce",
        )
        lon = pd.to_numeric(
            row["geocode_longitude"],
            errors="coerce",
        )

        if pd.isna(lat) or pd.isna(lon):
            coordinate_keys.append(None)
        else:
            coordinate_keys.append(
                (round(float(lat), 7),
                 round(float(lon), 7))
            )

    valid_keys = [
        key for key in coordinate_keys
        if key is not None
    ]

    duplicate_keys = {
        key
        for key in valid_keys
        if valid_keys.count(key) > 1
    }

    results = []

    for index, row in df.iterrows():
        original = str(
            row["geocode_input_address"]
        )

        returned = str(
            row["geocode_returned_address"]
        )

        original_parsed = parse_road_address(
            original
        )

        returned_parsed = parse_road_address(
            returned
        )

        latitude = pd.to_numeric(
            row["geocode_latitude"],
            errors="coerce",
        )

        longitude = pd.to_numeric(
            row["geocode_longitude"],
            errors="coerce",
        )

        reasons = []

        if (
            original_parsed is None
            or returned_parsed is None
        ):
            reasons.append(
                "도로명주소 구성요소 추출 실패"
            )

        elif original_parsed != returned_parsed:
            reasons.append(
                "도로명 또는 건물번호 불일치"
            )

        if pd.isna(latitude) or pd.isna(longitude):
            reasons.append("좌표 없음")
        else:
            valid, reason = validate_coordinate(
                float(latitude),
                float(longitude),
            )

            if not valid:
                reasons.append(reason)

        if coordinate_keys[index] in duplicate_keys:
            reasons.append(
                "서로 다른 시설의 동일 좌표 확인 필요"
            )

        # 이 상태는 주소와 좌표의 형식적 검증 결과.
        # 현재 수거시설 운영 여부 검증이 아님.
        status = (
            "ADDRESS_VERIFIED"
            if not reasons
            else "MANUAL_REVIEW"
        )

        result = row.to_dict()

        result.update({
            "normalized_input_address":
                normalize_address(original),
            "normalized_returned_address":
                normalize_address(returned),
            "verified_latitude":
                float(latitude)
                if pd.notna(latitude)
                and status == "ADDRESS_VERIFIED"
                else None,
            "verified_longitude":
                float(longitude)
                if pd.notna(longitude)
                and status == "ADDRESS_VERIFIED"
                else None,
            "address_validation_status": status,
            "validation_reason":
                "; ".join(reasons)
                if reasons
                else "도로명, 건물번호 및 좌표 기본검사 통과",
            "operation_verified": False,
            "source_reference_year": 2020,
            "verified_at": datetime.now(
                KST
            ).isoformat(timespec="seconds"),
        })

        results.append(result)

        print()
        print(
            f"[{index + 1}/6] "
            f"{row['geocode_facility_name']}"
        )
        print(
            "원본:",
            normalize_address(original),
        )
        print(
            "반환:",
            normalize_address(returned),
        )
        print("검증:", status)

        if reasons:
            print("사유:", "; ".join(reasons))

    verified_df = pd.DataFrame(results)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    verified_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    counts = (
        verified_df["address_validation_status"]
        .value_counts()
        .to_dict()
    )

    summary = {
        "generated_at": datetime.now(
            KST
        ).isoformat(timespec="seconds"),
        "total_records": len(verified_df),
        "address_verified": int(
            counts.get("ADDRESS_VERIFIED", 0)
        ),
        "manual_review": int(
            counts.get("MANUAL_REVIEW", 0)
        ),
        "coordinate_duplicate_groups": len(
            duplicate_keys
        ),
        "source_reference_year": 2020,
        "operation_verified": False,
        "description": (
            "주소 표기 정규화와 도로명, "
            "건물번호 및 좌표 범위에 대한 "
            "기본 검증 결과. "
            "현장 확인이나 시설 운영 검증은 아님."
        ),
    }

    REPORT_PATH.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 65)
    print("검증 완료")
    print("=" * 65)

    print("전체:", len(verified_df))
    print(
        "주소 검증 통과:",
        counts.get("ADDRESS_VERIFIED", 0),
    )
    print(
        "수동 검토:",
        counts.get("MANUAL_REVIEW", 0),
    )

    print()
    print("결과 파일:", OUTPUT_PATH)
    print("검증 보고서:", REPORT_PATH)

    print()
    print(
        "주의: 주소 검증 통과는 "
        "현재 폐의약품 수거시설 운영을 "
        "확인했다는 뜻이 아닙니다."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"오류: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
