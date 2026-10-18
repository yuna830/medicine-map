
export interface Facility {
  id: number;
  district: string;
  name: string;

  road_address: string | null;
  lot_address?: string | null;

  latitude: number | null;
  longitude: number | null;

  reference_date: string | null;
  source_file: string;

  map_marker_available: boolean;
  operation_verified: boolean;

  data_quality_review: boolean;
  temporal_review: boolean;
  count_analysis_candidate?: boolean;
  spatial_analysis_candidate?: boolean;

  same_coordinate?: boolean;
  same_address?: boolean;
  review_reasons: string | null;

  nearest_record_id: number | null;
  nearest_name: string | null;
  nearest_district: string | null;
  nearest_distance_km: number | null;
  nearest_distance_m: number | null;

  nearest_same_district_km: number | null;
  nearest_same_district_m: number | null;

  nearest_distinct_km: number | null;
  nearest_distinct_m: number | null;

  location_status: string;
  data_notice: string;

  coordinate_source?: string | null;
  coordinate_validation_status?: string | null;
}

export interface District {
  district: string;
  facility_records: number;

  population_total: number;
  population_65_plus: number;

  facilities_per_10000: number;
  facilities_per_10000_seniors: number;

  rank_per_10000: number;
  rank_per_10000_seniors?: number;

  senior_population_pct?: number;

  quality_review_records: number;
  temporal_review_records: number;
  spatial_candidates: number;

  flow_total: number;
  flow_age_60_plus: number;
  flow_age_60_plus_pct?: number;
  resident_senior_pct?: number;

  annual_total_reported: number;
  annual_total_needs_review?: boolean;

  collection_volume_year: number;
  collection_volume_unit: string | null;

  population_period?: string;
  flow_period?: string;
  comparison_warning?: string;
}

export interface MonthlyCollection {
  district: string;
  year: number;
  quarter?: number;
  month: number;
  period: string;
  collection_value: number;
  unit_verified?: boolean;
}

export interface Metadata {
  project: string;

  coverage: {
    city: string;
    districts: string[];
    district_count: number;
    not_seoul_wide: boolean;
  };

  records: {
    facility_count: number;
    map_marker_count: number;
    missing_coordinate_count: number;
    monthly_volume_records: number;
  };

  periods: {
    population: string;
    flow_population: string;
    collection_volume: string;
    facility_reference_dates_vary: boolean;
  };

  limitations: string[];
}

export interface SpatialDistrict {
  district: string;
  facility_records: number;
  mean_nearest_km: number;
  mean_nearest_m: number;
  median_nearest_m: number;
  max_nearest_m: number;
  mean_distinct_nearest_m: number;
  same_coordinate_records: number;
}

export interface SpatialAnalysis {
  generated_at: string;
  source_file: string;
  method: string;
  earth_radius_km: number;
  scope: string;

  total_records: number;
  district_count: number;
  coordinate_records: number;
  missing_coordinates: number;

  mean_nearest_km: number;
  mean_nearest_m: number;
  median_nearest_km: number;
  median_nearest_m: number;
  max_nearest_km: number;
  max_nearest_m: number;

  nearest_over_1km_records: number;
  same_coordinate_records: number;

  mean_distinct_nearest_km: number;
  mean_distinct_nearest_m: number;
  distinct_nearest_over_1km_records: number;
  nearest_other_district_records: number;

  districts: SpatialDistrict[];
  cautions: string[];
}

export interface MedicineData {
  facilities: Facility[];
  districts: District[];
  monthly: MonthlyCollection[];
  metadata: Metadata;
  spatial: SpatialAnalysis;
}
