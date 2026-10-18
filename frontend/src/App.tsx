
import { useEffect, useMemo, useState } from 'react';

import {
  AlertCircle,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  Database,
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
import { loadMedicineData } from './services/dataService';

import type {
  Facility,
  MedicineData,
} from './types/medicine';

import './App.css';

const ALL = '전체';

function formatDate(value: string | null): string {
  return value ? value.slice(0, 10) : '미확인';
}

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
        {facility.road_address || '주소 정보 없음'}
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
        {facility.road_address || '주소 정보 없음'}
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

function App() {
  const [data, setData] =
    useState<MedicineData | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] =
    useState<string | null>(null);

  const [district, setDistrict] = useState(ALL);
  const [query, setQuery] = useState('');

  const [selectedId, setSelectedId] =
    useState<number | null>(null);

  const [showDataInfo, setShowDataInfo] =
    useState(false);

  useEffect(() => {
    let cancelled = false;

    loadMedicineData()
      .then((result) => {
        if (cancelled) return;

        setData(result);
        setError(null);
        setLoading(false);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;

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

  const filteredFacilities = useMemo(() => {
    if (!data) return [];

    const keyword = query.trim().toLowerCase();

    return data.facilities.filter((facility) => {
      const matchesDistrict =
        district === ALL ||
        facility.district === district;

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
        searchableText.includes(keyword)
      );
    });
  }, [data, district, query]);

  const selectedFacility = useMemo(() => {
    if (!data || selectedId === null) {
      return null;
    }

    return (
      data.facilities.find(
        (facility) => facility.id === selectedId,
      ) ?? null
    );
  }, [data, selectedId]);

  const mapFacilities = useMemo(
    () =>
      filteredFacilities.filter(
        (facility) => facility.map_marker_available,
      ),
    [filteredFacilities],
  );

  function changeDistrict(value: string) {
    setDistrict(value);
    setSelectedId(null);
  }

  function selectFacility(facility: Facility) {
    setSelectedId(facility.id);
  }

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
      <header className="compact-header">
        <div className="compact-header-inner">
          <a href="#top" className="compact-brand">
            <span className="brand-icon">
              <Pill size={18} />
            </span>
            <span>폐의약품 수거시설 안내</span>
          </a>

          <nav className="compact-nav">
            <a href="#finder">시설 찾기</a>
            <a href="#analysis">지역 통계</a>
          </nav>
        </div>
      </header>

      <main className="compact-main" id="top">
        <div className="dashboard-heading">
          <div>
            <h1>우리 동네 폐의약품 수거시설</h1>
            <p>
              서울시 9개 자치구 공공데이터 기반
              수거시설 위치 및 지역별 분포 분석
            </p>
          </div>

          <span className="coverage-label">
            <MapPin size={14} />
            서울시 9개 구
          </span>
        </div>

        <SummaryCards
          metadata={data.metadata}
          districts={data.districts}
          spatial={data.spatial}
        />

        <section id="finder" className="main-finder">
          <div className="section-title-row">
            <h2>수거시설 찾기</h2>

            <span className="result-indicator">
              검색 {filteredFacilities.length}건

              <span className="result-divider">
                ·
              </span>

              지도 {mapFacilities.length}건
            </span>
          </div>

          <div className="compact-filters">
            <label className="compact-search">
              <Search size={17} />

              <input
                type="search"
                placeholder="시설명 또는 주소 검색"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setSelectedId(null);
                }}
              />

              {query && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('');
                    setSelectedId(null);
                  }}
                  aria-label="검색어 지우기"
                >
                  <X size={15} />
                </button>
              )}
            </label>

            <label className="compact-select">
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
                    <option
                      key={item}
                      value={item}
                    >
                      {item}
                    </option>
                  ),
                )}
              </select>

              <ChevronDown size={16} />
            </label>
          </div>

          <div className="compact-finder-grid">
            <div className="compact-list-panel">
              <div className="compact-panel-heading">
                <strong>수거시설 목록</strong>
                <span>
                  {filteredFacilities.length}건
                </span>
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

            <div className="compact-map-panel">
              <KakaoMap
                facilities={mapFacilities}
                selectedFacility={selectedFacility}
                onSelectFacility={selectFacility}
              />

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

        <AnalysisDashboard
          districts={data.districts}
          monthly={data.monthly}
          spatial={data.spatial}
          selectedDistrict={district}
          onDistrictChange={changeDistrict}
        />


        <section className="compact-data-info">
          <button
            type="button"
            className="data-info-toggle"
            onClick={() =>
              setShowDataInfo((previous) => !previous)
            }
            aria-expanded={showDataInfo}
          >
            <span>
              <Database size={16} />
              데이터 출처 및 분석 유의사항
            </span>

            <ChevronRight
              size={17}
              className={showDataInfo ? 'rotated' : ''}
            />
          </button>

          {showDataInfo && (
            <div className="data-info-content">
              <p>
                <strong>분석 자료: </strong>
                자치구별 폐의약품 수거시설 공공데이터,
                서울시 주민등록인구,
                길단위 유동인구,
                폐의약품 수거 처리량
              </p>

              <ul>
                {data.metadata.limitations.map(
                  (limitation) => (
                    <li key={limitation}>
                      {limitation}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}
        </section>
      </main>

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
