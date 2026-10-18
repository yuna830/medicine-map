
import pandas as pd

from common import (
    RAW,
    INTERIM,
    PROCESSED,
    DISTRICTS,
    load_csv,
    save_csv,
    find_facility_files,
)


# ==========================================
# 문자열 정리
# ==========================================

def clean_text(series):

    return (
        series.astype("string")
        .str.strip()
        .replace({
            "": pd.NA,
            "-": pd.NA,
        })
    )


# ==========================================
# 수거시설 데이터 표준화
# ==========================================

def standardize_facilities(path):

    raw = load_csv(path)

    gu = next(
        (
            district
            for district in DISTRICTS
            if district in path.name
        ),
        None,
    )

    if gu is None:
        raise ValueError(
            f"자치구 확인 실패: {path.name}"
        )

    # 원본 컬럼명을 공통 컬럼으로 변경
    aliases = {
        "설치장소명": "name",
        "수거함 위치명": "name",
        "소재지도로명주소": "road_address",
        "주소": "road_address",
        "소재지지번주소": "lot_address",
        "위도": "latitude",
        "경도": "longitude",
        "세부위치": "location_detail",
        "관리기관명": "manager",
        "관리기관전화번호": "phone",
        "전화번호": "phone",
        "데이터기준일자": "reference_date",
        "시군구명": "district",
    }

    out = raw.rename(
        columns=aliases
    )

    # 필수 컬럼 검사
    required = [
        "name",
        "road_address",
        "reference_date",
    ]

    absent = [
        col
        for col in required
        if col not in out.columns
    ]

    if absent:
        raise ValueError(
            f"{path.name}: 필수 컬럼 없음 {absent}"
        )

    standard_columns = [
        "name",
        "district",
        "road_address",
        "lot_address",
        "latitude",
        "longitude",
        "location_detail",
        "manager",
        "phone",
        "reference_date",
    ]

    # 존재하지 않는 선택 컬럼 추가
    for col in standard_columns:

        if col not in out.columns:
            out[col] = pd.NA

    out = out[standard_columns].copy()

    out["district"] = (
        out["district"].fillna(gu)
    )

    # 문자열 정리
    text_columns = [
        "name",
        "district",
        "road_address",
        "lot_address",
        "location_detail",
        "manager",
        "phone",
    ]

    for col in text_columns:
        out[col] = clean_text(
            out[col]
        )

    # 위도·경도 숫자 변환
    out["latitude"] = pd.to_numeric(
        out["latitude"],
        errors="coerce",
    )

    out["longitude"] = pd.to_numeric(
        out["longitude"],
        errors="coerce",
    )

    # 기준일 변환
    out["reference_date"] = (
        pd.to_datetime(
            out["reference_date"],
            errors="coerce",
        )
        .dt.strftime("%Y-%m-%d")
    )

    # 출처 기록
    out["source_file"] = path.name

    # 좌표 존재 여부
    out["has_coordinates"] = (
        out["latitude"].notna()
        & out["longitude"].notna()
    )

    # 서울시의 대략적 좌표 범위 검사
    out["coordinate_in_seoul_bbox"] = (
        out["latitude"].between(
            37.40, 37.75
        )
        & out["longitude"].between(
            126.75, 127.25
        )
    )

    return out


# ==========================================
# 2026년 2분기 인구 데이터 읽기
# ==========================================

def load_population_2026q2():

    path = (
        RAW
        / "등록인구(연령별_동별)_20261015230311.csv"
    )

    df = load_csv(path)

    # 9개 자치구의 인구 합계만 선택
    # '계'는 한국인+등록외국인
    df = df[
        (df["항목"] == "계")
        & (df["동별(1)"].isin(DISTRICTS))
    ].copy()

    # 2026년 2분기 총인구
    total_col = "2026 2/4"

    # 65세 이상 연령별 인구
    senior_cols = [
        f"2026 2/4.{i}"
        for i in range(14, 22)
    ]

    # 숫자로 변환
    for col in [total_col, *senior_cols]:

        if col not in df.columns:
            raise ValueError(
                f"인구 컬럼 없음: {col}"
            )

        df[col] = pd.to_numeric(
            df[col].str.replace(
                ",",
                "",
                regex=False,
            ),
            errors="coerce",
        )

    # 65세 이상 인구 합계
    df["population_65_plus"] = (
        df[senior_cols].sum(
            axis=1,
            min_count=len(senior_cols),
        )
    )

    population = df[
        [
            "동별(1)",
            total_col,
            "population_65_plus",
        ]
    ].rename(
        columns={
            "동별(1)": "district",
            total_col: "population_total",
        }
    )

    population["population_period"] = "2026-Q2"

    # 자치구 중복 및 누락 검증
    if (
        population["district"].duplicated().any()
        or len(population) != 9
    ):
        raise ValueError(
            "9개 자치구 인구 매칭 오류"
        )

    if population[
        [
            "population_total",
            "population_65_plus",
        ]
    ].isna().any().any():

        raise ValueError(
            "인구 데이터에 결측치가 있습니다."
        )

    return population


# ==========================================
# 전체 전처리
# ==========================================

def main():

    files = find_facility_files()

    if len(files) != 9:
        raise ValueError(
            f"시설 파일은 9개여야 합니다. "
            f"현재: {len(files)}개"
        )

    # 9개 파일 통합
    facilities = pd.concat(
        [
            standardize_facilities(path)
            for path in files
        ],
        ignore_index=True,
    )

    # 원본 행 개수 확인
    if len(facilities) != 233:
        print(
            "[주의] 기존 233개 기록과 "
            "현재 건수가 다릅니다."
        )

    # 시설 기록 ID
    facilities.insert(
        0,
        "record_id",
        range(1, len(facilities) + 1),
    )

    # 동일 시설 후보 찾기
    facilities["possible_duplicate"] = (
        facilities.duplicated(
            subset=[
                "district",
                "name",
                "road_address",
            ],
            keep=False,
        )
    )

    # 표준화된 시설 데이터 저장
    save_csv(
        facilities,
        INTERIM / "facilities_standardized.csv",
    )

    # 중복 의심 데이터 저장
    save_csv(
        facilities[
            facilities["possible_duplicate"]
        ],
        INTERIM / "possible_duplicates.csv",
    )

    # 좌표 없는 시설 저장
    save_csv(
        facilities[
            ~facilities["has_coordinates"]
        ],
        INTERIM / "missing_coordinates.csv",
    )

    # 서울 좌표 범위에서 벗어나는 자료
    save_csv(
        facilities[
            facilities["has_coordinates"]
            & ~facilities["coordinate_in_seoul_bbox"]
        ],
        INTERIM / "coordinate_bbox_review.csv",
    )

    # ======================================
    # 인구 데이터
    # ======================================

    population = load_population_2026q2()

    save_csv(
        population,
        INTERIM / "population_2026q2_9districts.csv",
    )

    # ======================================
    # 자치구별 시설 수 집계
    # ======================================

    counts = facilities.groupby(
        "district",
        as_index=False,
    ).agg(
        facility_records=(
            "record_id",
            "count",
        ),
        facilities_with_coordinates=(
            "has_coordinates",
            "sum",
        ),
        possible_duplicate_records=(
            "possible_duplicate",
            "sum",
        ),
        earliest_reference_date=(
            "reference_date",
            "min",
        ),
        latest_reference_date=(
            "reference_date",
            "max",
        ),
    )

    # ======================================
    # 인구 + 시설 데이터 결합
    # ======================================

    merged = population.merge(
        counts,
        on="district",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    # 결합 검증
    if not (
        merged["_merge"] == "both"
    ).all():

        raise ValueError(
            "시설·인구 결합에 실패한 자치구가 있습니다."
        )

    merged = merged.drop(
        columns=["_merge"]
    )

    # ======================================
    # 인구 1만 명당 시설 기록 수
    # ======================================

    merged["facilities_per_10000"] = (
        merged["facility_records"]
        / merged["population_total"]
        * 10000
    )

    # 65세 이상 인구 1만 명당 시설 기록 수
    merged["facilities_per_10000_seniors"] = (
        merged["facility_records"]
        / merged["population_65_plus"]
        * 10000
    )

    # ======================================
    # 최종 결과 저장
    # ======================================

    save_csv(
        merged,
        PROCESSED
        / "district_facility_population_2026q2.csv",
    )

    print()
    print("=== 9개 자치구 분석 데이터 ===")

    print(
        merged[
            [
                "district",
                "facility_records",
                "population_total",
                "population_65_plus",
                "facilities_per_10000",
            ]
        ].to_string(index=False)
    )

    print()
    print("전처리 및 데이터 결합 완료")
    print("저장 위치: data/interim, data/processed")

    print(
        "주의: 시설 자료의 기준일이 서로 다르므로 "
        "현재 결과는 탐색적 비교입니다."
    )


if __name__ == "__main__":
    main()
