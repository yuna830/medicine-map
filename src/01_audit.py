
import pandas as pd

from common import (
    RAW,
    AUDIT,
    DISTRICTS,
    load_csv,
    save_csv,
    find_facility_files,
)


def main():

    # ======================================
    # 전체 CSV 파일 목록
    # ======================================

    files = sorted(
        RAW.glob("*.csv")
    )

    if not files:
        raise FileNotFoundError(
            f"원본 CSV가 없습니다: {RAW}"
        )

    summaries = []
    columns = []
    missing = []

    facility_files = set(
        find_facility_files()
    )

    # ======================================
    # 파일별 데이터 확인
    # ======================================

    for path in files:

        df = load_csv(path)

        count = len(df)

        # 완전히 비어 있는 행
        blank_rows = int(
            df.isna().all(axis=1).sum()
        )

        # 공백을 정리한 뒤 중복 검사
        normalized = (
            df.fillna("")
            .apply(lambda col: col.str.strip())
        )

        duplicated = int(
            normalized.duplicated().sum()
        )

        # ==================================
        # 파일 기본 정보
        # ==================================

        summary = {
            "file": path.name,
            "rows": count,
            "columns": len(df.columns),
            "blank_rows": blank_rows,
            "duplicate_rows_exact": duplicated,
            "has_latitude": "위도" in df.columns,
            "has_longitude": "경도" in df.columns,
            "date_min": "",
            "date_max": "",
            "facility_gu": "",
        }

        # ==================================
        # 데이터 기준일 확인
        # ==================================

        if "데이터기준일자" in df.columns:

            dates = pd.to_datetime(
                df["데이터기준일자"],
                errors="coerce",
            ).dropna()

            if not dates.empty:

                summary["date_min"] = (
                    dates.min().date().isoformat()
                )

                summary["date_max"] = (
                    dates.max().date().isoformat()
                )

        # ==================================
        # 시설 파일의 자치구 확인
        # ==================================

        if path in facility_files:

            gu = next(
                (
                    district
                    for district in DISTRICTS
                    if district in path.name
                ),
                "",
            )

            summary["facility_gu"] = gu

        summaries.append(summary)

        # ==================================
        # 컬럼 목록 및 결측치 분석
        # ==================================

        for col in df.columns:

            columns.append({
                "file": path.name,
                "column": col,
            })

            missing_count = int(
                df[col].isna().sum()
            )

            missing_pct = (
                round(
                    missing_count / count * 100,
                    2,
                )
                if count > 0
                else 0
            )

            missing.append({
                "file": path.name,
                "column": col,
                "missing_count": missing_count,
                "missing_pct": missing_pct,
            })

        print(
            f"{path.name}: "
            f"{count}행, "
            f"{len(df.columns)}열, "
            f"중복 {duplicated}행"
        )

    # ======================================
    # 결과 저장
    # ======================================

    save_csv(
        pd.DataFrame(summaries),
        AUDIT / "file_summary.csv",
    )

    save_csv(
        pd.DataFrame(columns),
        AUDIT / "column_inventory.csv",
    )

    save_csv(
        pd.DataFrame(missing),
        AUDIT / "missing_values.csv",
    )

    print()
    print("데이터 감사 완료")
    print(f"저장 경로: {AUDIT}")

    print(f"원본 파일 수: {len(files)}")
    print(
        f"수거시설 파일 수: "
        f"{len(facility_files)}"
    )


if __name__ == "__main__":
    main()
