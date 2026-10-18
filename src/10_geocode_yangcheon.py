
from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from dotenv import load_dotenv


# ==========================================
# 1. 경로 설정
# ==========================================

ROOT = Path(__file__).resolve().parents[1]

ENV_PATH = ROOT / ".env"

INPUT_CANDIDATES = [
    ROOT / "data" / "interim" / "facilities_standardized.csv",
    ROOT / "data" / "processed" / "facilities_standardized.csv",
]

OUTPUT_DIR = ROOT / "data" / "geocoded"
REPORT_DIR = ROOT / "reports" / "geocoding"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_ALL = OUTPUT_DIR / "yangcheon_geocoded.csv"
OUTPUT_REVIEW = OUTPUT_DIR / "yangcheon_review.csv"
OUTPUT_SUMMARY = REPORT_DIR / "yangcheon_summary.json"

API_URL = (
    "https://dapi.kakao.com/v2/local/search/address.json"
)

KST = ZoneInfo("Asia/Seoul")

# 대략적인 서울 서남부 범위 확인용.
# 행정경계 판정은 아님.
LAT_MIN = 37.40
LAT_MAX = 37.65
LON_MIN = 126.75
LON_MAX = 127.00

REQUEST_INTERVAL = 0.35

# 자동 승인에는 엄격한 조건 적용
STATUS_VERIFIED = "VERIFIED"
STATUS_REVIEW = "REVIEW"
STATUS_FAILED = "FAILED"


# ==========================================
# 2. 기본 함수
# ==========================================

def now_kst() -> str:
    return datetime.now(KST).isoformat(
        timespec="seconds"
    )


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def normalize_address(value: object) -> str:
    text = clean_text(value)

    text = unicodedata.normalize("NFKC", text)
    text = text.lower()

    text = re.sub(
        r"^대한민국\s*",
        "",
        text,
    )

    text = re.sub(
        r"^서울특별시\s*",
        "",
        text,
    )

    text = re.sub(
        r"^서울시\s*",
        "",
        text,
    )

    text = re.sub(r"\s+", "", text)

    return text


def has_yangcheon(value: object) -> bool:
    return "양천구" in normalize_address(value)


def find_column(
    dataframe: pd.DataFrame,
    candidates: list[str],
    required: bool = True,
) -> str | None:
    actual = {
        column.lower().strip(): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        result = actual.get(candidate.lower().strip())

        if result is not None:
            return result

    if required:
        raise ValueError(
            "필요한 컬럼을 찾을 수 없습니다.\n"
            f"후보: {candidates}\n"
            f"현재 컬럼: {list(dataframe.columns)}"
        )

    return None


def read_csv_file(path: Path) -> pd.DataFrame:
    last_error = None

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

        except UnicodeDecodeError as error:
            last_error = error

    raise RuntimeError(
        f"CSV 인코딩을 확인할 수 없습니다: {path}"
    ) from last_error


def find_input_file() -> Path:
    for path in INPUT_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "시설 전처리 파일을 찾을 수 없습니다.\n"
        "아래 경로를 확인하세요.\n"
        + "\n".join(str(p) for p in INPUT_CANDIDATES)
    )


# ==========================================
# 3. 데이터 읽기
# ==========================================

def load_yangcheon() -> pd.DataFrame:
    input_path = find_input_file()

    print(f"입력 파일: {input_path}")

    dataframe = read_csv_file(input_path)

    district_col = find_column(
        dataframe,
        [
            "district",
            "자치구",
            "시군구명",
            "시군구",
        ],
    )

    name_col = find_column(
        dataframe,
        [
            "facility_name",
            "name",
            "시설명",
            "수거함명",
            "수거함위치",
            "설치장소",
            "설치장소명",
        ],
        required=False,
    )

    address_col = find_column(
        dataframe,
        [
            "road_address",
            "address",
            "소재지도로명주소",
            "도로명주소",
            "주소",
            "소재지주소",
        ],
        required=False,
    )

    lot_address_col = find_column(
        dataframe,
        [
            "lot_address",
            "소재지지번주소",
            "지번주소",
        ],
        required=False,
    )

    if address_col is None and lot_address_col is None:
        raise ValueError(
            "도로명주소 또는 지번주소 컬럼이 필요합니다."
        )

    selected = dataframe[
        dataframe[district_col].map(clean_text) == "양천구"
    ].copy()

    if selected.empty:
        raise ValueError(
            "전처리 데이터에서 양천구 기록을 찾지 못했습니다."
        )

    if len(selected) != 6:
        raise ValueError(
            "기존에 확인한 양천구 6건과 "
            f"현재 입력 데이터 {len(selected)}건이 다릅니다.\n"
            "원본을 확인한 후 다시 실행하세요."
        )

    selected = selected.reset_index(drop=True)

    selected["geocode_source_row"] = [
        int(index) + 1
        for index in range(len(selected))
    ]

    selected["geocode_facility_name"] = (
        selected[name_col].map(clean_text)
        if name_col
        else "시설명 미제공"
    )

    if address_col:
        selected["geocode_input_address"] = (
            selected[address_col].map(clean_text)
        )
    else:
        selected["geocode_input_address"] = ""

    if lot_address_col:
        selected["geocode_input_lot_address"] = (
            selected[lot_address_col].map(clean_text)
        )
    else:
        selected["geocode_input_lot_address"] = ""

    return selected


# ==========================================
# 4. 카카오 API 호출
# ==========================================

def search_address(
    session: requests.Session,
    api_key: str,
    address: str,
) -> list[dict]:
    headers = {
        "Authorization": f"KakaoAK {api_key}",
    }

    params = {
        "query": address,
        "size": 10,
    }

    response = session.get(
        API_URL,
        headers=headers,
        params=params,
        timeout=15,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"HTTP {response.status_code}: "
            f"{response.text[:350]}"
        )

    payload = response.json()

    return payload.get("documents", [])


# ==========================================
# 5. 주소 후보 검사
# ==========================================

def get_candidate_address(
    document: dict,
) -> str:
    road = document.get("road_address") or {}
    lot = document.get("address") or {}

    return clean_text(
        road.get("address_name")
        or lot.get("address_name")
        or document.get("address_name")
    )


def get_match_status(
    original_address: str,
    document: dict,
) -> tuple[str, str]:
    road = document.get("road_address") or {}
    lot = document.get("address") or {}

    returned_addresses = [
        clean_text(road.get("address_name")),
        clean_text(lot.get("address_name")),
    ]

    returned_addresses = [
        address
        for address in returned_addresses
        if address
    ]

    if not returned_addresses:
        return STATUS_REVIEW, "반환 주소 없음"

    if not any(
        has_yangcheon(address)
        for address in returned_addresses
    ):
        return STATUS_REVIEW, "반환 주소가 양천구가 아님"

    try:
        latitude = float(document["y"])
        longitude = float(document["x"])
    except (KeyError, ValueError, TypeError):
        return STATUS_REVIEW, "좌표값 오류"

    if not (
        LAT_MIN <= latitude <= LAT_MAX
        and LON_MIN <= longitude <= LON_MAX
    ):
        return STATUS_REVIEW, "좌표 범위 수동 확인 필요"

    normalized_original = normalize_address(
        original_address
    )

    # 원본과 반환된 도로명/지번주소가
    # 완전히 일치할 때만 자동 승인.
    #
    # 상호명이나 상세주소까지 포함된 원본은
    # 다르게 나올 수 있으므로 검토 대상으로 둠.

    exact_match = any(
        normalized_original == normalize_address(address)
        for address in returned_addresses
    )

    if exact_match:
        return STATUS_VERIFIED, "주소 문자열 일치"

    return STATUS_REVIEW, "주소 문자열 불일치: 수동 확인"


def select_candidate(
    original_address: str,
    documents: list[dict],
) -> tuple[dict | None, str, str]:
    if not documents:
        return None, STATUS_FAILED, "검색 결과 없음"

    evaluated = []

    for document in documents:
        status, reason = get_match_status(
            original_address,
            document,
        )

        evaluated.append(
            (document, status, reason)
        )

    verified = [
        item
        for item in evaluated
        if item[1] == STATUS_VERIFIED
    ]

    # 후보가 여러 개이고 좌표가 서로 다르면
    # 모호한 검색 결과로 처리.
    if verified:
        positions = {
            (
                clean_text(item[0].get("x")),
                clean_text(item[0].get("y")),
            )
            for item in verified
        }

        if len(positions) == 1:
            return verified[0]

        return (
            verified[0][0],
            STATUS_REVIEW,
            "일치 후보들의 좌표가 서로 다름",
        )

    # 검증되지 않은 첫 후보는 참고용만 저장
    return evaluated[0]


# ==========================================
# 6. 양천구 지오코딩
# ==========================================

def geocode_yangcheon(
    dataframe: pd.DataFrame,
    api_key: str,
) -> pd.DataFrame:
    results = []

    with requests.Session() as session:
        for index, row in dataframe.iterrows():
            facility_name = clean_text(
                row["geocode_facility_name"]
            )

            road_address = clean_text(
                row["geocode_input_address"]
            )

            lot_address = clean_text(
                row["geocode_input_lot_address"]
            )

            address = road_address or lot_address

            print(
                f"\n[{index + 1}/{len(dataframe)}] "
                f"{facility_name}"
            )
            print(f"주소: {address}")

            output = {
                "geocode_query": address,
                "geocode_status": STATUS_FAILED,
                "geocode_reason": "",
                "geocode_returned_address": "",
                "geocode_latitude": None,
                "geocode_longitude": None,
                "geocode_candidate_count": 0,
                "geocode_provider": "Kakao Local API",
                "geocode_checked_at": now_kst(),
                "geocode_manual_approved": False,
                "geocode_manual_note": "",
            }

            if not address:
                output["geocode_reason"] = "원본 주소 없음"
                results.append(output)
                continue

            try:
                documents = search_address(
                    session,
                    api_key,
                    address,
                )

                output["geocode_candidate_count"] = len(
                    documents
                )

                # 도로명주소 결과가 없는 경우
                # 지번주소로 한 번 더 검색.
                if not documents and lot_address:
                    if lot_address != address:
                        documents = search_address(
                            session,
                            api_key,
                            lot_address,
                        )

                        output["geocode_query"] = lot_address
                        output["geocode_candidate_count"] = len(
                            documents
                        )

                candidate, status, reason = select_candidate(
                    output["geocode_query"],
                    documents,
                )

                output["geocode_status"] = status
                output["geocode_reason"] = reason

                if candidate:
                    output["geocode_returned_address"] = (
                        get_candidate_address(candidate)
                    )

                    try:
                        output["geocode_latitude"] = float(
                            candidate["y"]
                        )
                        output["geocode_longitude"] = float(
                            candidate["x"]
                        )
                    except (KeyError, ValueError, TypeError):
                        output["geocode_status"] = STATUS_REVIEW
                        output["geocode_reason"] = (
                            "좌표 변환 실패"
                        )

                print(
                    "결과:",
                    output["geocode_status"],
                    output["geocode_reason"],
                )

            except requests.RequestException as error:
                output["geocode_reason"] = (
                    f"네트워크 오류: {error}"
                )

                print(output["geocode_reason"])

            except RuntimeError as error:
                output["geocode_reason"] = str(error)

                print(output["geocode_reason"])

                # 인증 실패나 요청 제한은
                # 계속 호출하지 않고 즉시 중단.
                if (
                    "HTTP 401" in str(error)
                    or "HTTP 403" in str(error)
                    or "HTTP 429" in str(error)
                ):
                    raise RuntimeError(
                        "카카오 API 인증 또는 요청 제한 오류입니다. "
                        "REST API 키와 쿼터를 확인하세요."
                    ) from error

            results.append(output)

            time.sleep(REQUEST_INTERVAL)

    result_df = pd.concat(
        [
            dataframe.reset_index(drop=True),
            pd.DataFrame(results),
        ],
        axis=1,
    )

    return result_df


# ==========================================
# 7. 결과 저장
# ==========================================

def save_results(dataframe: pd.DataFrame) -> None:
    dataframe.to_csv(
        OUTPUT_ALL,
        index=False,
        encoding="utf-8-sig",
    )

    review = dataframe[
        dataframe["geocode_status"] != STATUS_VERIFIED
    ].copy()

    review.to_csv(
        OUTPUT_REVIEW,
        index=False,
        encoding="utf-8-sig",
    )

    status_counts = (
        dataframe["geocode_status"]
        .value_counts()
        .to_dict()
    )

    summary = {
        "project": "medicine-map",
        "task": "yangcheon_geocoding",
        "generated_at": now_kst(),
        "source_record_count": int(len(dataframe)),
        "verified_count": int(
            status_counts.get(STATUS_VERIFIED, 0)
        ),
        "review_count": int(
            status_counts.get(STATUS_REVIEW, 0)
        ),
        "failed_count": int(
            status_counts.get(STATUS_FAILED, 0)
        ),
        "source_facility_reference_year": 2020,
        "geocoding_is_operation_verification": False,
        "notes": [
            "원본 시설 데이터는 변경하지 않았습니다.",
            "자동 검증은 주소 문자열 일치 조건을 사용했습니다.",
            "위도 경도는 카카오 주소 검색 결과입니다.",
            "지오코딩 성공은 현재 운영 여부를 의미하지 않습니다.",
            "좌표는 공간 분석에 반영하기 전에 별도 확인이 필요합니다.",
        ],
    }

    OUTPUT_SUMMARY.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 65)
    print("10단계: 양천구 주소 지오코딩 결과")
    print("=" * 65)

    print(f"전체 기록: {len(dataframe)}건")
    print(
        "자동 검증:",
        status_counts.get(STATUS_VERIFIED, 0),
        "건",
    )
    print(
        "수동 검토:",
        status_counts.get(STATUS_REVIEW, 0),
        "건",
    )
    print(
        "변환 실패:",
        status_counts.get(STATUS_FAILED, 0),
        "건",
    )

    print()
    print(
        dataframe[
            [
                "geocode_facility_name",
                "geocode_input_address",
                "geocode_returned_address",
                "geocode_latitude",
                "geocode_longitude",
                "geocode_status",
            ]
        ].to_string(index=False)
    )

    print()
    print("저장 경로:")
    print(OUTPUT_ALL)
    print(OUTPUT_REVIEW)
    print(OUTPUT_SUMMARY)

    print()
    print(
        "주의: 좌표가 변환되더라도 "
        "현재 운영 중인 시설로 확정되지 않습니다."
    )


# ==========================================
# 8. 메인
# ==========================================

def main() -> None:
    print("=" * 65)
    print("양천구 폐의약품 수거시설 지오코딩")
    print("=" * 65)

    load_dotenv(ENV_PATH)

    api_key = os.getenv(
        "KAKAO_REST_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError(
            "KAKAO_REST_API_KEY가 없습니다.\n"
            f"{ENV_PATH} 파일을 확인하세요."
        )

    dataframe = load_yangcheon()

    result = geocode_yangcheon(
        dataframe,
        api_key,
    )

    save_results(result)


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print(
            f"\n작업 실패: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
