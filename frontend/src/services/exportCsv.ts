
import type {
  District,
  Facility,
  MonthlyCollection,
  SpatialAnalysis,
} from '../types/medicine';

type CsvValue =
  | string
  | number
  | boolean
  | null
  | undefined;

function escapeCsv(value: CsvValue): string {
  const text = value == null ? '' : String(value);

  const safe =
    typeof value === 'string' &&
    /^[\s]*[=+@\-\t\r]/.test(text)
      ? `'${text}`
      : text;

  return `"${safe.replace(/"/g, '""')}"`;
}

function saveCsv(
  filename: string,
  headers: string[],
  rows: CsvValue[][],
): void {
  const content = [headers, ...rows]
    .map((row) => row.map(escapeCsv).join(','))
    .join('\r\n');

  const blob = new Blob(
    ['\uFEFF', content],
    {
      type: 'text/csv;charset=utf-8;',
    },
  );

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');

  anchor.href = url;
  anchor.download = filename;

  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 1000);
}

export function exportDistrictCsv(
  districts: District[],
  spatial: SpatialAnalysis,
): void {
  const distanceMap = new Map(
    spatial.districts.map((item) => [
      item.district,
      item.mean_nearest_m,
    ]),
  );

  saveCsv(
    'medicine_district_analysis.csv',
    [
      '자치구',
      '시설기록수',
      '전체인구_2026Q2',
      '65세이상인구_2026Q2',
      '전체인구1만명당시설기록수',
      '고령인구1만명당시설기록수',
      '평균최근접직선거리_m',
      '시설기준시점상이',
      '운영여부확인',
    ],
    districts.map((district) => [
      district.district,
      district.facility_records,
      district.population_total,
      district.population_65_plus,
      district.facilities_per_10000,
      district.facilities_per_10000_seniors,
      distanceMap.get(district.district) ?? null,
      true,
      false,
    ]),
  );
}

export function exportFacilityCsv(
  facilities: Facility[],
  filename = 'medicine_facility_records.csv',
): void {
  saveCsv(
    filename,
    [
      '기록ID',
      '자치구',
      '시설명',
      '도로명주소',
      '지번주소',
      '위도',
      '경도',
      '시설자료기준일',
      '원본파일',
      '운영여부확인',
    ],
    facilities.map((facility) => [
      facility.id,
      facility.district,
      facility.name,
      facility.road_address,
      facility.lot_address,
      facility.latitude,
      facility.longitude,
      facility.reference_date,
      facility.source_file,
      facility.operation_verified,
    ]),
  );
}

export function exportMonthlyCsv(
  monthly: MonthlyCollection[],
): void {
  saveCsv(
    'medicine_collection_monthly_2024.csv',
    [
      '자치구',
      '기준연도',
      '월',
      '기준기간',
      '원본처리량수치',
      '측정단위',
      '공식단위확인',
    ],
    monthly.map((item) => [
      item.district,
      item.year,
      item.month,
      item.period,
      item.collection_value,
      item.unit_verified === true
        ? 'kg'
        : '미확인',
      item.unit_verified === true,
    ]),
  );
}
