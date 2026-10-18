
from pathlib import Path

import pandas as pd


# ==========================================
# 프로젝트 기본 경로
# ==========================================

ROOT = Path(__file__).resolve().parents[1]

RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"

AUDIT = ROOT / "reports" / "audit"


# ==========================================
# 분석 대상 9개 자치구
# ==========================================

DISTRICTS = [
    "마포구",
    "양천구",
    "구로구",
    "관악구",
    "중구",
    "강동구",
    "서초구",
    "성북구",
    "중랑구",
]


# ==========================================
# CSV 파일 읽기
# ==========================================

def load_csv(path: Path) -> pd.DataFrame:

    encodings = [
        "utf-8-sig",
        "cp949",
        "euc-kr",
    ]

    for encoding in encodings:

        try:
            df = pd.read_csv(
                path,
                encoding=encoding,
                dtype=str,
                low_memory=False,
            )

            return df

        except UnicodeDecodeError:
            continue

    raise ValueError(
        f"CSV 인코딩 확인 실패: {path.name}"
    )


# ==========================================
# CSV 파일 저장
# ==========================================

def save_csv(
    df: pd.DataFrame,
    path: Path,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
    )


# ==========================================
# 수거시설 CSV 파일 찾기
# ==========================================

def find_facility_files():

    files = set(
        RAW.glob("*폐의약품*수거함*.csv")
    )

    files.update(
        RAW.glob("*폐의약품*수거함위치*.csv")
    )

    return sorted(files)
