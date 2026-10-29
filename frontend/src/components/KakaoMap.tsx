
import { useEffect, useRef, useState } from 'react';

import {
  AlertCircle,
  MapPin,
  RotateCcw,
} from 'lucide-react';

import type { Facility } from '../types/medicine';

/* ==========================================
   1. Kakao Maps 타입 정의
========================================== */

interface KakaoLatLng {
  getLat(): number;
  getLng(): number;
}

interface KakaoBounds {
  extend(position: KakaoLatLng): void;
}

interface KakaoMapInstance {
  setCenter(position: KakaoLatLng): void;
  setBounds(bounds: KakaoBounds): void;
  setLevel(level: number): void;
  getLevel(): number;
  relayout(): void;
}

interface KakaoMarkerImage {}

interface KakaoMarker {
  setMap(map: KakaoMapInstance | null): void;
  setImage(image: KakaoMarkerImage): void;
}

interface KakaoClusterer {
  addMarkers(markers: KakaoMarker[]): void;
  clear(): void;
  setMap(map: KakaoMapInstance | null): void;
}

interface KakaoMaps {
  load(callback: () => void): void;

  LatLng: new (
    latitude: number,
    longitude: number,
  ) => KakaoLatLng;

  LatLngBounds: new () => KakaoBounds;

  Size: new (
    width: number,
    height: number,
  ) => object;

  MarkerImage: new (
    src: string,
    size: object,
  ) => KakaoMarkerImage;

  Map: new (
    container: HTMLElement,
    options: {
      center: KakaoLatLng;
      level: number;
    },
  ) => KakaoMapInstance;

  Marker: new (options: {
    map?: KakaoMapInstance;
    position: KakaoLatLng;
    title?: string;
    image?: KakaoMarkerImage;
    zIndex?: number;
  }) => KakaoMarker;

  MarkerClusterer: new (options: {
    map: KakaoMapInstance;
    averageCenter: boolean;
    minLevel: number;
    minClusterSize: number;
    gridSize: number;
    disableClickZoom: boolean;
    styles: Array<{
      width: string;
      height: string;
      background: string;
      borderRadius: string;
      color: string;
      textAlign: string;
      lineHeight: string;
      fontSize: string;
      fontWeight: string;
      boxShadow: string;
    }>;
  }) => KakaoClusterer;

  event: {
    addListener(
      target: KakaoMarker,
      event: string,
      callback: () => void,
    ): void;
  };
}

declare global {
  interface Window {
    kakao?: {
      maps: KakaoMaps;
    };
  }
}

/* ==========================================
   2. Kakao Maps SDK 로딩
========================================== */

let sdkPromise: Promise<KakaoMaps> | null = null;

function loadKakaoMaps(
  key: string,
): Promise<KakaoMaps> {
  if (sdkPromise) {
    return sdkPromise;
  }

  const promise = new Promise<KakaoMaps>(
    (resolve, reject) => {
      const initialize = (maps: KakaoMaps) => {
        maps.load(() => {
          if (
            typeof maps.MarkerClusterer !== 'function'
          ) {
            reject(
              new Error(
                '클러스터링 라이브러리가 로드되지 않았습니다. ' +
                  '카카오맵 SDK 중복 로드를 확인해 주세요.',
              ),
            );

            return;
          }

          resolve(maps);
        });
      };

      // 클러스터링 SDK까지 로드된 경우
      if (
        window.kakao?.maps &&
        typeof window.kakao.maps.MarkerClusterer ===
          'function'
      ) {
        initialize(window.kakao.maps);
        return;
      }

      // 일반 지도 SDK만 먼저 로드된 경우
      if (window.kakao?.maps) {
        reject(
          new Error(
            '기존 카카오맵 SDK에 clusterer 라이브러리가 없습니다. ' +
              '브라우저 전체 새로고침이 필요합니다.',
          ),
        );

        return;
      }

      const script = document.createElement('script');

      script.src =
        'https://dapi.kakao.com/v2/maps/sdk.js' +
        `?appkey=${encodeURIComponent(key)}` +
        '&autoload=false&libraries=clusterer';

      script.async = true;

      script.onload = () => {
        const maps = window.kakao?.maps;

        if (!maps) {
          reject(
            new Error(
              '카카오맵 SDK 객체를 찾지 못했습니다.',
            ),
          );

          return;
        }

        initialize(maps);
      };

      script.onerror = () => {
        script.remove();

        reject(
          new Error(
            '카카오맵 SDK 네트워크 요청에 실패했습니다.',
          ),
        );
      };

      document.head.appendChild(script);
    },
  );

  sdkPromise = promise.catch(
    (error: unknown) => {
      sdkPromise = null;
      throw error;
    },
  );

  return sdkPromise;
}

/* ==========================================
   3. 지도 마커 이미지
========================================== */

function createMarkerImage(
  maps: KakaoMaps,
  selected: boolean,
): KakaoMarkerImage {
  const color = selected
    ? '#ef4444'
    : '#4f67d9';

  const size = selected ? 42 : 32;

  const svg = `
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="${size}"
      height="${size + 8}"
      viewBox="0 0 42 50"
    >
      <path
        d="M21 2 C11 2 4 10 4 20
           C4 34 21 47 21 47
           C21 47 38 34 38 20
           C38 10 31 2 21 2Z"
        fill="${color}"
        stroke="#ffffff"
        stroke-width="2.5"
      />
      <circle
        cx="21"
        cy="20"
        r="7"
        fill="#ffffff"
      />
    </svg>
  `;

  const imageUrl =
    'data:image/svg+xml;charset=UTF-8,' +
    encodeURIComponent(svg);

  return new maps.MarkerImage(
    imageUrl,
    new maps.Size(size, size + 8),
  );
}

/* ==========================================
   4. 동일 좌표 시설 그룹화
========================================== */

function groupFacilitiesByLocation(
  facilities: Facility[],
): Facility[][] {
  const grouped = new Map<string, Facility[]>();

  facilities.forEach((facility) => {
    const latitude = facility.latitude;
    const longitude = facility.longitude;

    if (
      latitude == null ||
      longitude == null ||
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude)
    ) {
      return;
    }

    // 동일한 좌표를 사용하는 시설끼리 묶기
    const coordinateKey = [
      latitude.toFixed(7),
      longitude.toFixed(7),
    ].join(',');

    const existing =
      grouped.get(coordinateKey) ?? [];

    existing.push(facility);

    grouped.set(
      coordinateKey,
      existing,
    );
  });

  return [...grouped.values()];
}

/* ==========================================
   5. 컴포넌트 Props
========================================== */

interface KakaoMapProps {
  facilities: Facility[];

  selectedFacility: Facility | null;

  onSelectFacility: (
    facility: Facility,
  ) => void;

  onSelectLocation?: (
    facilities: Facility[],
  ) => void;
}

/* ==========================================
   6. 메인 컴포넌트
========================================== */

function KakaoMap({
  facilities,
  selectedFacility,
  onSelectFacility,
  onSelectLocation,
}: KakaoMapProps) {
  const containerRef =
    useRef<HTMLDivElement>(null);

  const mapRef =
    useRef<KakaoMapInstance | null>(null);

  const sdkRef =
    useRef<KakaoMaps | null>(null);

  const clustererRef =
    useRef<KakaoClusterer | null>(null);

  const markerRef =
    useRef<KakaoMarker[]>([]);

  const selectedMarkerRef =
    useRef<KakaoMarker | null>(null);

  const callbackRef =
    useRef(onSelectFacility);

  const locationCallbackRef =
    useRef(onSelectLocation);

  const facilitiesRef =
    useRef(facilities);

  const [ready, setReady] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const key = import.meta.env
    .VITE_KAKAO_MAP_KEY as
    | string
    | undefined;

  /* ======================================
     7. 지도에 표시 가능한 시설 필터링
  ====================================== */

  const validFacilities =
    facilities.filter(
      (facility) =>
        facility.map_marker_available &&
        facility.latitude != null &&
        facility.longitude != null &&
        Number.isFinite(
          facility.latitude,
        ) &&
        Number.isFinite(
          facility.longitude,
        ),
    );

  /* ======================================
     8. 최신 콜백 및 시설 목록 유지
  ====================================== */

  useEffect(() => {
    callbackRef.current =
      onSelectFacility;

    locationCallbackRef.current =
      onSelectLocation;

    facilitiesRef.current =
      facilities;
  }, [
    onSelectFacility,
    onSelectLocation,
    facilities,
  ]);

  /* ======================================
     9. 마커 제거
  ====================================== */

  function clearMarkers() {
    clustererRef.current?.clear();

    markerRef.current.forEach(
      (marker) => {
        marker.setMap(null);
      },
    );

    markerRef.current = [];
  }

  /* ======================================
     10. 현재 검색 결과 전체 보기
  ====================================== */

  function fitMapToFacilities() {
    const map = mapRef.current;
    const maps = sdkRef.current;

    if (!map || !maps) {
      return;
    }

    const valid =
      facilitiesRef.current.filter(
        (facility) =>
          facility.map_marker_available &&
          facility.latitude != null &&
          facility.longitude != null &&
          Number.isFinite(
            facility.latitude,
          ) &&
          Number.isFinite(
            facility.longitude,
          ),
      );

    map.relayout();

    if (valid.length === 0) {
      map.setCenter(
        new maps.LatLng(
          37.5665,
          126.978,
        ),
      );

      map.setLevel(8);
      return;
    }

    if (valid.length === 1) {
      const facility = valid[0];

      map.setCenter(
        new maps.LatLng(
          facility.latitude!,
          facility.longitude!,
        ),
      );

      map.setLevel(4);
      return;
    }

    const bounds =
      new maps.LatLngBounds();

    valid.forEach((facility) => {
      bounds.extend(
        new maps.LatLng(
          facility.latitude!,
          facility.longitude!,
        ),
      );
    });

    map.setBounds(bounds);
  }

  /* ======================================
     11. 최초 지도 생성
  ====================================== */

  useEffect(() => {
    if (!key) {
      setError(
        '카카오맵 JavaScript 키가 없습니다.',
      );

      return;
    }

    let disposed = false;

    loadKakaoMaps(key)
      .then((maps) => {
        if (
          disposed ||
          !containerRef.current
        ) {
          return;
        }

        const map = new maps.Map(
          containerRef.current,
          {
            center: new maps.LatLng(
              37.5665,
              126.978,
            ),
            level: 8,
          },
        );

        const clusterer =
          new maps.MarkerClusterer({
            map,
            averageCenter: true,
            minLevel: 5,
            minClusterSize: 2,
            gridSize: 65,
            disableClickZoom: false,

            styles: [
              {
                width: '44px',
                height: '44px',
                background:
                  'rgba(79,103,217,0.88)',
                borderRadius: '50%',
                color: '#ffffff',
                textAlign: 'center',
                lineHeight: '44px',
                fontSize: '13px',
                fontWeight: '700',
                boxShadow:
                  '0 2px 8px rgba(0,0,0,0.2)',
              },
              {
                width: '54px',
                height: '54px',
                background:
                  'rgba(45,85,194,0.9)',
                borderRadius: '50%',
                color: '#ffffff',
                textAlign: 'center',
                lineHeight: '54px',
                fontSize: '14px',
                fontWeight: '700',
                boxShadow:
                  '0 3px 10px rgba(0,0,0,0.2)',
              },
              {
                width: '62px',
                height: '62px',
                background:
                  'rgba(29,78,216,0.92)',
                borderRadius: '50%',
                color: '#ffffff',
                textAlign: 'center',
                lineHeight: '62px',
                fontSize: '15px',
                fontWeight: '700',
                boxShadow:
                  '0 3px 12px rgba(0,0,0,0.24)',
              },
            ],
          });

        sdkRef.current = maps;
        mapRef.current = map;
        clustererRef.current =
          clusterer;

        setError(null);
        setReady(true);
      })
      .catch((caught: unknown) => {
        if (disposed) {
          return;
        }

        setError(
          caught instanceof Error
            ? caught.message
            : '카카오맵 초기화에 실패했습니다.',
        );
      });

    return () => {
      disposed = true;

      clustererRef.current?.clear();

      clustererRef.current?.setMap(
        null,
      );

      markerRef.current.forEach(
        (marker) => {
          marker.setMap(null);
        },
      );

      selectedMarkerRef.current?.setMap(
        null,
      );

      markerRef.current = [];
      selectedMarkerRef.current = null;

      clustererRef.current = null;
      mapRef.current = null;
      sdkRef.current = null;

      setReady(false);
    };
  }, [key]);

  /* ======================================
     12. 필터 변경 시 지도 마커 재생성
  ====================================== */

  useEffect(() => {
    const map = mapRef.current;
    const maps = sdkRef.current;

    const clusterer =
      clustererRef.current;

    if (
      !ready ||
      !map ||
      !maps ||
      !clusterer
    ) {
      return;
    }

    clearMarkers();

    // 동일 좌표를 사용하는 시설 묶기
    const groupedFacilities =
      groupFacilitiesByLocation(
        validFacilities,
      );

    const markers =
      groupedFacilities.map(
        (group) => {
          const facility = group[0];

          const position =
            new maps.LatLng(
              facility.latitude!,
              facility.longitude!,
            );

          // 클러스터에서 관리하므로
          // map 속성은 지정하지 않음
          const marker =
            new maps.Marker({
              position,
              title:
                group.length > 1
                  ? `${facility.name} 외 ${
                      group.length - 1
                    }건`
                  : facility.name,
              image:
                createMarkerImage(
                  maps,
                  false,
                ),
            });

          maps.event.addListener(
            marker,
            'click',
            () => {
              if (
                locationCallbackRef.current
              ) {
                locationCallbackRef.current(
                  group,
                );
              } else {
                callbackRef.current(
                  facility,
                );
              }
            },
          );

          return marker;
        },
      );

    markerRef.current = markers;

    if (markers.length > 0) {
      clusterer.addMarkers(
        markers,
      );
    }

    fitMapToFacilities();

    return () => {
      clearMarkers();
    };

  }, [
    facilities,
    ready,
  ]);

  /* ======================================
     13. 선택한 시설 강조 표시
  ====================================== */

  useEffect(() => {
    const map = mapRef.current;
    const maps = sdkRef.current;

    if (
      !ready ||
      !map ||
      !maps
    ) {
      return;
    }

    selectedMarkerRef.current?.setMap(
      null,
    );

    selectedMarkerRef.current = null;

    if (
      !selectedFacility ||
      selectedFacility.latitude == null ||
      selectedFacility.longitude == null ||
      !selectedFacility.map_marker_available
    ) {
      return;
    }

    const position =
      new maps.LatLng(
        selectedFacility.latitude,
        selectedFacility.longitude,
      );

    const highlightedMarker =
      new maps.Marker({
        map,
        position,
        title:
          selectedFacility.name,
        image:
          createMarkerImage(
            maps,
            true,
          ),
        zIndex: 100,
      });

    selectedMarkerRef.current =
      highlightedMarker;

    // 선택 위치가 잘 보이도록 확대
    if (map.getLevel() > 4) {
      map.setLevel(4);
    }

    map.setCenter(position);

    return () => {
      highlightedMarker.setMap(
        null,
      );
    };

  }, [
    selectedFacility,
    ready,
  ]);

  /* ======================================
     14. 지도 화면
  ====================================== */

  return (
    <div className="map-container">

      {/* 카카오 지도 */}

      <div
        ref={containerRef}
        className="kakao-map"
      />

      {/* 전체 보기 버튼 */}

      {ready && (
        <button
          type="button"
          className="map-reset-button"
          onClick={
            fitMapToFacilities
          }
          title="검색 결과 전체 보기"
        >
          <RotateCcw size={14} />
          전체 보기
        </button>
      )}

      {/* API 키 없음 */}

      {!key && (
        <div className="map-fallback">
          <AlertCircle size={26} />

          <strong>
            카카오맵 API 키가 없습니다.
          </strong>

          <p>
            frontend/.env.local의
            VITE_KAKAO_MAP_KEY를
            확인해 주세요.
          </p>
        </div>
      )}

      {/* 지도 로딩 오류 */}

      {key && error && (
        <div className="map-fallback">
          <AlertCircle size={26} />

          <strong>
            지도를 표시하지 못했습니다.
          </strong>

          <p>
            {error}
          </p>
        </div>
      )}

      {/* 지도 불러오는 중 */}

      {key && !error && !ready && (
        <div className="map-loading">
          <MapPin size={26} />

          <span>
            지도 불러오는 중...
          </span>
        </div>
      )}

      {/* 검색 결과 없음 */}

      {ready &&
        validFacilities.length === 0 && (
          <div className="map-empty">
            지도에 표시할 시설이 없습니다.
          </div>
        )}

    </div>
  );
}

export default KakaoMap;
