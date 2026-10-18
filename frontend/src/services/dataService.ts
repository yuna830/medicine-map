
import type {
  District,
  Facility,
  MedicineData,
  Metadata,
  MonthlyCollection,
  SpatialAnalysis,
} from '../types/medicine';

async function fetchJson<T>(filename: string): Promise<T> {
  const url = `${import.meta.env.BASE_URL}data/${filename}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `${filename} 파일을 불러오지 못했습니다. ` +
      `(HTTP ${response.status})`,
    );
  }

  return (await response.json()) as T;
}

export async function loadMedicineData(): Promise<MedicineData> {
  const [
    facilities,
    districts,
    monthly,
    metadata,
    spatial,
  ] = await Promise.all([
    fetchJson<Facility[]>('facilities.json'),
    fetchJson<District[]>('districts.json'),
    fetchJson<MonthlyCollection[]>('collection_monthly.json'),
    fetchJson<Metadata>('metadata.json'),
    fetchJson<SpatialAnalysis>('spatial_analysis.json'),
  ]);

  if (
    !Array.isArray(facilities) ||
    !Array.isArray(districts) ||
    !Array.isArray(monthly) ||
    !Array.isArray(spatial?.districts)
  ) {
    throw new Error('JSON 데이터 형식이 올바르지 않습니다.');
  }

  if (facilities.length !== metadata.records.facility_count) {
    throw new Error('시설 기록 수가 메타데이터와 일치하지 않습니다.');
  }

  if (districts.length !== metadata.coverage.district_count) {
    throw new Error('자치구 수가 메타데이터와 일치하지 않습니다.');
  }

  if (monthly.length !== metadata.records.monthly_volume_records) {
    throw new Error('월별 처리량 데이터 수가 일치하지 않습니다.');
  }

  const facilityIds = new Set(
    facilities.map((facility) => facility.id),
  );

  if (facilityIds.size !== facilities.length) {
    throw new Error('중복된 수거시설 ID가 있습니다.');
  }

  const districtNames = new Set(
    districts.map((district) => district.district),
  );

  for (const facility of facilities) {
    if (!districtNames.has(facility.district)) {
      throw new Error(`알 수 없는 자치구: ${facility.district}`);
    }
  }

  const markerCount = facilities.filter(
    (facility) => facility.map_marker_available,
  ).length;

  if (markerCount !== metadata.records.map_marker_count) {
    throw new Error('지도 표시 가능 시설 수가 일치하지 않습니다.');
  }

  if (
    spatial.total_records !== facilities.length ||
    spatial.coordinate_records !== markerCount ||
    spatial.missing_coordinates !==
      metadata.records.missing_coordinate_count ||
    spatial.district_count !== districts.length ||
    !Number.isFinite(spatial.mean_nearest_m)
  ) {
    throw new Error(
      '공간 분석 결과가 시설 데이터와 일치하지 않습니다.',
    );
  }

  const spatialDistrictNames = new Set(
    spatial.districts.map((item) => item.district),
  );

  if (
    spatialDistrictNames.size !== districtNames.size ||
    [...districtNames].some(
      (name) => !spatialDistrictNames.has(name),
    )
  ) {
    throw new Error(
      '공간 분석 대상 자치구가 일치하지 않습니다.',
    );
  }

  for (const district of districts) {
    const spatialDistrict = spatial.districts.find(
      (item) => item.district === district.district,
    );

    if (
      !spatialDistrict ||
      spatialDistrict.facility_records !== district.spatial_candidates
    ) {
      throw new Error(
        `${district.district}의 공간 분석 기록 수가 일치하지 않습니다.`,
      );
    }
  }

  return {
    facilities,
    districts,
    monthly,
    metadata,
    spatial,
  };
}
