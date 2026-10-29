
import { useEffect, useMemo, useState } from 'react';

import {
  AlertCircle,
  ArrowUpRight,
  ChevronDown,
  Download,
  ExternalLink,
  Info,
  MapPin,
  Navigation,
  Pill,
  Search,
  X,
} from 'lucide-react';

import KakaoMap from './components/KakaoMap';
import SummaryCards from './components/SummaryCards';
import AnalysisDashboard from './components/AnalysisDashboard';
import DataInformation from './components/DataInformation';

import { loadMedicineData } from './services/dataService';
import { exportFacilityCsv } from './services/exportCsv';

import type {
  Facility,
  MedicineData,
} from './types/medicine';

import './App.css';

const ALL = '전체';

type DateFilter =
  | 'all'
  | 'since2025'
  | 'before2025';

function matchesDate(
  date: string | null,
  mode: DateFilter,
): boolean {
  if (mode === 'all') {
    return true;
  }

  if (!date) {
    return false;
  }

  const normalized = date.slice(0, 10);

  if (mode === 'since2025') {
    return normalized >= '2025-01-01';
  }

  return normalized < '2025-01-01';
}

function formatDate(value: string | null): string {
  return value ? value.slice(0, 10) : '미확인';
}

/* =========================================
   수거시설 목록 아이템
========================================= */

function FacilityListItem({
  facility,
  active,
  onClick,
}: {
  facility: Facility;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`compact-facility ${active ? 'active' : ''}`}
      onClick={onClick}
    >
      <div className="compact-facility-main">
        <strong>{facility.name}</strong>

        <span className="small-district-tag">
          {facility.district}
        </span>
      </div>

      <span className="compact-address">
        {facility.road_address ||
          facility.lot_address ||
          '주소 정보 없음'}
      </span>

      <div className="compact-facility-meta">
        <span>
          기준 {formatDate(facility.reference_date)}
        </span>

        {!facility.map_marker_available && (
          <span className="coordinate-warning">
            좌표 없음
          </span>
        )}
      </div>
    </button>
  );
}

/* =========================================
   수거시설 상세 정보
========================================= */

function CompactFacilityDetail({
  facility,
  onClose,
}: {
  facility: Facility;
  onClose: () => void;
}) {
  const directionsUrl =
    facility.latitude != null &&
    facility.longitude != null
      ? `https://map.kakao.com/link/to/${encodeURIComponent(
          facility.name,
        )},${facility.latitude},${facility.longitude}`
      : null;

  return (
    <div className="compact-detail">
      <div className="compact-detail-header">
        <div>
          <span className="detail-eyebrow">
            선택한 수거시설 · {facility.district}
          </span>

          <h3>{facility.name}</h3>
        </div>

        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="상세 정보 닫기"
        >
          <X size={17} />
        </button>
      </div>

      <p className="detail-address">
        {facility.road_address ||
          facility.lot_address ||
          '주소 정보 없음'}
      </p>

      <div className="detail-meta-row">
        <span>
          자료 기준 {formatDate(facility.reference_date)}
        </span>

        <span>
          {facility.map_marker_available
            ? '좌표 확보'
            : '좌표 없음'}
        </span>
      </div>

      {facility.district === '양천구' && (
        <p className="nearest-info">
          <Info size={13} />
          2020년 공개 자료의 주소를 기반으로 좌표 보완
        </p>
      )}

      {facility.nearest_name &&
        facility.nearest_distance_m != null && (
          <p className="nearest-info">
            <Navigation size={13} />
            가까운 수록 시설: {facility.nearest_name}
            {' · '}직선거리{' '}
            {Math.round(facility.nearest_distance_m)}m
          </p>
        )}

      <div className="detail-footer">
        <span>
          <AlertCircle size={13} />
          운영 여부 미확인
        </span>

        {directionsUrl && (
          <a
            href={directionsUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            길찾기
            <ArrowUpRight size={14} />
          </a>
        )}
      </div>
    </div>
  );
}

/* =========================================
   메인 앱
========================================= */

function App() {
  const [data, setData] =
    useState<MedicineData | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] =
    useState<string | null>(null);

  const [district, setDistrict] = useState(ALL);
  const [query, setQuery] = useState('');

  const [dateFilter, setDateFilter] =
    useState<DateFilter>('all');

  const [sameLocation, setSameLocation] =
    useState<Facility[]>([]);

  const [selectedId, setSelectedId] =
    useState<number | null>(null);

  /* =====================================
     데이터 불러오기
  ===================================== */

  useEffect(() => {
    let cancelled = false;

    loadMedicineData()
      .then((result) => {
        if (cancelled) {
          return;
        }

        setData(result);
        setError(null);
        setLoading(false);
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }

        setError(
          caught instanceof Error
            ? caught.message
            : '데이터를 불러오지 못했습니다.',
        );

        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  /* =====================================
     시설 검색 및 필터
  ===================================== */

  const filteredFacilities = useMemo(() => {
    if (!data) {
      return [];
    }

    const keyword = query.trim().toLowerCase();

    return data.facilities.filter((facility) => {
      const matchesDistrict =
        district === ALL ||
        facility.district === district;

      const matchesPeriod = matchesDate(
        facility.reference_date,
        dateFilter,
      );

      const searchableText = [
        facility.name,
        facility.district,
        facility.road_address || '',
        facility.lot_address || '',
      ]
        .join(' ')
        .toLowerCase();

      return (
        matchesDistrict &&
        matchesPeriod &&
        searchableText.includes(keyword)
      );
    });
  }, [data, district, query, dateFilter]);

  /* =====================================
     선택 시설
  ===================================== */

  const selectedFacility = useMemo(() => {
    if (!data || selectedId === null) {
      return null;
    }

    return (
      filteredFacilities.find(
        (facility) => facility.id === selectedId,
      ) ?? null
    );
  }, [data, filteredFacilities, selectedId]);

  /* =====================================
     지도 표시 대상
  ===================================== */

  const mapFacilities = useMemo(
    () =>
      filteredFacilities.filter(
        (facility) => facility.map_marker_available,
      ),
    [filteredFacilities],
  );

  /* =====================================
     이벤트 함수
  ===================================== */

  function changeDistrict(value: string) {
    setDistrict(value);
    setSelectedId(null);
    setSameLocation([]);
  }

  function changeQuery(value: string) {
    setQuery(value);
    setSelectedId(null);
    setSameLocation([]);
  }

  function changeDateFilter(value: DateFilter) {
    setDateFilter(value);
    setSelectedId(null);
    setSameLocation([]);
  }

  function selectFacility(facility: Facility) {
    setSelectedId(facility.id);
    setSameLocation([]);
  }

  function selectMapLocation(
    facilitiesAtLocation: Facility[],
  ) {
    if (facilitiesAtLocation.length === 0) {
      return;
    }

    if (facilitiesAtLocation.length === 1) {
      selectFacility(facilitiesAtLocation[0]);
      return;
    }

    setSelectedId(null);
    setSameLocation(facilitiesAtLocation);
  }

  function handleChartDistrictChange(value: string) {
    changeDistrict(value);

    document
      .getElementById('finder')
      ?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
  }

  /* =====================================
     로딩 및 오류
  ===================================== */

  if (loading) {
    return (
      <div className="status-page">
        <Pill size={32} />
        <h2>데이터를 불러오는 중입니다</h2>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="status-page">
        <AlertCircle size={32} />
        <h2>데이터를 불러오지 못했습니다</h2>
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="app-shell">
      {/* =====================================
          헤더
      ===================================== */}

      <header className="compact-header">
        <div className="compact-header-inner">
          <a href="#top" className="compact-brand">
            <span className="brand-icon">
              <Pill size={18} />
            </span>

            <span>폐의약품 수거시설 안내</span>
          </a>

          <nav
            className="compact-nav"
            aria-label="주요 메뉴"
          >
            <a href="#finder">시설 찾기</a>
            <a href="#analysis">지역 통계</a>
          </nav>

          <span
            className="coverage-label header-coverage"
            aria-label="분석 대상 지역"
          >
            <MapPin size={14} />
            서울시 {data.metadata.coverage.districts.length}개 구
          </span>
        </div>
      </header>

      <main className="compact-main" id="top">
        {/* =====================================
            상단 통계
        ===================================== */}

        <SummaryCards
          metadata={data.metadata}
          districts={data.districts}
          spatial={data.spatial}
        />

        {/* =====================================
            수거시설 찾기
        ===================================== */}

        <section id="finder" className="main-finder">
          <div className="section-title-row">
            <h2>수거시설 찾기</h2>

            <span className="result-indicator">
              검색 {filteredFacilities.length}건
              <span className="result-divider">·</span>
              지도 {mapFacilities.length}건
            </span>
          </div>

          {/* =====================================
              통합 검색 및 필터 영역
          ===================================== */}

          <div className="facility-toolbar">
            {/* 시설명 및 주소 검색 */}

            <label className="compact-search facility-search">
              <Search size={17} />

              <input
                type="search"
                placeholder="시설명 또는 주소 검색"
                value={query}
                onChange={(event) =>
                  changeQuery(event.target.value)
                }
              />

              {query && (
                <button
                  type="button"
                  aria-label="검색어 지우기"
                  onClick={() => changeQuery('')}
                >
                  <X size={15} />
                </button>
              )}
            </label>

            {/* 자치구 선택 */}

            <label className="compact-select facility-district">
              <select
                value={district}
                onChange={(event) =>
                  changeDistrict(event.target.value)
                }
                aria-label="자치구 선택"
              >
                <option value={ALL}>
                  전체 자치구
                </option>

                {data.metadata.coverage.districts.map(
                  (item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ),
                )}
              </select>

              <ChevronDown size={16} />
            </label>

            {/* 자료 기준일 선택 */}

            <label className="compact-select facility-date">
              <span className="facility-date-label">
                자료 기준일
              </span>

              <select
                value={dateFilter}
                onChange={(event) => {
                  const value = event.currentTarget.value;

                  if (
                    value === 'all' ||
                    value === 'since2025' ||
                    value === 'before2025'
                  ) {
                    changeDateFilter(value);
                  }
                }}
                aria-label="자료 기준일"
              >
                <option value="all">
                  전체 기록
                </option>

                <option value="since2025">
                  2025년 이후
                </option>

                <option value="before2025">
                  2025년 이전
                </option>
              </select>

              <ChevronDown size={16} />
            </label>

            {/* 현재 필터에 맞는 CSV 다운로드 */}

            <button
              type="button"
              className="facility-csv-button"
              disabled={filteredFacilities.length === 0}
              onClick={() =>
                exportFacilityCsv(
                  filteredFacilities,
                  'medicine_facilities_filtered.csv',
                )
              }
            >
              <Download size={15} />
              <span>현재 검색 결과 CSV</span>
            </button>
          </div>

          {/* =====================================
              시설 목록과 지도
          ===================================== */}

          <div className="compact-finder-grid">
            {/* 시설 목록 */}

            <div className="compact-list-panel">
              <div className="compact-panel-heading">
                <strong>수거시설 목록</strong>
                <span>{filteredFacilities.length}건</span>
              </div>

              <div className="compact-list-scroll">
                {filteredFacilities.length > 0 ? (
                  filteredFacilities.map((facility) => (
                    <FacilityListItem
                      key={facility.id}
                      facility={facility}
                      active={selectedId === facility.id}
                      onClick={() =>
                        selectFacility(facility)
                      }
                    />
                  ))
                ) : (
                  <div className="empty-results">
                    검색 결과가 없습니다.
                  </div>
                )}
              </div>
            </div>

            {/* 지도 */}

            <div className="compact-map-panel">
              <KakaoMap
                facilities={mapFacilities}
                selectedFacility={selectedFacility}
                onSelectFacility={selectFacility}
                onSelectLocation={selectMapLocation}
              />

              {/* 동일 좌표 시설 선택 */}

              {sameLocation.length > 1 && (
                <div className="shared-coordinate-panel">
                  <div className="shared-coordinate-heading">
                    <strong>
                      같은 좌표의 시설 {sameLocation.length}건
                    </strong>

                    <button
                      type="button"
                      onClick={() => setSameLocation([])}
                      aria-label="닫기"
                    >
                      <X size={16} />
                    </button>
                  </div>

                  <p>
                    서로 다른 시설 기록이 같은 좌표를
                    사용하고 있습니다. 시설명을 선택해
                    상세 정보를 확인하세요.
                  </p>

                  {sameLocation.map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      onClick={() =>
                        selectFacility(item)
                      }
                    >
                      {item.name} · {item.district}
                    </button>
                  ))}
                </div>
              )}

              {/* 선택 시설 상세 */}

              {selectedFacility && (
                <CompactFacilityDetail
                  facility={selectedFacility}
                  onClose={() =>
                    setSelectedId(null)
                  }
                />
              )}
            </div>
          </div>
        </section>

        {/* =====================================
            분석 차트
        ===================================== */}

        <AnalysisDashboard
          districts={data.districts}
          monthly={data.monthly}
          spatial={data.spatial}
          selectedDistrict={district}
          onDistrictChange={handleChartDistrictChange}
        />

        {/* =====================================
            데이터 안내
        ===================================== */}

        <DataInformation
          data={data}
          filteredFacilities={filteredFacilities}
        />
      </main>

      {/* =====================================
          푸터
      ===================================== */}

      <footer className="compact-footer">
        <span>
          폐의약품 수거시설 공공데이터 분석 프로젝트
        </span>

        <span>
          Python · pandas · React · Kakao Maps
          <ExternalLink size={12} />
        </span>
      </footer>
    </div>
  );
}

export default App;
