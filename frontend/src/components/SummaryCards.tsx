
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  AlertCircle,
  BarChart3,
  Database,
  Info,
  Lightbulb,
  MapPin,
  TrendingUp,
  Users,
  X,
} from 'lucide-react';

import type {
  District,
  MedicineData,
} from '../types/medicine';

import './SummaryCards.css';
import './SummaryCardsDetails.css';

type CardId =
  | 'facilities'
  | 'population'
  | 'seniors'
  | 'distance';

interface SummaryCardsProps {
  metadata: MedicineData['metadata'];
  districts: District[];
  spatial: MedicineData['spatial'];
}

interface DetailRow {
  label: string;
  value: string;
}

interface CardInfo {
  id: CardId;
  title: string;
  value: string;
  unit: string;
  shortDescription: string;
  description: string;
  rows: DetailRow[];
  findings: string[];
  interpretation: string;
  cautions: string[];
}

const formatter = new Intl.NumberFormat('ko-KR');

function formatInteger(value: number): string {
  return formatter.format(value);
}

function formatRate(value: number): string {
  return value.toFixed(3);
}

function calculateRate(
  facilities: number,
  population: number,
): number {
  if (population <= 0) return 0;
  return facilities / population * 10000;
}

function calculatePercent(
  value: number,
  total: number,
): number {
  if (total <= 0) return 0;
  return value / total * 100;
}

function getRanking(
  districts: District[],
  populationKey:
    | 'population_total'
    | 'population_65_plus',
) {
  return districts
    .filter((item) => item[populationKey] > 0)
    .map((item) => ({
      district: item.district,
      facilities: item.facility_records,
      population: item[populationKey],
      rate: calculateRate(
        item.facility_records,
        item[populationKey],
      ),
    }))
    .sort((a, b) => b.rate - a.rate);
}

function CardIcon({ id }: { id: CardId }) {
  switch (id) {
    case 'facilities':
      return <Database size={17} />;
    case 'population':
      return <BarChart3 size={17} />;
    case 'seniors':
      return <Users size={17} />;
    case 'distance':
      return <MapPin size={17} />;
  }
}

export default function SummaryCards({
  metadata,
  districts,
  spatial,
}: SummaryCardsProps) {
  const [activeId, setActiveId] =
    useState<CardId | null>(null);

  const closeButtonRef =
    useRef<HTMLButtonElement>(null);

  const previousFocusRef =
    useRef<HTMLElement | null>(null);

  const cards = useMemo<CardInfo[]>(() => {
    const facilityCount =
      metadata.records.facility_count;

    const mappedCount =
      metadata.records.map_marker_count;

    const missingCount =
      metadata.records.missing_coordinate_count;

    const districtCount =
      metadata.coverage.district_count;

    const totalPopulation = districts.reduce(
      (sum, item) => sum + item.population_total,
      0,
    );

    const seniorPopulation = districts.reduce(
      (sum, item) => sum + item.population_65_plus,
      0,
    );

    const totalFacilities = districts.reduce(
      (sum, item) => sum + item.facility_records,
      0,
    );

    const populationRate = calculateRate(
      totalFacilities,
      totalPopulation,
    );

    const seniorRate = calculateRate(
      totalFacilities,
      seniorPopulation,
    );

    const coordinateRate = calculatePercent(
      mappedCount,
      facilityCount,
    );

    const seniorShare = calculatePercent(
      seniorPopulation,
      totalPopulation,
    );

    const populationRanking = getRanking(
      districts,
      'population_total',
    );

    const seniorRanking = getRanking(
      districts,
      'population_65_plus',
    );

    const populationHighest = populationRanking[0];
    const populationLowest = populationRanking.at(-1);

    const seniorHighest = seniorRanking[0];
    const seniorLowest = seniorRanking.at(-1);

    const populationGap =
      populationHighest &&
      populationLowest &&
      populationLowest.rate > 0
        ? populationHighest.rate / populationLowest.rate
        : null;

    const seniorGap =
      seniorHighest &&
      seniorLowest &&
      seniorLowest.rate > 0
        ? seniorHighest.rate / seniorLowest.rate
        : null;

    const mostSeniorDistrict = [...districts].sort(
      (a, b) =>
        b.population_65_plus - a.population_65_plus,
    )[0];

    const mostSeniorRate = mostSeniorDistrict
      ? calculateRate(
          mostSeniorDistrict.facility_records,
          mostSeniorDistrict.population_65_plus,
        )
      : 0;

    const dataMatches =
      facilityCount === totalFacilities;

    const spatialRanking = [...spatial.districts].sort(
      (a, b) =>
        b.mean_nearest_m - a.mean_nearest_m,
    );

    const highestSpatialDistrict = spatialRanking[0];

    return [
      {
        id: 'facilities',
        title: '전체 수거시설 기록',
        value: formatInteger(facilityCount),
        unit: '건',

        shortDescription:
          '9개 자치구에서 확보한 수거시설 원본 기록 수',

        description:
          '서울시 일부 자치구에서 확보한 ' +
          '폐의약품 수거시설 위치 자료의 ' +
          '원본 기록 수입니다.',

        rows: [
          {
            label: '분석 대상 지역',
            value: `${districtCount}개 자치구`,
          },
          {
            label: '지도 표시 가능',
            value: `${formatInteger(mappedCount)}건`,
          },
          {
            label: '좌표 미제공',
            value: `${formatInteger(missingCount)}건`,
          },
          {
            label: '좌표 보유율',
            value: `${coordinateRate.toFixed(1)}%`,
          },
        ],

        findings: [
          `전체 ${formatInteger(facilityCount)}건 중 ${formatInteger(mappedCount)}건에 지도 표시 가능한 좌표가 확보됐습니다.`,
          '양천구 6건은 기존 주소를 지오코딩하여 좌표를 보완했습니다.',
          '동일 좌표 기록과 시설 자료 기준일의 차이가 확인됐습니다.',
        ],

        interpretation:
          '분석 대상 시설 기록을 지도에 표시할 수 있게 되었지만, ' +
          '좌표 확보가 시설의 현재 운영을 확인한 것은 아닙니다.',

        cautions: [
          '서울시 전체 25개 구가 아닌 자료를 확보한 9개 구만 분석했습니다.',
          '시설 기록 수는 현재 운영 중인 수거시설 수와 다를 수 있습니다.',
          '양천구 6건은 2020년 공개 자료의 주소로 좌표를 보완했습니다.',
          ...(dataMatches
            ? []
            : [
                '메타데이터의 시설 수와 자치구별 합계가 일치하지 않습니다.',
              ]),
        ],
      },

      {
        id: 'population',
        title: '인구 1만 명당 시설',
        value: formatRate(populationRate),
        unit: '건',

        shortDescription:
          '주민등록인구 대비 시설 기록 비율',

        description:
          '9개 자치구의 시설 기록 수를 주민등록 총인구 ' +
          '합계로 나누어 계산한 지표입니다.',

        rows: [
          {
            label: '전체 주민등록인구',
            value: `${formatInteger(totalPopulation)}명`,
          },
          {
            label: '시설 기록 합계',
            value: `${formatInteger(totalFacilities)}건`,
          },
          {
            label: '인구 대비 최고 구',
            value: populationHighest
              ? `${populationHighest.district} (${formatRate(populationHighest.rate)}건)`
              : '자료 없음',
          },
          {
            label: '인구 대비 최저 구',
            value: populationLowest
              ? `${populationLowest.district} (${formatRate(populationLowest.rate)}건)`
              : '자료 없음',
          },
          {
            label: '최고 / 최저 비율',
            value: populationGap !== null
              ? `약 ${populationGap.toFixed(1)}배`
              : '계산 불가',
          },
        ],

        findings: [
          populationHighest && populationLowest
            ? `${populationHighest.district}는 인구 1만 명당 ${formatRate(populationHighest.rate)}건, ${populationLowest.district}는 ${formatRate(populationLowest.rate)}건입니다.`
            : '지역별 비율을 계산할 자료가 부족합니다.',

          populationGap !== null
            ? `분석 대상 중 최고·최저 비율은 약 ${populationGap.toFixed(1)}배 차이가 납니다.`
            : '지역 간 격차 비율을 계산할 수 없습니다.',
        ],

        interpretation:
          '단순 시설 기록 수뿐 아니라 지역별 인구 규모를 고려하면 ' +
          '시설 분포의 차이를 확인할 수 있습니다.',

        cautions: [
          '계산식: 시설 기록 수 ÷ 주민등록 총인구 × 10,000',
          '인구는 2026년 2분기 기준이지만 시설 자료 기준일은 서로 다릅니다.',
          '특히 양천구 자료는 2020년 기준이므로 현재 지역 간 격차로 단정할 수 없습니다.',
          '인구 대비 시설 기록 수는 주민 이동 편의성을 직접 의미하지 않습니다.',
        ],
      },

      {
        id: 'seniors',
        title: '고령인구 1만 명당 시설',
        value: formatRate(seniorRate),
        unit: '건',

        shortDescription:
          '65세 이상 주민등록인구 대비 시설 기록 비율',

        description:
          '9개 자치구의 시설 기록 수를 65세 이상 주민등록인구 ' +
          '합계로 나누어 계산한 지표입니다.',

        rows: [
          {
            label: '65세 이상 총인구',
            value: `${formatInteger(seniorPopulation)}명`,
          },
          {
            label: '전체 인구 중 고령인구',
            value: `${seniorShare.toFixed(1)}%`,
          },
          {
            label: '고령인구 대비 최고 구',
            value: seniorHighest
              ? `${seniorHighest.district} (${formatRate(seniorHighest.rate)}건)`
              : '자료 없음',
          },
          {
            label: '고령인구 대비 최저 구',
            value: seniorLowest
              ? `${seniorLowest.district} (${formatRate(seniorLowest.rate)}건)`
              : '자료 없음',
          },
          {
            label: '최고 / 최저 비율',
            value: seniorGap !== null
              ? `약 ${seniorGap.toFixed(1)}배`
              : '계산 불가',
          },
        ],

        findings: [
          mostSeniorDistrict
            ? `${mostSeniorDistrict.district}는 65세 이상 인구가 ${formatInteger(mostSeniorDistrict.population_65_plus)}명으로 9개 구 중 가장 많지만, 고령인구 1만 명당 시설 기록은 ${formatRate(mostSeniorRate)}건입니다.`
            : '고령인구 데이터가 부족합니다.',

          seniorHighest
            ? `${seniorHighest.district}는 고령인구 1만 명당 시설 기록 수가 ${formatRate(seniorHighest.rate)}건으로 가장 높습니다.`
            : '지역별 최고 비율을 확인할 수 없습니다.',

          seniorGap !== null
            ? `고령인구 대비 최고·최저 비율은 약 ${seniorGap.toFixed(1)}배 차이를 보입니다.`
            : '지역 간 격차를 계산할 수 없습니다.',
        ],

        interpretation:
          '고령인구 규모가 큰 지역에 시설 기록이 반드시 같은 ' +
          '비율로 분포하지는 않습니다. 고령인구 규모를 고려한 ' +
          '시설 배치 수준을 추가로 검토할 필요가 있습니다.',

        cautions: [
          '계산식: 시설 기록 수 ÷ 65세 이상 주민등록인구 × 10,000',
          '고령층의 실제 이동거리나 교통 이용 여건은 반영하지 않습니다.',
          '시설 자료 기준일이 다르고 양천구 자료가 오래돼 현재 상황으로 일반화할 수 없습니다.',
        ],
      },

      {
        id: 'distance',
        title: '평균 최근접 시설 거리',
        value: formatInteger(
          Math.round(spatial.mean_nearest_m),
        ),
        unit: 'm',

        shortDescription:
          '가장 가까운 다른 수록 시설까지의 평균 직선거리',

        description:
          '9개 자치구의 좌표 보유 시설에서 가장 가까운 ' +
          '다른 수록 시설까지의 직선거리를 계산한 결과입니다.',

        rows: [
          {
            label: '공간 분석 시설 기록',
            value: `${spatial.total_records}건`,
          },
          {
            label: '공간 분석 자치구',
            value: `${spatial.district_count}개 구`,
          },
          {
            label: '최근접 거리 중앙값',
            value: `${Math.round(spatial.median_nearest_m)}m`,
          },
          {
            label: '최근접 거리 최대값',
            value: `${spatial.max_nearest_km.toFixed(3)}km`,
          },
          {
            label: '다른 좌표의 최근접 시설 1km 이상',
            value: `${spatial.distinct_nearest_over_1km_records}건`,
          },
          {
            label: '자치구별 평균이 가장 긴 구',
            value: highestSpatialDistrict
              ? `${highestSpatialDistrict.district} (${Math.round(highestSpatialDistrict.mean_nearest_m)}m)`
              : '자료 없음',
          },
        ],

        findings: [
          `좌표가 있는 ${spatial.total_records}건의 평균 최근접 다른 시설 기록까지의 직선거리는 약 ${Math.round(spatial.mean_nearest_m)}m입니다.`,

          highestSpatialDistrict
            ? `${highestSpatialDistrict.district}는 분석한 ${spatial.district_count}개 구 중 평균 최근접 직선거리가 가장 길게 나타났습니다.`
            : '지역별 공간 분석 자료가 없습니다.',

          `서로 다른 좌표의 최근접 시설까지 거리가 1km 이상인 기록은 ${spatial.distinct_nearest_over_1km_records}건입니다.`,
        ],

        interpretation:
          '시설 간 간격에 지역별 차이가 나타나지만, ' +
          '이 수치는 주민의 실제 이동거리나 접근성을 ' +
          '직접 측정한 결과는 아닙니다.',

        cautions: [
          '직선거리 기준이며 도보 또는 차량 이동거리가 아닙니다.',
          '동일 좌표에 있는 다른 기록의 최근접 거리는 0m일 수 있습니다.',
          '양천구 6건은 2020년 주소 기반으로 좌표를 보완했습니다.',
          '시설의 실제 운영 여부와 좌표의 현장 정확성은 확인되지 않았습니다.',
        ],
      },
    ];
  }, [metadata, districts, spatial]);

  const activeCard =
    cards.find((card) => card.id === activeId) ?? null;

  function openCard(id: CardId) {
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    setActiveId(id);
  }

  function closeCard() {
    setActiveId(null);
  }

  useEffect(() => {
    if (!activeId) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setActiveId(null);
      }

      if (event.key !== 'Tab') return;

      const modal = document.querySelector('.summary-modal');

      if (!(modal instanceof HTMLElement)) return;

      const focusable = Array.from(
        modal.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      );

      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

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

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [activeId]);

  return (
    <>
      <div className="compact-summary">
        {cards.map((card) => (
          <div className="summary-card-wrap" key={card.id}>
            <button
              type="button"
              className="metric-card interactive-metric"
              onClick={() => openCard(card.id)}
              aria-haspopup="dialog"
              aria-label={`${card.title} ${card.value}${card.unit}, 자세히 보기`}
            >
              <span className="metric-card-top">
                <span>{card.title}</span>
                <Info size={14} />
              </span>

              <strong>
                {card.value}
                <small>{card.unit}</small>
              </strong>
            </button>

            <div className="metric-tooltip" role="tooltip">
              <span>{card.shortDescription}</span>
              <small>클릭하여 상세 분석 확인</small>
            </div>
          </div>
        ))}
      </div>

      {activeCard && (
        <div
          className="summary-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeCard();
            }
          }}
        >
          <div
            className="summary-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="summary-modal-title"
            aria-describedby="summary-modal-description"
          >
            <div className="summary-modal-header">
              <div className="summary-modal-heading">
                <span className="summary-modal-icon">
                  <CardIcon id={activeCard.id} />
                </span>

                <h2 id="summary-modal-title">
                  {activeCard.title}
                </h2>
              </div>

              <button
                type="button"
                ref={closeButtonRef}
                className="summary-modal-close"
                onClick={closeCard}
                aria-label="팝업 닫기"
              >
                <X size={19} />
              </button>
            </div>

            <div className="summary-modal-body">
              <div className="summary-modal-number">
                {activeCard.value}
                <small>{activeCard.unit}</small>
              </div>

              <p id="summary-modal-description">
                {activeCard.description}
              </p>

              {activeCard.id === 'facilities' && (
                <div className="summary-coverage">
                  <div className="summary-coverage-label">
                    <span>좌표 보유율</span>

                    <strong>
                      {calculatePercent(
                        metadata.records.map_marker_count,
                        metadata.records.facility_count,
                      ).toFixed(1)}
                      %
                    </strong>
                  </div>

                  <div className="summary-coverage-track">
                    <div
                      className="summary-coverage-fill"
                      style={{
                        width: `${calculatePercent(
                          metadata.records.map_marker_count,
                          metadata.records.facility_count,
                        )}%`,
                      }}
                    />
                  </div>
                </div>
              )}

              <div className="summary-detail-table">
                {activeCard.rows.map((row) => (
                  <div
                    className="summary-detail-row"
                    key={row.label}
                  >
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                  </div>
                ))}
              </div>

              <div className="summary-modal-divider" />

              <div className="summary-modal-notes">
                <div className="summary-insight-section">
                  <h3>
                    <TrendingUp size={16} />
                    주요 분석 결과
                  </h3>

                  <div className="summary-findings">
                    {activeCard.findings.map((finding) => (
                      <div
                        className="summary-finding"
                        key={finding}
                      >
                        <span className="finding-dot" />
                        <p>{finding}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="summary-insight-section">
                  <h3>
                    <Lightbulb size={16} />
                    결과 해석
                  </h3>

                  <p className="summary-interpretation">
                    {activeCard.interpretation}
                  </p>
                </div>

                <div className="summary-insight-section">
                  <h3>
                    <AlertCircle size={16} />
                    데이터 유의사항
                  </h3>

                  <div className="summary-cautions">
                    {activeCard.cautions.map((caution) => (
                      <div
                        className="summary-caution"
                        key={caution}
                      >
                        <Info size={13} />
                        <span>{caution}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="summary-modal-footer">
              <button
                type="button"
                onClick={closeCard}
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
