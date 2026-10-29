
import { useState } from 'react';

import {
    Calculator,
    ChevronDown,
    Database,
    Download,
    ExternalLink,
    FileWarning,
    Info,
    Link2,
} from 'lucide-react';

import type {
    Facility,
    MedicineData,
} from '../types/medicine';

import {
    exportDistrictCsv,
    exportFacilityCsv,
    exportMonthlyCsv,
} from '../services/exportCsv';

import './DataInformation.css';

interface DataInformationProps {
    data: MedicineData;
    filteredFacilities: Facility[];
}

type InformationTab =
    | 'sources'
    | 'methods'
    | 'limitations'
    | 'downloads';

interface SourceItem {
    title: string;
    period: string;
    purpose: string;
    note: string;
    url?: string;
    urlLabel?: string;
}

const SOURCE_ITEMS: SourceItem[] = [
    {
        title: '폐의약품 수거시설 공공데이터',
        period: '자치구별 기준일 상이',
        purpose: '시설명·주소·좌표 및 시설 기록 수',
        note:
            '9개 자치구의 공개 자료를 통합. 현재 운영 여부 미확인. 개별 원본 링크는 추가 검증 필요.',
    },
    {
        title: '서울시 등록인구(연령별·동별)',
        period: '분석 사용값: 2026년 2분기',
        purpose:
            '전체 인구 및 65세 이상 인구 대비 시설 기록 비율 계산',
        note:
            '주민등록인구를 기준으로 분석. 다운로드한 원본 CSV의 해당 분기 자료 사용.',
        url:
            'https://data.seoul.go.kr/dataList/OA-12235/S/1/datasetView.do',
        urlLabel: '서울 열린데이터광장 원본',
    },
    {
        title: '서울시 상권분석서비스(길단위인구-자치구)',
        period: '수집 CSV: 2026년 2분기',
        purpose: '보조 유동인구 분석 자료',
        note:
            '원본 CSV의 기준_년분기_코드 20262 확인. 주요 인구 대비 시설 비율은 주민등록인구 기준으로 계산.',
        url:
            'https://data.seoul.go.kr/dataList/OA-22179/A/1/datasetView.do',
        urlLabel: '서울 열린데이터광장 원본',
    },
    {
        title: '서울시 자치구별 월별 폐의약품 수거량',
        period: '2024년 1~12월',
        purpose:
            '월별 수거량 추이 및 합계·평균·변동성 분석',
        note:
            '공식 데이터 페이지에서 단위 kg 확인. 2024년 원본 CSV 사용.',
        url:
            'https://data.seoul.go.kr/dataList/OA-22374/F/1/datasetView.do',
        urlLabel: '서울 열린데이터광장 원본',
    },
];

const TABS: Array<{
    id: InformationTab;
    label: string;
    icon: typeof Database;
}> = [
        {
            id: 'sources',
            label: '분석 데이터',
            icon: Database,
        },
        {
            id: 'methods',
            label: '분석 방법',
            icon: Calculator,
        },
        {
            id: 'limitations',
            label: '데이터 한계',
            icon: FileWarning,
        },
        {
            id: 'downloads',
            label: 'CSV 다운로드',
            icon: Download,
        },
    ];

function InformationSectionTitle({
    title,
    description,
}: {
    title: string;
    description: string;
}) {
    return (
        <div className="data-detail-heading">
            <h3>{title}</h3>
            <p>{description}</p>
        </div>
    );
}

function DataInformation({
    data,
    filteredFacilities,
}: DataInformationProps) {
    const [open, setOpen] = useState(false);

    const [activeTab, setActiveTab] =
        useState<InformationTab>('sources');

    return (
        <section className="compact-data-info data-detail-section">
            <button
                type="button"
                className="data-info-toggle"
                aria-expanded={open}
                onClick={() => setOpen((previous) => !previous)}
            >
                <span>
                    <Database size={16} />
                    데이터 출처 및 분석 유의사항
                </span>

                <ChevronDown
                    size={17}
                    className={
                        open ? 'data-detail-chevron-open' : ''
                    }
                />
            </button>

            {open && (
                <div className="data-detail-content">
                    {/* 분석 자료 요약 */}

                    <div className="data-detail-overview">
                        <div>
                            <span>분석 대상</span>
                            <strong>
                                서울시{' '}
                                {data.metadata.coverage.district_count}개 구
                            </strong>
                        </div>

                        <div>
                            <span>시설 기록</span>
                            <strong>
                                {data.metadata.records.facility_count}건
                            </strong>
                        </div>

                        <div>
                            <span>인구 기준</span>
                            <strong>
                                {data.metadata.periods.population}
                            </strong>
                        </div>

                        <div>
                            <span>수거량 기준</span>
                            <strong>
                                {data.metadata.periods.collection_volume}년 · kg
                            </strong>
                        </div>
                    </div>

                    {/* 탭 메뉴 */}

                    <div
                        className="data-detail-tabs"
                        role="tablist"
                        aria-label="데이터 상세 정보"
                    >
                        {TABS.map((tab) => {
                            const TabIcon = tab.icon;

                            return (
                                <button
                                    key={tab.id}
                                    type="button"
                                    role="tab"
                                    id={`data-tab-${tab.id}`}
                                    aria-selected={activeTab === tab.id}
                                    aria-controls={`data-panel-${tab.id}`}
                                    className={
                                        activeTab === tab.id
                                            ? 'data-detail-tab active'
                                            : 'data-detail-tab'
                                    }
                                    onClick={() => setActiveTab(tab.id)}
                                >
                                    <TabIcon size={15} />
                                    {tab.label}
                                </button>
                            );
                        })}
                    </div>

                    <div
                        className="data-detail-panel"
                        role="tabpanel"
                        id={`data-panel-${activeTab}`}
                        aria-labelledby={`data-tab-${activeTab}`}
                    >
                        {/* ====================================
                분석 데이터
            ==================================== */}

                        {activeTab === 'sources' && (
                            <>
                                <InformationSectionTitle
                                    title="사용한 분석 데이터"
                                    description="공식 자료 출처, 분석 기준시점 및 활용 목적"
                                />

                                <div className="data-source-grid">
                                    {SOURCE_ITEMS.map((item) => (
                                        <article
                                            className="data-source-card"
                                            key={item.title}
                                        >
                                            <div className="data-source-card-heading">
                                                <strong>{item.title}</strong>
                                                <span>{item.period}</span>
                                            </div>

                                            <p>{item.purpose}</p>

                                            <small>{item.note}</small>

                                            {item.url && (
                                                <p>
                                                    <a
                                                        href={item.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        style={{
                                                            display: 'inline-flex',
                                                            alignItems: 'center',
                                                            gap: 5,
                                                            color: '#425bc5',
                                                            fontWeight: 600,
                                                            textDecoration: 'none',
                                                        }}
                                                    >
                                                        <ExternalLink size={13} />
                                                        {item.urlLabel ||
                                                            '원본 자료 확인'}
                                                    </a>
                                                </p>
                                            )}
                                        </article>
                                    ))}
                                </div>

                                <div className="data-detail-note">
                                    <Link2 size={16} />

                                    <p>
                                        등록인구, 길단위 유동인구,
                                        폐의약품 월별 수거량은 공식 데이터
                                        페이지를 연결했습니다.
                                        시설 위치 원본은 자치구별로
                                        출처가 달라 개별 자료 링크를
                                        추가 확인해야 합니다.
                                    </p>
                                </div>
                            </>
                        )}

                        {/* ====================================
                분석 방법
            ==================================== */}

                        {activeTab === 'methods' && (
                            <>
                                <InformationSectionTitle
                                    title="분석 방법 및 산식"
                                    description="통계 그래프와 요약 지표의 계산 기준"
                                />

                                <div className="data-method-list">
                                    <article>
                                        <strong>
                                            01. 전체 인구 대비 시설 기록 비율
                                        </strong>

                                        <div className="data-formula">
                                            시설 기록 수 ÷ 전체 주민등록인구
                                            × 10,000
                                        </div>

                                        <p>
                                            인구 규모가 다른 자치구 사이의
                                            시설 기록 비율 비교
                                        </p>
                                    </article>

                                    <article>
                                        <strong>
                                            02. 고령인구 대비 시설 기록 비율
                                        </strong>

                                        <div className="data-formula">
                                            시설 기록 수 ÷
                                            65세 이상 주민등록인구 × 10,000
                                        </div>

                                        <p>
                                            65세 이상 주민등록인구를 기준으로
                                            보정한 시설 기록 비율
                                        </p>
                                    </article>

                                    <article>
                                        <strong>
                                            03. 평균 최근접 시설 간 거리
                                        </strong>

                                        <div className="data-formula">
                                            각 시설에서 가장 가까운 다른
                                            수록 시설까지의 직선거리 평균
                                        </div>

                                        <p>
                                            시설 간 위치 간격을 나타내며,
                                            주민의 이동거리나 이동시간은
                                            의미하지 않음
                                        </p>
                                    </article>

                                    <article>
                                        <strong>
                                            04. Pearson 상관계수
                                        </strong>

                                        <div className="data-formula">
                                            r = Σ[(x − x̄)(y − ȳ)] ÷
                                            √(Σ(x − x̄)² × Σ(y − ȳ)²)
                                        </div>

                                        <p>
                                            9개 자치구의 65세 이상 인구 수와
                                            시설 기록 수 간 선형 관계 분석
                                        </p>
                                    </article>

                                    <article>
                                        <strong>
                                            05. 월별 폐의약품 수거량
                                        </strong>

                                        <div className="data-formula">
                                            월별 수거량(kg)의 합계,
                                            평균, 표준편차 및 변동계수 계산
                                        </div>

                                        <p>
                                            2024년 자료 사용.
                                            자치구 선택 시 해당 자치구의
                                            월별 기록만 집계
                                        </p>
                                    </article>
                                </div>
                            </>
                        )}

                        {/* ====================================
                데이터 한계
            ==================================== */}

                        {activeTab === 'limitations' && (
                            <>
                                <InformationSectionTitle
                                    title="해석 시 유의사항"
                                    description="분석 범위와 시설 자료의 제한사항"
                                />

                                <div className="data-limitations-list">
                                    <div className="data-limitation-item">
                                        <Info size={15} />
                                        <p>
                                            분석 대상은 서울시 전체 25개 구가
                                            아니라 원자료를 확보한 9개 구입니다.
                                        </p>
                                    </div>

                                    <div className="data-limitation-item">
                                        <Info size={15} />
                                        <p>
                                            수거시설 자료의 기준일은 자치구마다
                                            다르며, 현재 운영 여부는 확인되지
                                            않았습니다.
                                        </p>
                                    </div>

                                    <div className="data-limitation-item">
                                        <Info size={15} />
                                        <p>
                                            양천구 6건의 좌표는 2020년 공개
                                            자료의 주소를 기반으로 보완했습니다.
                                        </p>
                                    </div>

                                    <div className="data-limitation-item">
                                        <Info size={15} />
                                        <p>
                                            최근접 시설 간 직선거리는 실제
                                            도보 거리 또는 주민의 접근시간과
                                            다를 수 있습니다.
                                        </p>
                                    </div>

                                    <div className="data-limitation-item">
                                        <Info size={15} />
                                        <p>
                                            자료 기준일 필터는 시설 목록과
                                            지도에만 적용됩니다. 상단 요약과
                                            통계 그래프는 전체 원자료 기준입니다.
                                        </p>
                                    </div>

                                    <div className="data-limitation-item">
                                        <Info size={15} />
                                        <p>
                                            2024년 수거량과 2026년 인구,
                                            기준일이 서로 다른 시설 자료를
                                            직접 비교하여 시설 운영 효율을
                                            단정할 수 없습니다.
                                        </p>
                                    </div>
                                </div>

                                <div className="data-detail-warning">
                                    <FileWarning size={18} />
                                    <p>
                                        총 233건은 수집한 시설 기록 수이며,
                                        현재 운영 중인 실제 수거함 수를
                                        확정한 값은 아닙니다.
                                    </p>
                                </div>
                            </>
                        )}

                        {/* ====================================
                CSV 다운로드
            ==================================== */}

                        {activeTab === 'downloads' && (
                            <>
                                <InformationSectionTitle
                                    title="분석 결과 내려받기"
                                    description="웹사이트의 데이터와 분석 결과를 CSV로 저장"
                                />

                                <div className="data-download-grid">
                                    <button
                                        type="button"
                                        onClick={() =>
                                            exportDistrictCsv(
                                                data.districts,
                                                data.spatial,
                                            )
                                        }
                                    >
                                        <Download size={17} />

                                        <span>
                                            <strong>자치구별 분석</strong>
                                            <small>
                                                인구 대비 시설 비율 및 공간 지표
                                            </small>
                                        </span>
                                    </button>

                                    <button
                                        type="button"
                                        onClick={() =>
                                            exportFacilityCsv(data.facilities)
                                        }
                                    >
                                        <Download size={17} />

                                        <span>
                                            <strong>전체 수거시설 기록</strong>
                                            <small>
                                                시설명·주소·좌표·자료 기준일
                                            </small>
                                        </span>
                                    </button>

                                    <button
                                        type="button"
                                        onClick={() =>
                                            exportMonthlyCsv(data.monthly)
                                        }
                                    >
                                        <Download size={17} />

                                        <span>
                                            <strong>2024년 월별 수거량</strong>
                                            <small>
                                                자치구별 월별 처리량 · kg
                                            </small>
                                        </span>
                                    </button>

                                    <button
                                        type="button"
                                        disabled={
                                            filteredFacilities.length === 0
                                        }
                                        onClick={() =>
                                            exportFacilityCsv(
                                                filteredFacilities,
                                                'medicine_facilities_filtered.csv',
                                            )
                                        }
                                    >
                                        <Download size={17} />

                                        <span>
                                            <strong>현재 검색 결과</strong>
                                            <small>
                                                조건에 맞는 시설 기록{' '}
                                                {filteredFacilities.length}건
                                            </small>
                                        </span>
                                    </button>
                                </div>

                                <p className="data-download-caption">
                                    2024년 수거 처리량은 원본 수치를 그대로
                                    제공하며, 공식 측정 단위는 추가 확인이 필요합니다.
                                    시설의 현재 운영 여부도 별도 검증이 필요합니다.
                                </p>
                            </>
                        )}
                    </div>
                </div>
            )}
        </section>
    );
}

export default DataInformation;
