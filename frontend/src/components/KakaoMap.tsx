
import { useEffect, useRef, useState } from 'react';
import {
    AlertCircle,
    MapPin,
    RotateCcw,
} from 'lucide-react';

import type { Facility } from '../types/medicine';

// ==========================================
// 1. Kakao Maps 타입
// ==========================================

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

interface KakaoMarkerImage { }

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

// ==========================================
// 2. SDK 불러오기
// ==========================================

let sdkPromise: Promise<KakaoMaps> | null = null;

function loadKakaoMaps(
    key: string,
): Promise<KakaoMaps> {
    if (sdkPromise) {
        return sdkPromise;
    }

    const promise = new Promise<KakaoMaps>((resolve, reject) => {
        const initialize = (maps: KakaoMaps) => {
            maps.load(() => {
                if (typeof maps.MarkerClusterer !== 'function') {
                    reject(
                        new Error(
                            '클러스터링 라이브러리가 로드되지 않았습니다. ' +
                            '기존 SDK 스크립트가 중복 로드되는지 확인해 주세요.',
                        ),
                    );
                    return;
                }

                resolve(maps);
            });
        };

        // 이미 클러스터 라이브러리까지 로드된 경우
        if (
            window.kakao?.maps &&
            typeof window.kakao.maps.MarkerClusterer === 'function'
        ) {
            initialize(window.kakao.maps);
            return;
        }

        // 기존 일반 SDK가 로드된 상태라면
        // 라이브러리가 없는 SDK를 그대로 재사용하지 않음
        if (window.kakao?.maps) {
            reject(
                new Error(
                    '이전에 로드된 카카오맵 SDK에 clusterer가 없습니다. ' +
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
                    new Error('카카오맵 SDK 객체를 찾지 못했습니다.'),
                );
                return;
            }

            // SDK 초기화 후 라이브러리 검사
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
    });

    sdkPromise = promise.catch((error: unknown) => {
        sdkPromise = null;
        throw error;
    });

    return sdkPromise;
}


// ==========================================
// 3. 마커 이미지
// ==========================================

function createMarkerImage(
    maps: KakaoMaps,
    selected: boolean,
): KakaoMarkerImage {
    const color = selected ? '#ef4444' : '#4f67d9';
    const size = selected ? 42 : 32;

    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg"
         width="${size}"
         height="${size + 8}"
         viewBox="0 0 42 50">
      <path
        d="M21 2 C11 2 4 10 4 20
           C4 34 21 47 21 47
           C21 47 38 34 38 20
           C38 10 31 2 21 2Z"
        fill="${color}"
        stroke="#ffffff"
        stroke-width="2.5"
      />
      <circle cx="21" cy="20" r="7"
              fill="#ffffff"/>
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

// ==========================================
// 4. Props
// ==========================================

interface KakaoMapProps {
    facilities: Facility[];
    selectedFacility: Facility | null;
    onSelectFacility: (facility: Facility) => void;
}

// ==========================================
// 5. 메인 컴포넌트
// ==========================================

export default function KakaoMap({
    facilities,
    selectedFacility,
    onSelectFacility,
}: KakaoMapProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    const mapRef = useRef<KakaoMapInstance | null>(null);
    const sdkRef = useRef<KakaoMaps | null>(null);
    const clustererRef = useRef<KakaoClusterer | null>(null);

    const markerRef = useRef<KakaoMarker[]>([]);
    const selectedMarkerRef = useRef<KakaoMarker | null>(null);

    const callbackRef = useRef(onSelectFacility);
    const facilitiesRef = useRef(facilities);

    const [ready, setReady] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const key = import.meta.env.VITE_KAKAO_MAP_KEY as
        | string
        | undefined;

    const validFacilities = facilities.filter(
        (facility) =>
            facility.map_marker_available &&
            facility.latitude != null &&
            facility.longitude != null &&
            Number.isFinite(facility.latitude) &&
            Number.isFinite(facility.longitude),
    );

    useEffect(() => {
        callbackRef.current = onSelectFacility;
        facilitiesRef.current = facilities;
    }, [onSelectFacility, facilities]);

    // ========================================
    // 6. 마커 정리 함수
    // ========================================

    function clearMarkers() {
        clustererRef.current?.clear();

        markerRef.current.forEach((marker) => {
            marker.setMap(null);
        });

        markerRef.current = [];
    }

    // ========================================
    // 7. 현재 표시 대상 전체 보기
    // ========================================

    function fitMapToFacilities() {
        const map = mapRef.current;
        const maps = sdkRef.current;

        if (!map || !maps) return;

        const valid = facilitiesRef.current.filter(
            (facility) =>
                facility.map_marker_available &&
                facility.latitude != null &&
                facility.longitude != null,
        );

        map.relayout();

        if (valid.length === 0) {
            map.setCenter(
                new maps.LatLng(37.5665, 126.978),
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

        const bounds = new maps.LatLngBounds();

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

    // ========================================
    // 8. 최초 지도 생성
    // ========================================

    useEffect(() => {
        if (!key) {
            setError('카카오맵 JavaScript 키가 없습니다.');
            return;
        }

        let disposed = false;

        loadKakaoMaps(key)
            .then((maps) => {
                if (disposed || !containerRef.current) {
                    return;
                }

                const map = new maps.Map(
                    containerRef.current,
                    {
                        center: new maps.LatLng(37.5665, 126.978),
                        level: 8,
                    },
                );

                const clusterer = new maps.MarkerClusterer({
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
                            background: 'rgba(79,103,217,0.88)',
                            borderRadius: '50%',
                            color: '#ffffff',
                            textAlign: 'center',
                            lineHeight: '44px',
                            fontSize: '13px',
                            fontWeight: '700',
                            boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
                        },
                        {
                            width: '54px',
                            height: '54px',
                            background: 'rgba(45,85,194,0.9)',
                            borderRadius: '50%',
                            color: '#ffffff',
                            textAlign: 'center',
                            lineHeight: '54px',
                            fontSize: '14px',
                            fontWeight: '700',
                            boxShadow: '0 3px 10px rgba(0,0,0,0.2)',
                        },
                        {
                            width: '62px',
                            height: '62px',
                            background: 'rgba(29,78,216,0.92)',
                            borderRadius: '50%',
                            color: '#ffffff',
                            textAlign: 'center',
                            lineHeight: '62px',
                            fontSize: '15px',
                            fontWeight: '700',
                            boxShadow: '0 3px 12px rgba(0,0,0,0.24)',
                        },
                    ],
                });

                sdkRef.current = maps;
                mapRef.current = map;
                clustererRef.current = clusterer;

                setError(null);
                setReady(true);
            })
            .catch((caught: unknown) => {
                if (disposed) return;

                setError(
                    caught instanceof Error
                        ? caught.message
                        : '카카오맵 초기화에 실패했습니다.',
                );
            });

        return () => {
            disposed = true;

            clustererRef.current?.clear();
            clustererRef.current?.setMap(null);

            markerRef.current.forEach((marker) => {
                marker.setMap(null);
            });

            selectedMarkerRef.current?.setMap(null);

            markerRef.current = [];
            selectedMarkerRef.current = null;
            clustererRef.current = null;
            mapRef.current = null;
            sdkRef.current = null;

            setReady(false);
        };
    }, [key]);

    // ========================================
    // 9. 필터에 맞게 클러스터 갱신
    // ========================================

    useEffect(() => {
        const map = mapRef.current;
        const maps = sdkRef.current;
        const clusterer = clustererRef.current;

        if (!ready || !map || !maps || !clusterer) {
            return;
        }

        clearMarkers();

        const markers = validFacilities.map((facility) => {
            const position = new maps.LatLng(
                facility.latitude!,
                facility.longitude!,
            );

            // 클러스터에서 관리하므로
            // 여기에서는 map 속성을 설정하지 않음
            const marker = new maps.Marker({
                position,
                title: facility.name,
                image: createMarkerImage(maps, false),
            });

            maps.event.addListener(
                marker,
                'click',
                () => {
                    callbackRef.current(facility);
                },
            );

            return marker;
        });

        markerRef.current = markers;

        if (markers.length > 0) {
            clusterer.addMarkers(markers);
        }

        fitMapToFacilities();
    }, [facilities, ready]);

    // ========================================
    // 10. 선택한 시설 강조
    // ========================================

    useEffect(() => {
        const map = mapRef.current;
        const maps = sdkRef.current;

        if (!ready || !map || !maps) return;

        selectedMarkerRef.current?.setMap(null);
        selectedMarkerRef.current = null;

        if (
            !selectedFacility ||
            selectedFacility.latitude == null ||
            selectedFacility.longitude == null ||
            !selectedFacility.map_marker_available
        ) {
            return;
        }

        const position = new maps.LatLng(
            selectedFacility.latitude,
            selectedFacility.longitude,
        );

        // 선택한 마커는 클러스터와 별개로
        // 지도 위에 강조 표시
        const highlightedMarker = new maps.Marker({
            map,
            position,
            title: selectedFacility.name,
            image: createMarkerImage(maps, true),
            zIndex: 100,
        });

        selectedMarkerRef.current = highlightedMarker;

        // 클러스터가 풀리는 확대 수준으로 이동
        if (map.getLevel() > 4) {
            map.setLevel(4);
        }

        map.setCenter(position);

        return () => {
            highlightedMarker.setMap(null);
        };
    }, [selectedFacility, ready]);

    // ========================================
    // 11. 화면 출력
    // ========================================

    return (
        <div className="map-container">
            <div
                ref={containerRef}
                className="kakao-map"
            />

            {ready && (
                <button
                    type="button"
                    className="map-reset-button"
                    onClick={fitMapToFacilities}
                    title="검색 결과 전체 보기"
                >
                    <RotateCcw size={14} />
                    전체 보기
                </button>
            )}

            {!key && (
                <div className="map-fallback">
                    <AlertCircle size={26} />
                    <strong>카카오맵 API 키가 없습니다.</strong>
                    <p>
                        frontend/.env.local의
                        VITE_KAKAO_MAP_KEY를 확인해 주세요.
                    </p>
                </div>
            )}

            {key && error && (
                <div className="map-fallback">
                    <AlertCircle size={26} />
                    <strong>지도를 표시하지 못했습니다.</strong>
                    <p>{error}</p>
                </div>
            )}

            {key && !error && !ready && (
                <div className="map-loading">
                    <MapPin size={26} />
                    <span>지도 불러오는 중...</span>
                </div>
            )}

            {ready && validFacilities.length === 0 && (
                <div className="map-empty">
                    지도에 표시할 시설이 없습니다.
                </div>
            )}
        </div>
    );
}
