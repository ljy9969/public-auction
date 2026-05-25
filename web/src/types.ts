export interface Property {
  id?: number;
  cltr_no: string;
  pbct_no?: string | null;
  pbct_cdtn_no?: string | null;
  title: string;
  address_jibun?: string | null;
  category?: string | null;
  bid_method?: string | null;
  min_price?: number | null;
  appraisal_price?: number | null;
  area_build_m2?: number | null;
  fail_count?: number | null;
  bid_start?: string | null;
  bid_end?: string | null;
  status?: string | null;
  transit_minutes?: number | null;
  transit_estimated?: boolean;
  distance_seolleung_km?: number | null;
  source_url?: string | null;
  scraped_at?: string | null;
  passes_filters?: boolean;
  filter_notes?: string[] | unknown;
  fee_rate?: string | null;
  region_line?: string | null;
  detail_json?: Record<string, string> | null;
  rights_json?: Record<string, string> | null;
  schedule_json?: Record<string, string> | null;
}

export interface ScrapeStatus {
  running: boolean;
  message?: string | null;
  count: number;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}
