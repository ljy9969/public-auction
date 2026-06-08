import { useEffect, useRef } from "react";
import { formatPrice, type MarketSample, type ParcelGeometry } from "../api";

interface PropertyMapProps {
  lat: number;
  lng: number;
  title?: string;
  /** 시세 검증 비교 거래 — 백필 때 저장한 좌표(lat/lng)로 '주변' 검증 마커 표시 */
  comps?: MarketSample[];
  /** 일반 ↔ 위성(하이브리드) 토글. 외부 버튼이 우측 상단 H3 옆에 별도 배치되므로 */
  /*  Naver 기본 mapTypeControl 은 꺼두고 이 prop 으로만 제어. */
  mapType?: "normal" | "satellite";
  /** 지번(번지) 경계 폴리곤 — 마커와 함께 필지 영역 강조 */
  parcel?: ParcelGeometry | null;
}

type NaverWindow = Window & { naver?: { maps?: Record<string, unknown> } };

const SCRIPT_ID = "naver-map-sdk";

function propPin(): string {
  return `<div style="transform:translate(-50%,-100%);display:flex;flex-direction:column;align-items:center">
    <div style="background:#ef4444;color:#fff;font-size:11px;font-weight:700;padding:2px 7px;border-radius:10px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35);white-space:nowrap">매물</div>
    <div style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:7px solid #ef4444;margin-top:-1px"></div>
  </div>`;
}

function compPin(label: string): string {
  return `<div style="transform:translate(-50%,-50%);background:#2563eb;color:#fff;font-size:10px;font-weight:600;padding:2px 6px;border-radius:9px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3);white-space:nowrap;max-width:120px;overflow:hidden;text-overflow:ellipsis">${label}</div>`;
}

/** Naver Maps embed (requires VITE_NAVER_MAP_CLIENT_ID). Falls back to OSM iframe. */
export default function PropertyMap({ lat, lng, title, comps, mapType = "normal", parcel }: PropertyMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  // SDK 객체에 정적 타입이 없어 런타임 ref 로만 보관 — mapType 변경 시 setMapTypeId 호출.
  const mapInstanceRef = useRef<any>(null);
  const parcelRef = useRef<any>(null);
  const naverKey = (import.meta.env.VITE_NAVER_MAP_CLIENT_ID as string | undefined)?.trim();

  useEffect(() => {
    if (!naverKey || !mapRef.current) return;

    const init = () => {
      // SDK는 동적이라 정적 타입이 없다 — 런타임 객체로 사용.
      const maps = (window as NaverWindow).naver?.maps as any;
      if (!maps || !mapRef.current) return;

      const center = new maps.LatLng(lat, lng);
      const map = new maps.Map(mapRef.current, {
        center,
        zoom: 15,
        mapTypeControl: false, // 외부 토글 버튼이 H3 옆에 별도로 있음
      });
      mapInstanceRef.current = map;
      // 매물 본 마커 (빨강 핀)
      new maps.Marker({
        position: center,
        map,
        zIndex: 1000,
        title: title || "물건 위치",
        icon: { content: propPin(), anchor: new maps.Point(0, 0) },
      });

      // 비교 거래 마커 — 백필 때 저장한 좌표 사용 (같은 동·지번끼리 묶어 1개)
      const withCoord = (comps || []).filter(
        (c) => c.lat != null && c.lng != null
      );
      if (withCoord.length === 0) return;

      const byKey = new Map<
        string,
        { lat: number; lng: number; name: string; dong: string; jibun: string; prices: number[] }
      >();
      for (const c of withCoord) {
        const k = `${c.lat},${c.lng}`;
        if (!byKey.has(k))
          byKey.set(k, {
            lat: c.lat as number,
            lng: c.lng as number,
            name: c.name,
            dong: c.dong,
            jibun: c.jibun || "",
            prices: [],
          });
        if (c.deal_amount) byKey.get(k)!.prices.push(c.deal_amount);
      }

      const bounds = new maps.LatLngBounds();
      bounds.extend(center);
      byKey.forEach((v) => {
        const ll = new maps.LatLng(v.lat, v.lng);
        const cnt = v.prices.length;
        const lo = cnt ? Math.min(...v.prices) : 0;
        const hi = cnt ? Math.max(...v.prices) : 0;
        const priceTxt = cnt
          ? ` · ${cnt}건 ${formatPrice(lo)}${hi !== lo ? `~${formatPrice(hi)}` : ""}`
          : "";
        new maps.Marker({
          position: ll,
          map,
          zIndex: 100,
          title: `${v.name || v.dong} ${v.jibun}${priceTxt}`,
          icon: { content: compPin(v.name || v.dong), anchor: new maps.Point(0, 0) },
        });
        bounds.extend(ll);
      });
      map.fitBounds(bounds);
    };

    if ((window as NaverWindow).naver?.maps) {
      init();
      return;
    }
    if (document.getElementById(SCRIPT_ID)) {
      const t = window.setInterval(() => {
        if ((window as NaverWindow).naver?.maps) {
          window.clearInterval(t);
          init();
        }
      }, 60);
      return () => window.clearInterval(t);
    }
    const s = document.createElement("script");
    s.id = SCRIPT_ID;
    s.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${encodeURIComponent(naverKey)}`;
    s.async = true;
    s.onload = init;
    document.head.appendChild(s);
  }, [lat, lng, naverKey, comps, title]);

  // 외부 토글이 mapType 을 바꾸면 지도에 반영. 'satellite' 는 라벨 포함된 HYBRID 로
  // (도로명/지번이 보여 위치 파악이 쉬움). 'normal' 은 NORMAL.
  useEffect(() => {
    const maps = (window as NaverWindow).naver?.maps as any;
    const map = mapInstanceRef.current;
    if (!map || !maps?.MapTypeId) return;
    map.setMapTypeId(
      mapType === "satellite" ? maps.MapTypeId.HYBRID : maps.MapTypeId.NORMAL
    );
  }, [mapType]);

  // 지번 경계 폴리곤 그리기 — parcel 도착/변경 시. (지도 init 이후 별도 오버레이)
  useEffect(() => {
    const maps = (window as NaverWindow).naver?.maps as any;
    const map = mapInstanceRef.current;
    if (!maps || !map) return;
    parcelRef.current?.setMap(null);
    parcelRef.current = null;
    if (!parcel) return;
    const ring = (r: number[][]) => r.map(([lo, la]: number[]) => new maps.LatLng(la, lo));
    const paths =
      parcel.type === "MultiPolygon"
        ? (parcel.coordinates as number[][][][]).flatMap((poly) => poly.map(ring))
        : (parcel.coordinates as number[][][]).map(ring);
    try {
      parcelRef.current = new maps.Polygon({
        map,
        paths,
        fillColor: "#2563eb",
        fillOpacity: 0.18,
        strokeColor: "#2563eb",
        strokeOpacity: 0.9,
        strokeWeight: 2,
        clickable: false,
        zIndex: 50,
      });
    } catch {
      /* 좌표 형식 이상 시 폴리곤 생략 */
    }
  }, [parcel]);

  if (naverKey) {
    return (
      <div
        ref={mapRef}
        className="property-map"
        style={{ width: "100%", height: 280, borderRadius: 8 }}
        aria-label={title || "물건 위치"}
      />
    );
  }

  const pad = 0.008;
  const bbox = `${lng - pad},${lat - pad},${lng + pad},${lat + pad}`;
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik&marker=${lat}%2C${lng}`;

  return (
    <iframe
      title={title || "물건 위치"}
      className="property-map"
      src={src}
      style={{ width: "100%", height: 280, border: 0, borderRadius: 8 }}
      loading="lazy"
    />
  );
}
