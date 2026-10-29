
import {
    useEffect,
    useMemo,
    useRef,
    useState,
} from 'react';

import {
    AlertCircle,
    BarChart3,
    Check,
    ChevronDown,
    Info,
    ScatterChart as ScatterIcon,
    TrendingUp,
    X,
} from 'lucide-react';

import {
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    Line,
    LineChart,
    ResponsiveContainer,
    Scatter,
    ScatterChart,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';

import type {
    District,
    MedicineData,
} from '../types/medicine';

import './AnalysisDashboard.css';

// ==========================================
// 1. 타입
// ==========================================

type Metric = 'population' | 'senior' | 'distance';

type DetailType =
    | 'metric'
    | 'monthly'
    | 'correlation';

interface AnalysisDashboardProps {
    districts: District[];
    monthly: MedicineData['monthly'];
    spatial: MedicineData['spatial'];
    selectedDistrict: string;
    onDistrictChange: (district: string) => void;
}

interface MetricRow {
    district: string;
    value: number | null;
    facility_records: number;
    population_total: number;
    population_65_plus: number;
}

interface ScatterRow {
    district: string;
    seniorTenThousands: number;
    population_65_plus: number;
    facilities: number;
    seniorRate: number;
}

interface MonthlyRow {
    month: string;
    monthNumber: number;
    value: number;
}

interface MonthlyStats {
    annualTotal: number;
    monthlyMean: number;
    monthlyStd: number;
    monthlyCv: number;
    highest: MonthlyRow;
    lowest: MonthlyRow;
}

interface MetricStats {
    highest: MetricRow & { value: number };
    lowest: MetricRow & { value: number };
    mean: number;
    gap: number;
    ratio: number | null;
}

// ==========================================
// 2. 기본 설정
// ==========================================

const ALL = '전체';

const formatter = new Intl.NumberFormat('ko-KR');

const METRIC_OPTIONS: Array<{
    value: Metric;
    label: string;
}> = [
        {
            value: 'population',
            label: '전체 인구 대비',
        },
        {
            value: 'senior',
            label: '고령인구 대비',
        },
        {
            value: 'distance',
            label: '시설 간 거리',
        },
    ];

// ==========================================
// 3. 공통 함수
// ==========================================

function formatNumber(value: number): string {
    return formatter.format(value);
}

function calculateRate(
    facilities: number,
    population: number,
): number {
    if (
        !Number.isFinite(population) ||
        population <= 0
    ) {
        return 0;
    }

    return facilities / population * 10000;
}

function getMetricValue(
    district: District,
    metric: Metric,
    spatialMeans: Record<string, number>,
): number | null {
    if (metric === 'population') {
        return district.population_total > 0
            ? calculateRate(
                district.facility_records,
                district.population_total,
            )
            : null;
    }

    if (metric === 'senior') {
        return district.population_65_plus > 0
            ? calculateRate(
                district.facility_records,
                district.population_65_plus,
            )
            : null;
    }

    const value = spatialMeans[district.district];

    return Number.isFinite(value) ? value : null;
}

function getMetricTitle(metric: Metric): string {
    switch (metric) {
        case 'population':
            return '전체 인구 1만 명당 시설';

        case 'senior':
            return '고령인구 1만 명당 시설';

        case 'distance':
            return '평균 최근접 시설 간 거리';
    }
}

function formatMetric(
    value: number,
    metric: Metric,
): string {
    return metric === 'distance'
        ? `${formatNumber(Math.round(value))}m`
        : `${value.toFixed(3)}건`;
}

function getAxisSettings(metric: Metric): {
    ticks: number[];
    maximum: number;
} {
    switch (metric) {
        case 'population':
            return {
                ticks: [0, 0.5, 1, 1.5, 2, 2.5],
                maximum: 2.5,
            };

        case 'senior':
            return {
                ticks: [0, 3, 6, 9, 12],
                maximum: 12,
            };

        case 'distance':
            return {
                ticks: [0, 300, 600, 900, 1200],
                maximum: 1200,
            };
    }
}

function formatAxisTick(
    value: number,
    metric: Metric,
): string {
    if (metric === 'population') {
        return Number(value.toFixed(1)).toString();
    }

    return formatNumber(value);
}

// ==========================================
// 4. Pearson 상관계수
// ==========================================

function calculatePearson(
    pairs: Array<{ x: number; y: number }>,
): number | null {
    const validPairs = pairs.filter(
        (pair) =>
            Number.isFinite(pair.x) &&
            Number.isFinite(pair.y),
    );

    if (validPairs.length < 3) return null;

    const n = validPairs.length;

    const meanX =
        validPairs.reduce(
            (sum, pair) => sum + pair.x,
            0,
        ) / n;

    const meanY =
        validPairs.reduce(
            (sum, pair) => sum + pair.y,
            0,
        ) / n;

    let numerator = 0;
    let denominatorX = 0;
    let denominatorY = 0;

    for (const pair of validPairs) {
        const dx = pair.x - meanX;
        const dy = pair.y - meanY;

        numerator += dx * dy;
        denominatorX += dx * dx;
        denominatorY += dy * dy;
    }

    const denominator = Math.sqrt(
        denominatorX * denominatorY,
    );

    if (denominator === 0) return null;

    return Math.max(
        -1,
        Math.min(1, numerator / denominator),
    );
}

function describeCorrelation(
    value: number | null,
): string {
    if (value === null) {
        return '상관계수 계산 불가';
    }

    const absolute = Math.abs(value);

    const direction =
        value > 0
            ? '양의'
            : value < 0
                ? '음의'
                : '';

    if (absolute < 0.2) {
        return '선형 관계가 매우 약한 편';
    }

    if (absolute < 0.4) {
        return `${direction} 선형 관계가 약한 편`;
    }

    if (absolute < 0.7) {
        return `${direction} 선형 관계가 중간 정도`;
    }

    return `${direction} 선형 관계가 강한 편`;
}

// ==========================================
// 5. 월별 처리량 통계
// ==========================================

function calculateMonthlyStats(
    rows: MonthlyRow[],
): MonthlyStats | null {
    if (rows.length !== 12) return null;

    const values = rows.map((row) => row.value);

    if (
        values.some(
            (value) => !Number.isFinite(value),
        )
    ) {
        return null;
    }

    const annualTotal = values.reduce(
        (sum, value) => sum + value,
        0,
    );

    const monthlyMean = annualTotal / values.length;

    // 12개월 전체에 대한 모집단 표준편차
    const variance =
        values.reduce(
            (sum, value) =>
                sum + (value - monthlyMean) ** 2,
            0,
        ) / values.length;

    const monthlyStd = Math.sqrt(variance);

    const monthlyCv =
        monthlyMean !== 0
            ? monthlyStd / monthlyMean * 100
            : 0;

    const highest = rows.reduce((a, b) =>
        a.value >= b.value ? a : b,
    );

    const lowest = rows.reduce((a, b) =>
        a.value <= b.value ? a : b,
    );

    return {
        annualTotal,
        monthlyMean,
        monthlyStd,
        monthlyCv,
        highest,
        lowest,
    };
}

// ==========================================
// 6. 자치구별 지표 통계
// ==========================================

function calculateMetricStats(
    rows: Array<MetricRow & { value: number }>,
): MetricStats | null {
    if (rows.length === 0) return null;

    const highest = rows[0];
    const lowest = rows[rows.length - 1];

    const mean =
        rows.reduce(
            (sum, row) => sum + row.value,
            0,
        ) / rows.length;

    const gap = highest.value - lowest.value;

    const ratio =
        lowest.value > 0
            ? highest.value / lowest.value
            : null;

    return {
        highest,
        lowest,
        mean,
        gap,
        ratio,
    };
}

// ==========================================
// 7. 산점도 툴팁
// ==========================================

function ScatterTooltip({
    active,
    payload,
}: {
    active?: boolean;
    payload?: ReadonlyArray<{
        payload?: unknown;
    }>;
}) {
    if (!active || !payload?.length) {
        return null;
    }

    const raw = payload[0]?.payload;

    if (
        !raw ||
        typeof raw !== 'object' ||
        !('district' in raw) ||
        !('population_65_plus' in raw) ||
        !('facilities' in raw) ||
        !('seniorRate' in raw)
    ) {
        return null;
    }

    const row = raw as ScatterRow;

    return (
        <div className="analysis-scatter-tooltip">
            <strong>{row.district}</strong>

            <div>
                <span>65세 이상 인구</span>
                <b>
                    {formatNumber(row.population_65_plus)}명
                </b>
            </div>

            <div>
                <span>시설 기록</span>
                <b>{row.facilities}건</b>
            </div>

            <div>
                <span>고령인구 1만 명당</span>
                <b>{row.seniorRate.toFixed(3)}건</b>
            </div>
        </div>
    );
}

// ==========================================
// 8. 메인 컴포넌트
// ==========================================

export default function AnalysisDashboard({
    districts,
    monthly,
    spatial,
    selectedDistrict,
    onDistrictChange,
}: AnalysisDashboardProps) {
    const [metric, setMetric] =
        useState<Metric>('population');

    const [menuOpen, setMenuOpen] =
        useState(false);

    // 세 그래프의 상세 팝업을 하나로 관리
    const [activeDetail, setActiveDetail] =
        useState<DetailType | null>(null);

    const menuRef = useRef<HTMLDivElement>(null);

    const closeRef =
        useRef<HTMLButtonElement>(null);

    const triggerRef =
        useRef<HTMLButtonElement | null>(null);

    // ========================================
    // 9. 상세 팝업 열기 및 닫기
    // ========================================

    function openDetail(
        type: DetailType,
        trigger: HTMLButtonElement,
    ) {
        triggerRef.current = trigger;
        setMenuOpen(false);
        setActiveDetail(type);
    }

    function closeDetail() {
        setActiveDetail(null);
    }

    // ========================================
    // 10. 지표 선택 메뉴
    // ========================================

    useEffect(() => {
        if (!menuOpen) return;

        function handlePointerDown(event: PointerEvent) {
            if (
                menuRef.current &&
                !menuRef.current.contains(event.target as Node)
            ) {
                setMenuOpen(false);
            }
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape') {
                setMenuOpen(false);
            }
        }

        document.addEventListener(
            'pointerdown',
            handlePointerDown,
        );

        document.addEventListener(
            'keydown',
            handleKeyDown,
        );

        return () => {
            document.removeEventListener(
                'pointerdown',
                handlePointerDown,
            );

            document.removeEventListener(
                'keydown',
                handleKeyDown,
            );
        };
    }, [menuOpen]);

    // ========================================
    // 11. 상세 팝업 이벤트
    // ========================================

    useEffect(() => {
        if (!activeDetail) return;

        const previousOverflow =
            document.body.style.overflow;

        document.body.style.overflow = 'hidden';

        closeRef.current?.focus();

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape') {
                setActiveDetail(null);
            }

            if (event.key !== 'Tab') return;

            const modal = document.querySelector(
                '.analysis-monthly-modal',
            );

            if (!(modal instanceof HTMLElement)) {
                return;
            }

            const buttons = Array.from(
                modal.querySelectorAll<HTMLButtonElement>(
                    'button:not([disabled])',
                ),
            );

            if (!buttons.length) return;

            const first = buttons[0];
            const last = buttons[buttons.length - 1];

            if (
                event.shiftKey &&
                document.activeElement === first
            ) {
                event.preventDefault();
                last.focus();
            } else if (
                !event.shiftKey &&
                document.activeElement === last
            ) {
                event.preventDefault();
                first.focus();
            }
        }

        document.addEventListener(
            'keydown',
            handleKeyDown,
        );

        return () => {
            document.body.style.overflow =
                previousOverflow;

            document.removeEventListener(
                'keydown',
                handleKeyDown,
            );

            triggerRef.current?.focus();
        };
    }, [activeDetail]);

    // ========================================
    // 12. 공간 분석 데이터
    // ========================================

    const spatialMeans = useMemo(
        () =>
            Object.fromEntries(
                spatial.districts.map((item) => [
                    item.district,
                    item.mean_nearest_m,
                ]),
            ) as Record<string, number>,
        [spatial],
    );

    // ========================================
    // 13. 왼쪽 그래프 데이터
    // ========================================

    const metricRows = useMemo<MetricRow[]>(() => {
        return districts
            .map((district) => ({
                district: district.district,
                value: getMetricValue(
                    district,
                    metric,
                    spatialMeans,
                ),
                facility_records:
                    district.facility_records,
                population_total:
                    district.population_total,
                population_65_plus:
                    district.population_65_plus,
            }))
            .sort((a, b) => {
                if (
                    a.value === null &&
                    b.value === null
                ) {
                    return a.district.localeCompare(
                        b.district,
                        'ko',
                    );
                }

                if (a.value === null) return 1;
                if (b.value === null) return -1;

                return b.value - a.value;
            });
    }, [districts, metric, spatialMeans]);

    const chartRows = useMemo(
        () =>
            metricRows.filter(
                (
                    row,
                ): row is MetricRow & {
                    value: number;
                } => row.value !== null,
            ),
        [metricRows],
    );

    const metricStats = useMemo(
        () => calculateMetricStats(chartRows),
        [chartRows],
    );

    const axisSettings = useMemo(
        () => getAxisSettings(metric),
        [metric],
    );

    // ========================================
    // 14. 월별 처리량 데이터
    // ========================================

    const monthlyRows = useMemo<MonthlyRow[]>(() => {
        const result = Array.from(
            { length: 12 },
            (_, index) => ({
                monthNumber: index + 1,
                month: `${index + 1}월`,
                value: 0,
            }),
        );

        for (const item of monthly) {
            if (
                selectedDistrict !== ALL &&
                item.district !== selectedDistrict
            ) {
                continue;
            }

            const month = Number(item.month);
            const amount = Number(item.collection_value);

            if (
                Number.isInteger(month) &&
                month >= 1 &&
                month <= 12 &&
                Number.isFinite(amount)
            ) {
                result[month - 1].value += amount;
            }
        }

        return result;
    }, [monthly, selectedDistrict]);

    const monthlyStats = useMemo(
        () => calculateMonthlyStats(monthlyRows),
        [monthlyRows],
    );

    const hasMonthlyData = useMemo(
        () =>
            monthly.some(
                (item) =>
                    (selectedDistrict === ALL ||
                        item.district === selectedDistrict) &&
                    Number.isInteger(Number(item.month)) &&
                    Number(item.month) >= 1 &&
                    Number(item.month) <= 12 &&
                    Number.isFinite(Number(item.collection_value)),
            ),
        [monthly, selectedDistrict],
    );

    // ========================================
    // 15. 산점도 및 상관계수
    // ========================================

    const scatterRows = useMemo<ScatterRow[]>(() => {
        return districts
            .filter(
                (district) =>
                    district.population_65_plus > 0 &&
                    Number.isFinite(
                        district.facility_records,
                    ),
            )
            .map((district) => ({
                district: district.district,
                seniorTenThousands:
                    district.population_65_plus / 10000,
                population_65_plus:
                    district.population_65_plus,
                facilities:
                    district.facility_records,
                seniorRate: calculateRate(
                    district.facility_records,
                    district.population_65_plus,
                ),
            }));
    }, [districts]);

    const pearson = useMemo(
        () =>
            calculatePearson(
                scatterRows.map((row) => ({
                    x: row.population_65_plus,
                    y: row.facilities,
                })),
            ),
        [scatterRows],
    );

    const ordinaryScatterRows = scatterRows.filter(
        (row) => row.district !== selectedDistrict,
    );

    const selectedScatterRows = scatterRows.filter(
        (row) => row.district === selectedDistrict,
    );

    const mostSeniorDistrict = useMemo(
        () =>
            [...scatterRows].sort(
                (a, b) =>
                    b.population_65_plus -
                    a.population_65_plus,
            )[0],
        [scatterRows],
    );

    const mostFacilitiesDistrict = useMemo(
        () =>
            [...scatterRows].sort(
                (a, b) => b.facilities - a.facilities,
            )[0],
        [scatterRows],
    );

    const fewestFacilitiesDistrict = useMemo(
        () =>
            [...scatterRows].sort(
                (a, b) => a.facilities - b.facilities,
            )[0],
        [scatterRows],
    );

    const totalSeniorPopulation = useMemo(
        () =>
            scatterRows.reduce(
                (sum, row) =>
                    sum + row.population_65_plus,
                0,
            ),
        [scatterRows],
    );

    const totalFacilities = useMemo(
        () =>
            scatterRows.reduce(
                (sum, row) => sum + row.facilities,
                0,
            ),
        [scatterRows],
    );

    // ========================================
    // 16. 하단 분석 문장
    // ========================================

    const metricInsight = useMemo(() => {
        const highest = chartRows[0];
        const lowest = chartRows.at(-1);

        if (!highest || !lowest) {
            return '분석 가능한 데이터가 없습니다.';
        }

        if (metric === 'distance') {
            const ratio =
                lowest.value > 0
                    ? highest.value / lowest.value
                    : null;

            return (
                `${highest.district}의 평균 최근접 시설 거리는 ` +
                `약 ${Math.round(highest.value)}m로, ` +
                `${lowest.district}(${Math.round(lowest.value)}m)의 ` +
                (ratio !== null
                    ? `약 ${ratio.toFixed(1)}배입니다.`
                    : '값보다 깁니다.') +
                ' 시설 간 직선거리 비교이며 실제 이동거리는 아닙니다.'
            );
        }

        if (metric === 'senior') {
            return (
                `${highest.district} ${highest.value.toFixed(3)}건, ` +
                `${lowest.district} ${lowest.value.toFixed(3)}건으로 ` +
                '고령인구 대비 시설 기록 비율에 차이가 있습니다.'
            );
        }

        const ratio =
            lowest.value > 0
                ? highest.value / lowest.value
                : null;

        const withoutYangcheon = chartRows.filter(
            (row) => row.district !== '양천구',
        );

        const first = withoutYangcheon[0];
        const last = withoutYangcheon.at(-1);

        const sensitivityRatio =
            first && last && last.value > 0
                ? first.value / last.value
                : null;

        return (
            `${highest.district}와 ${lowest.district}의 ` +
            '인구 대비 시설 기록 비율은 ' +
            (ratio === null
                ? '비교할 수 없습니다.'
                : `약 ${ratio.toFixed(1)}배 차이입니다.`) +
            (sensitivityRatio !== null
                ? ` 양천구 제외 시 약 ${sensitivityRatio.toFixed(1)}배입니다.`
                : '')
        );
    }, [chartRows, metric]);

    const correlationInsight =
        pearson === null
            ? '고령인구와 시설 기록 수의 상관계수를 계산할 수 없습니다.'
            : `고령인구와 시설 기록 수의 Pearson r = ${pearson.toFixed(3)} (${describeCorrelation(pearson)}).`;

    // ========================================
    // 17. 상세 팝업 제목
    // ========================================

    const modalTitle =
        activeDetail === 'monthly'
            ? '2024년 수거 처리량 분석'
            : activeDetail === 'correlation'
                ? '고령인구와 수거시설 수 분석'
                : `${getMetricTitle(metric)} 분석`;

    const modalSubtitle =
        activeDetail === 'monthly'
            ? selectedDistrict === ALL
                ? '9개 자치구 월별 합계'
                : `${selectedDistrict} 월별 통계`
            : activeDetail === 'correlation'
                ? `${scatterRows.length}개 자치구 · 상관관계 분석`
                : `${chartRows.length}개 자치구 · 지역별 비교`;

    // ========================================
    // 18. 화면 렌더링
    // ========================================

    return (
        <section
            id="analysis"
            className="compact-analysis"
        >
            <div className="section-title-row">
                <h2>지역별 데이터 분석</h2>

                <label className="analysis-region-select">
                    <span className="analysis-sr-only">
                        분석 자치구 선택
                    </span>

                    <select
                        value={selectedDistrict}
                        onChange={(event) =>
                            onDistrictChange(
                                event.target.value,
                            )
                        }
                    >
                        <option value={ALL}>
                            전체 자치구
                        </option>

                        {districts.map((district) => (
                            <option
                                key={district.district}
                                value={district.district}
                            >
                                {district.district}
                            </option>
                        ))}
                    </select>

                    <ChevronDown size={13} />
                </label>
            </div>

            <div className="analysis-dashboard-grid">
                {/* ==================================
            왼쪽: 지역별 지표 그래프
        ================================== */}

                <div className="dashboard-card analysis-chart-card">
                    <div className="dashboard-card-header">
                        <div>
                            <h3>{getMetricTitle(metric)}</h3>

                            <p>
                                {metric === 'distance'
                                    ? `좌표 보유 ${spatial.district_count}개 구 · 직선거리`
                                    : '2026년 2분기 주민등록인구 기준'}
                            </p>
                        </div>


                        <div className="analysis-metric-menu" ref={menuRef}>
                            <button
                                type="button"
                                className="analysis-chart-icon"
                                aria-label="지역별 지표 상세 분석"
                                aria-haspopup="dialog"
                                title="상세 분석"
                                onClick={(event) =>
                                    openDetail('metric', event.currentTarget)
                                }
                            >
                                <Info size={17} />
                            </button>

                            <button
                                type="button"
                                className={`analysis-chart-icon ${menuOpen ? 'active' : ''
                                    }`}
                                aria-label="분석 지표 변경"
                                aria-haspopup="menu"
                                aria-expanded={menuOpen}
                                onClick={() =>
                                    setMenuOpen((previous) => !previous)
                                }
                            >
                                <BarChart3 size={17} />
                                <ChevronDown size={11} />
                            </button>

                            {menuOpen && (
                                <div
                                    className="analysis-metric-dropdown"
                                    role="menu"
                                    aria-label="분석 지표 선택"
                                >
                                    {METRIC_OPTIONS.map((option) => (
                                        <button
                                            key={option.value}
                                            type="button"
                                            role="menuitemradio"
                                            aria-checked={metric === option.value}
                                            className={
                                                metric === option.value ? 'selected' : ''
                                            }
                                            onClick={() => {
                                                setMetric(option.value);
                                                setMenuOpen(false);
                                            }}
                                        >
                                            <span>{option.label}</span>

                                            {metric === option.value && (
                                                <Check size={13} />
                                            )}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>

                    </div>

                    <div className="analysis-chart-area">
                        <ResponsiveContainer
                            width="100%"
                            height="100%"
                        >
                            <BarChart
                                data={chartRows}
                                layout="vertical"
                                margin={{
                                    top: 5,
                                    right: 15,
                                    bottom: 5,
                                    left: -8,
                                }}
                            >
                                <CartesianGrid
                                    horizontal={false}
                                    stroke="#edf1f5"
                                    strokeDasharray="3 3"
                                />

                                <XAxis
                                    type="number"
                                    domain={[
                                        0,
                                        axisSettings.maximum,
                                    ]}
                                    ticks={axisSettings.ticks}
                                    allowDecimals
                                    tickFormatter={(value: number) =>
                                        formatAxisTick(value, metric)
                                    }
                                    tick={{ fontSize: 10 }}
                                    axisLine={false}
                                    tickLine={false}
                                />

                                <YAxis
                                    type="category"
                                    dataKey="district"
                                    width={51}
                                    tick={{ fontSize: 11 }}
                                    axisLine={false}
                                    tickLine={false}
                                />

                                <Tooltip
                                    cursor={{
                                        fill: 'rgba(100, 124, 221, 0.06)',
                                    }}
                                    contentStyle={{
                                        backgroundColor: '#fff',
                                        border: '1px solid #e1e7ef',
                                        borderRadius: '8px',
                                        padding: '7px 10px',
                                        boxShadow:
                                            '0 3px 12px rgba(20,35,65,0.08)',
                                        fontSize: '11px',
                                    }}
                                    labelStyle={{
                                        color: '#26344b',
                                        fontSize: '11px',
                                        fontWeight: 700,
                                        marginBottom: '3px',
                                    }}
                                    itemStyle={{
                                        color: '#64748b',
                                        fontSize: '10px',
                                        padding: 0,
                                    }}
                                    formatter={(value) => [
                                        formatMetric(
                                            Number(value),
                                            metric,
                                        ),
                                        getMetricTitle(metric),
                                    ]}
                                />


                                <Bar
                                    onClick={(entry: unknown) => {
                                        const row = entry as {
                                            district?: string;
                                            payload?: {
                                                district?: string;
                                            };
                                        };

                                        const clickedDistrict =
                                            row.payload?.district ??
                                            row.district;

                                        if (clickedDistrict) {
                                            onDistrictChange(clickedDistrict);
                                        }
                                    }}
                                    cursor="pointer"
                                    dataKey="value"
                                    maxBarSize={17}
                                    radius={[0, 4, 4, 0]}
                                >

                                    {chartRows.map((row) => (
                                        <Cell
                                            key={row.district}
                                            fill={
                                                selectedDistrict === row.district
                                                    ? '#3657c8'
                                                    : '#697ddb'
                                            }
                                        />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>


                    <div className="dashboard-card-footer">
                        {metric === 'distance'
                            ? '시설 간 최근접 직선거리(m) · 9개 구'
                            : '자치구별 시설 자료 기준일 상이'}
                    </div>

                </div>

                {/* ==================================
            가운데: 월별 처리량 그래프
        ================================== */}

                <div className="dashboard-card analysis-chart-card">
                    <div className="dashboard-card-header">
                        <div>
                            <h3>2024년 월별 수거 처리량</h3>

                            <p>
                                {selectedDistrict === ALL
                                    ? '9개 자치구 월별 합계'
                                    : `${selectedDistrict} 월별 처리량`}
                            </p>
                        </div>

                        <button
                            type="button"
                            className="analysis-chart-icon"
                            aria-label="월별 수거 처리량 상세 분석"
                            aria-haspopup="dialog"
                            onClick={(event) =>
                                openDetail(
                                    'monthly',
                                    event.currentTarget,
                                )
                            }
                        >
                            <TrendingUp size={17} />
                        </button>
                    </div>

                    <div className="analysis-chart-area">
                        {hasMonthlyData ? (
                            <ResponsiveContainer
                                width="100%"
                                height="100%"
                            >
                                <LineChart
                                    data={monthlyRows}
                                    margin={{
                                        top: 10,
                                        right: 12,
                                        bottom: 3,
                                        left: -12,
                                    }}
                                >
                                    <CartesianGrid
                                        stroke="#edf1f5"
                                        strokeDasharray="3 3"
                                    />

                                    <XAxis
                                        dataKey="month"
                                        tick={{ fontSize: 10 }}
                                        axisLine={false}
                                        tickLine={false}
                                    />

                                    <YAxis
                                        tick={{ fontSize: 10 }}
                                        axisLine={false}
                                        tickLine={false}
                                        tickFormatter={(value: number) =>
                                            formatNumber(value)
                                        }
                                    />

                                    <Tooltip
                                        contentStyle={{
                                            backgroundColor: '#fff',
                                            border: '1px solid #e1e7ef',
                                            borderRadius: '8px',
                                            padding: '7px 10px',
                                            boxShadow:
                                                '0 3px 12px rgba(20,35,65,0.08)',
                                            fontSize: '11px',
                                        }}
                                        labelStyle={{
                                            color: '#26344b',
                                            fontSize: '11px',
                                            fontWeight: 700,
                                        }}
                                        itemStyle={{
                                            color: '#64748b',
                                            fontSize: '10px',
                                            padding: 0,
                                        }}
                                        formatter={(value) => [
                                            formatNumber(Number(value)),
                                            '원자료 수치',
                                        ]}
                                    />

                                    <Line
                                        type="monotone"
                                        dataKey="value"
                                        stroke="#439488"
                                        strokeWidth={2.5}
                                        dot={{ r: 2.5 }}
                                        activeDot={{ r: 5 }}
                                    />
                                </LineChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="analysis-empty-chart">
                                해당 자치구의 월별 처리량 자료가 없습니다.
                            </div>
                        )}
                    </div>

                    <div className="dashboard-card-footer">
                        아이콘 클릭 시 상세 통계 · 공식 단위 확인 필요
                    </div>
                </div>

                {/* ==================================
            오른쪽: 고령인구 산점도
        ================================== */}

                <div className="dashboard-card analysis-chart-card">
                    <div className="dashboard-card-header">
                        <div>
                            <h3>고령인구와 수거시설 수</h3>

                            <p>
                                9개 자치구 · 고령인구와 시설 기록 비교
                            </p>
                        </div>

                        <button
                            type="button"
                            className="analysis-chart-icon"
                            aria-label="고령인구와 수거시설 수 상세 분석"
                            aria-haspopup="dialog"
                            onClick={(event) =>
                                openDetail(
                                    'correlation',
                                    event.currentTarget,
                                )
                            }
                        >
                            <ScatterIcon size={17} />
                        </button>
                    </div>

                    <div className="analysis-chart-area">
                        <ResponsiveContainer
                            width="100%"
                            height="100%"
                        >
                            <ScatterChart
                                margin={{
                                    top: 12,
                                    right: 15,
                                    bottom: 7,
                                    left: -14,
                                }}
                            >
                                <CartesianGrid
                                    stroke="#edf1f5"
                                    strokeDasharray="3 3"
                                />

                                <XAxis
                                    type="number"
                                    dataKey="seniorTenThousands"
                                    name="65세 이상 인구"
                                    unit="만"
                                    domain={[0, 12]}
                                    ticks={[0, 3, 6, 9, 12]}
                                    tick={{ fontSize: 10 }}
                                    axisLine={false}
                                    tickLine={false}
                                />

                                <YAxis
                                    type="number"
                                    dataKey="facilities"
                                    name="시설 기록"
                                    domain={[0, 50]}
                                    ticks={[0, 10, 20, 30, 40, 50]}
                                    allowDecimals={false}
                                    tick={{ fontSize: 10 }}
                                    axisLine={false}
                                    tickLine={false}
                                />

                                <Tooltip
                                    cursor={{ strokeDasharray: '3 3' }}
                                    content={({ active, payload }) => (
                                        <ScatterTooltip
                                            active={active}
                                            payload={payload}
                                        />
                                    )}
                                />

                                <Scatter
                                    name="전체 자치구"
                                    data={ordinaryScatterRows}
                                    fill="#687ddb"
                                />

                                {selectedScatterRows.length > 0 && (
                                    <Scatter
                                        name="선택 자치구"
                                        data={selectedScatterRows}
                                        fill="#ed8063"
                                    />
                                )}
                            </ScatterChart>
                        </ResponsiveContainer>
                    </div>

                    <div className="dashboard-card-footer analysis-correlation-footer">
                        <span>
                            Pearson r:{' '}
                            <strong>
                                {pearson === null
                                    ? '계산 불가'
                                    : pearson.toFixed(3)}
                            </strong>
                        </span>

                        <span>
                            분석 대상 {scatterRows.length}개 구
                        </span>
                    </div>
                </div>
            </div>

            {/* ==================================
          하단 분석 결과
      ================================== */}

            <div className="analysis-insight-grid">
                <div className="analysis-metric-insight">
                    <BarChart3 size={15} />

                    <div>
                        <strong>{getMetricTitle(metric)}</strong>
                        <p>{metricInsight}</p>
                    </div>
                </div>

                <div className="analysis-metric-insight">
                    <ScatterIcon size={15} />

                    <div>
                        <strong>
                            고령인구와 시설 수의 관계
                        </strong>
                        <p>{correlationInsight}</p>
                    </div>
                </div>
            </div>

            {/* ==================================
          공통 상세 팝업
      ================================== */}

            {activeDetail && (
                <div
                    className="analysis-monthly-backdrop"
                    onMouseDown={(event) => {
                        if (event.target === event.currentTarget) {
                            closeDetail();
                        }
                    }}
                >
                    <div
                        className="analysis-monthly-modal"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="analysis-detail-title"
                    >
                        <div className="analysis-monthly-header">
                            <div className="analysis-monthly-heading">
                                <span className="analysis-monthly-icon">
                                    {activeDetail === 'monthly' ? (
                                        <TrendingUp size={17} />
                                    ) : activeDetail === 'correlation' ? (
                                        <ScatterIcon size={17} />
                                    ) : (
                                        <BarChart3 size={17} />
                                    )}
                                </span>

                                <div>
                                    <h2 id="analysis-detail-title">
                                        {modalTitle}
                                    </h2>

                                    <p>{modalSubtitle}</p>
                                </div>
                            </div>

                            <button
                                ref={closeRef}
                                type="button"
                                className="analysis-monthly-close"
                                aria-label="상세 분석 닫기"
                                onClick={closeDetail}
                            >
                                <X size={18} />
                            </button>
                        </div>

                        <div className="analysis-monthly-body">
                            {/* ==============================
                  1. 지역별 지표 상세
              ============================== */}

                            {activeDetail === 'metric' && (
                                metricStats ? (
                                    <div className="analysis-monthly-columns">
                                        <div className="analysis-monthly-left">
                                            <span className="analysis-monthly-label">
                                                {metric === 'distance'
                                                    ? '9개 구 시설 간 평균 최근접 직선거리'
                                                    : `분석 대상 ${chartRows.length}개 구의 지표 평균`}
                                            </span>

                                            <div className="analysis-monthly-total">
                                                {formatMetric(
                                                    metric === 'distance'
                                                        ? spatial.mean_nearest_m
                                                        : metricStats.mean,
                                                    metric,
                                                )}
                                            </div>

                                            <p className="analysis-monthly-description">
                                                {metric === 'distance'
                                                    ? '233개 시설 각각에서 가장 가까운 다른 수록 시설까지의 직선거리를 계산했습니다.'
                                                    : '자치구별 시설 기록 수를 인구 규모로 보정하여 지역 간 차이를 비교했습니다.'}
                                            </p>

                                            <div className="analysis-monthly-table">
                                                <div>
                                                    <span>분석 대상</span>
                                                    <strong>
                                                        {chartRows.length}개 구
                                                    </strong>
                                                </div>

                                                <div>
                                                    <span>최고 자치구</span>
                                                    <strong>
                                                        {metricStats.highest.district}
                                                        {' · '}
                                                        {formatMetric(
                                                            metricStats.highest.value,
                                                            metric,
                                                        )}
                                                    </strong>
                                                </div>

                                                <div>
                                                    <span>최저 자치구</span>
                                                    <strong>
                                                        {metricStats.lowest.district}
                                                        {' · '}
                                                        {formatMetric(
                                                            metricStats.lowest.value,
                                                            metric,
                                                        )}
                                                    </strong>
                                                </div>

                                                <div>
                                                    <span>최고·최저 차이</span>
                                                    <strong>
                                                        {formatMetric(
                                                            metricStats.gap,
                                                            metric,
                                                        )}
                                                    </strong>
                                                </div>

                                                <div>
                                                    <span>최고 / 최저 비율</span>
                                                    <strong>
                                                        {metricStats.ratio === null
                                                            ? '계산 불가'
                                                            : `약 ${metricStats.ratio.toFixed(1)}배`}
                                                    </strong>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="analysis-monthly-right">
                                            <h3>
                                                <BarChart3 size={15} />
                                                분석 결과
                                            </h3>

                                            <p>
                                                {metricStats.highest.district}의 값은{' '}
                                                <strong>
                                                    {formatMetric(
                                                        metricStats.highest.value,
                                                        metric,
                                                    )}
                                                </strong>
                                                이며, {metricStats.lowest.district}는{' '}
                                                <strong>
                                                    {formatMetric(
                                                        metricStats.lowest.value,
                                                        metric,
                                                    )}
                                                </strong>
                                                입니다.
                                            </p>

                                            <p>{metricInsight}</p>

                                            <h3>
                                                <AlertCircle size={15} />
                                                데이터 유의사항
                                            </h3>

                                            {metric === 'distance' ? (
                                                <>
                                                    <p>
                                                        자치구별 평균은 해당 구의 시설 기록에
                                                        대한 평균이며, 전체 평균은 233개
                                                        시설 기록을 기준으로 계산했습니다.
                                                    </p>

                                                    <p>
                                                        시설 간 직선거리는 주민의 실제
                                                        이동거리나 접근시간을 의미하지 않습니다.
                                                    </p>

                                                    <p>
                                                        양천구 6건은 2020년 주소 기반
                                                        좌표 보완 자료이며 현재 운영 여부는
                                                        확인되지 않았습니다.
                                                    </p>
                                                </>
                                            ) : (
                                                <>
                                                    <p>
                                                        인구는 2026년 2분기 기준이고
                                                        수거시설 자료의 기준일은
                                                        자치구마다 다릅니다.
                                                    </p>

                                                    <p>
                                                        인구 대비 시설 기록 비율은 실제
                                                        주민의 이동 편의성이나 시설 운영
                                                        수준을 직접 나타내지는 않습니다.
                                                    </p>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                ) : (
                                    <p className="analysis-monthly-description">
                                        통계를 계산할 자료가 없습니다.
                                    </p>
                                )
                            )}

                            {/* ==============================
                  2. 월별 처리량 상세
              ============================== */}

                            {activeDetail === 'monthly' && (
                                monthlyStats && hasMonthlyData ? (
                                    <div className="analysis-monthly-columns">
                                        <div className="analysis-monthly-left">
                                            <span className="analysis-monthly-label">
                                                12개월 원자료 합계
                                            </span>

                                            <div className="analysis-monthly-total">
                                                {formatNumber(
                                                    monthlyStats.annualTotal,
                                                )}
                                            </div>

                                            <p className="analysis-monthly-description">
                                                선택한 지역의 월별 기록 12개를
                                                합산하고 월평균 및 월별 변동성을
                                                계산한 결과입니다.
                                            </p>

                                            <div className="analysis-monthly-table">
                                                <div>
                                                    <span>월평균 처리량</span>
                                                    <strong>
                                                        {formatNumber(
                                                            Math.round(
                                                                monthlyStats.monthlyMean,
                                                            ),
                                                        )}
                                                    </strong>
                                                </div>

                                                <div>
                                                    <span>월별 표준편차</span>
                                                    <strong>
                                                        {formatNumber(
                                                            Math.round(
                                                                monthlyStats.monthlyStd,
                                                            ),
                                                        )}
                                                    </strong>
                                                </div>

                                                <div>
                                                    <span>변동계수(CV)</span>
                                                    <strong>
                                                        {monthlyStats.monthlyCv.toFixed(1)}%
                                                    </strong>
                                                </div>

                                                <div>
                                                    <span>최고 처리량 월</span>
                                                    <strong>
                                                        {monthlyStats.highest.month}
                                                        {' · '}
                                                        {formatNumber(
                                                            monthlyStats.highest.value,
                                                        )}
                                                    </strong>
                                                </div>

                                                <div>
                                                    <span>최저 처리량 월</span>
                                                    <strong>
                                                        {monthlyStats.lowest.month}
                                                        {' · '}
                                                        {formatNumber(
                                                            monthlyStats.lowest.value,
                                                        )}
                                                    </strong>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="analysis-monthly-right">
                                            <h3>
                                                <TrendingUp size={15} />
                                                분석 결과
                                            </h3>

                                            <p>
                                                가장 높은 처리량을 기록한 달은{' '}
                                                <strong>
                                                    {monthlyStats.highest.month}
                                                </strong>
                                                이며, 가장 낮은 달은{' '}
                                                <strong>
                                                    {monthlyStats.lowest.month}
                                                </strong>
                                                입니다.
                                            </p>

                                            <p>
                                                월별 변동계수는{' '}
                                                <strong>
                                                    {monthlyStats.monthlyCv.toFixed(1)}%
                                                </strong>
                                                입니다. 변동계수는 월평균 대비
                                                처리량이 얼마나 변동하는지를
                                                보여주는 기술통계 지표입니다.
                                            </p>

                                            <h3>
                                                <AlertCircle size={15} />
                                                데이터 유의사항
                                            </h3>

                                            <p>
                                                공식 측정 단위는 추가 확인이
                                                필요하므로 원자료 수치로 표기했습니다.
                                            </p>

                                            <p>
                                                월별 수치를 합산한 결과는
                                                공식 연간 보고 합계와 일부 다를 수 있으며,
                                                이를 자동 보정하지 않았습니다.
                                            </p>

                                            <p>
                                                2024년 처리량과 서로 다른 기준일의
                                                시설 자료를 직접 연결하여
                                                운영 효율로 해석할 수는 없습니다.
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <p className="analysis-monthly-description">
                                        통계를 계산할 자료가 없습니다.
                                    </p>
                                )
                            )}

                            {/* ==============================
                  3. 산점도 상관관계 상세
              ============================== */}

                            {activeDetail === 'correlation' && (
                                <div className="analysis-monthly-columns">
                                    <div className="analysis-monthly-left">
                                        <span className="analysis-monthly-label">
                                            Pearson 상관계수 (r)
                                        </span>

                                        <div className="analysis-monthly-total">
                                            {pearson === null
                                                ? '계산 불가'
                                                : pearson.toFixed(3)}
                                        </div>

                                        <p className="analysis-monthly-description">
                                            9개 자치구의 65세 이상 인구 수와
                                            수거시설 기록 수 사이의
                                            선형 관계를 분석한 결과입니다.
                                        </p>

                                        <div className="analysis-monthly-table">
                                            <div>
                                                <span>분석 대상</span>
                                                <strong>
                                                    {scatterRows.length}개 구
                                                </strong>
                                            </div>

                                            <div>
                                                <span>65세 이상 인구 합계</span>
                                                <strong>
                                                    {formatNumber(
                                                        totalSeniorPopulation,
                                                    )}명
                                                </strong>
                                            </div>

                                            <div>
                                                <span>시설 기록 합계</span>
                                                <strong>
                                                    {formatNumber(
                                                        totalFacilities,
                                                    )}건
                                                </strong>
                                            </div>

                                            <div>
                                                <span>고령인구 최다 지역</span>
                                                <strong>
                                                    {mostSeniorDistrict
                                                        ? `${mostSeniorDistrict.district} · ${formatNumber(mostSeniorDistrict.population_65_plus)}명`
                                                        : '자료 없음'}
                                                </strong>
                                            </div>

                                            <div>
                                                <span>시설 기록 최다 지역</span>
                                                <strong>
                                                    {mostFacilitiesDistrict
                                                        ? `${mostFacilitiesDistrict.district} · ${mostFacilitiesDistrict.facilities}건`
                                                        : '자료 없음'}
                                                </strong>
                                            </div>

                                            <div>
                                                <span>시설 기록 최소 지역</span>
                                                <strong>
                                                    {fewestFacilitiesDistrict
                                                        ? `${fewestFacilitiesDistrict.district} · ${fewestFacilitiesDistrict.facilities}건`
                                                        : '자료 없음'}
                                                </strong>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="analysis-monthly-right">
                                        <h3>
                                            <ScatterIcon size={15} />
                                            분석 결과
                                        </h3>

                                        <p>
                                            Pearson 상관계수는{' '}
                                            <strong>
                                                {pearson === null
                                                    ? '계산 불가'
                                                    : pearson.toFixed(3)}
                                            </strong>
                                            {pearson === null
                                                ? '입니다.'
                                                : `으로, ${describeCorrelation(pearson)}입니다.`}
                                        </p>

                                        <p>
                                            분석 대상에서는 고령인구 수가 많은
                                            지역에 수거시설 기록이 반드시 더
                                            많이 분포하는 것은 아닙니다.
                                        </p>

                                        <h3>
                                            <Info size={15} />
                                            Pearson 상관계수란?
                                        </h3>

                                        <p>
                                            두 변수 사이의 선형 관계를
                                            -1부터 +1까지의 숫자로 표현한 지표입니다.
                                            음수는 한 변수가 커질 때 다른 변수가
                                            작아지는 경향을 의미하고,
                                            0에 가까울수록 선형 관계가 약합니다.
                                        </p>

                                        <h3>
                                            <AlertCircle size={15} />
                                            데이터 유의사항
                                        </h3>

                                        <p>
                                            상관관계는 인과관계를 의미하지 않으며,
                                            분석 대상이 9개 자치구이므로
                                            결과를 일반화할 때 주의해야 합니다.
                                        </p>

                                        <p>
                                            고령인구는 2026년 2분기 기준이지만
                                            시설 자료 기준일은 자치구마다 다릅니다.
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="analysis-monthly-actions">
                            <button
                                type="button"
                                onClick={closeDetail}
                            >
                                확인
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </section>
    );
}
