import { useEffect, useRef } from "react";

export interface ListMarker {
  id: number;
  lat: number;
  lng: number;
  label: string;
  index: number;
}

interface Props {
  markers: ListMarker[];
  highlightedId: number | null;
  /** Optional click handler — selects a list item from the map */
  onMarkerClick?: (id: number) => void;
}

type NaverMap = {
  setCenter: (latlng: unknown) => void;
  panTo: (latlng: unknown) => void;
  fitBounds: (bounds: unknown) => void;
  setZoom: (z: number) => void;
};

type NaverMarker = {
  setMap: (m: NaverMap | null) => void;
  setIcon: (icon: object) => void;
  setZIndex: (z: number) => void;
  getPosition: () => unknown;
  addListener: (ev: string, fn: () => void) => void;
};

type NaverMaps = {
  Map: new (el: HTMLElement, opts: object) => NaverMap;
  LatLng: new (lat: number, lng: number) => unknown;
  LatLngBounds: new () => { extend: (latlng: unknown) => void };
  Marker: new (opts: object) => NaverMarker;
  Point: new (x: number, y: number) => unknown;
  Size: new (w: number, h: number) => unknown;
};

type NaverWindow = Window & { naver?: { maps?: NaverMaps } };

const SCRIPT_ID = "naver-map-sdk";

function makeIcon(naver: NaverMaps, num: number, active: boolean) {
  const bg = active ? "#ef4444" : "#1d4ed8";
  const scale = active ? "scale(1.35)" : "scale(1)";
  return {
    content: `<div style="background:${bg};color:#fff;width:28px;height:28px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:13px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.35);transform:${scale};transition:transform 0.15s ease-out,background 0.15s">${num}</div>`,
    size: new naver.Size(28, 28),
    anchor: new naver.Point(14, 14),
  };
}

export default function ListMap({ markers, highlightedId, onMarkerClick }: Props) {
  const mapDiv = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<NaverMap | null>(null);
  const markerInstances = useRef<NaverMarker[]>([]);
  // 사용자가 Naver 기본 컨트롤로 토글한 mapType (예: '위성') 을 보존해, init 이 다시
  // 트리거(필터 변경 등으로 markers 새 identity) 되어도 이전 선택을 그대로 복원.
  const mapTypeRef = useRef<string | null>(null);
  // 직전에 그렸던 markers 의 id 시퀀스. 진짜 markers 내용이 변했을 때만 fitBounds —
  // 카드 hover 로 markers 가 같은 set 으로 재생성돼도 zoom/center/mapType 유지.
  const prevMarkerIdsRef = useRef<string>("");
  // onMarkerClick은 부모(PropertyList)에서 인라인 화살표로 넘어와 매 렌더마다 identity가 바뀐다.
  // 이걸 아래 init useEffect deps에 직접 넣으면: 마커 클릭 → 부모 리렌더 → 핸들러 identity 변경
  // → 맵 재초기화(fitBounds) → 줌이 서울 전체로 리셋되는 버그가 생긴다.
  // ref로 최신 핸들러만 들고 있으면 재초기화 없이 클릭 시점의 핸들러를 호출할 수 있다.
  const onMarkerClickRef = useRef(onMarkerClick);
  onMarkerClickRef.current = onMarkerClick;
  const naverKey = (import.meta.env.VITE_NAVER_MAP_CLIENT_ID as string | undefined)?.trim();

  // Initialize map + markers when the marker set changes
  useEffect(() => {
    if (!naverKey || !mapDiv.current || markers.length === 0) return;

    const init = () => {
      const naver = (window as NaverWindow).naver?.maps;
      if (!naver || !mapDiv.current) return;

      // 첫 호출이면 Map 인스턴스 생성 + maptype listener 등록. 이후 호출은 같은
      // Map 을 재사용 — mapType/zoom/center 가 보존되어 hover 등으로 마커가
      // 새 identity 가 되어도 시각 상태가 그대로 유지된다.
      const isFirstInit = !mapInstance.current;
      if (isFirstInit) {
        const map = new naver.Map(mapDiv.current, {
          zoom: 14,
          mapTypeControl: true, // 일반 ↔ 위성 토글 (Naver 기본 컨트롤)
        });
        mapInstance.current = map;
        const mapAny = map as unknown as {
          setMapTypeId: (id: string) => void;
          getMapTypeId: () => string;
          addListener: (ev: string, fn: () => void) => void;
        };
        if (mapTypeRef.current) {
          mapAny.setMapTypeId(mapTypeRef.current);
        }
        mapAny.addListener("maptypeid_changed", () => {
          try {
            mapTypeRef.current = mapAny.getMapTypeId();
          } catch {
            /* ignore */
          }
        });
      }
      const map = mapInstance.current!;

      // 마커는 매번 다시 그림 (강조 상태/순번 변화 반영).
      markerInstances.current.forEach((m) => m.setMap(null));
      markerInstances.current = markers.map((m) => {
        const marker = new naver.Marker({
          position: new naver.LatLng(m.lat, m.lng),
          map,
          title: m.label,
          icon: makeIcon(naver, m.index, false),
          zIndex: 100,
        });
        marker.addListener("click", () => onMarkerClickRef.current?.(m.id));
        return marker;
      });

      // markers 내용이 진짜 바뀐 첫 init 일 때만 fitBounds — 같은 set 으로 hover
      // 인해 ref 만 새로워진 경우엔 zoom/center 유지.
      const idsKey = markers.map((m) => m.id).join(",");
      if (isFirstInit || idsKey !== prevMarkerIdsRef.current) {
        if (markers.length === 1) {
          map.setCenter(new naver.LatLng(markers[0].lat, markers[0].lng));
          map.setZoom(11);
        } else {
          const bounds = new naver.LatLngBounds();
          markers.forEach((m) => bounds.extend(new naver.LatLng(m.lat, m.lng)));
          map.fitBounds(bounds);
        }
        prevMarkerIdsRef.current = idsKey;
      }
    };

    const w = window as NaverWindow;
    if (w.naver?.maps) {
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
  }, [markers, naverKey]);

  // Update highlight when selection changes — 마커 색은 즉시, panTo 만 debounce.
  // (카드 hover 가 빠르게 옮겨다닐 때 지도가 흔들리는 문제 — 한 카드 위에
  //  300ms 머무를 때만 지도가 이동.)
  useEffect(() => {
    const naver = (window as NaverWindow).naver?.maps;
    if (!naver) return;
    markers.forEach((m, i) => {
      const marker = markerInstances.current[i];
      if (!marker) return;
      const active = m.id === highlightedId;
      marker.setIcon(makeIcon(naver, m.index, active));
      marker.setZIndex(active ? 1000 : 100);
    });
    if (highlightedId == null) return;
    const target = markers.find((x) => x.id === highlightedId);
    if (!target || !mapInstance.current) return;
    const timer = window.setTimeout(() => {
      // panTo는 목표가 멀면 부드러운 이동을 위해 '줌아웃→이동→줌인' morph를 써서
      // 현재 줌이 살짝 바뀐다. 사용자가 확대해 둔 화면을 그대로 유지하려면
      // 줌을 건드리지 않고 중심만 옮기는 setCenter를 쓴다.
      mapInstance.current?.setCenter(new naver.LatLng(target.lat, target.lng));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [highlightedId, markers]);

  if (!naverKey) {
    return (
      <div className="list-map-empty">
        지도를 보려면 <code>web/.env</code>의 <code>VITE_NAVER_MAP_CLIENT_ID</code>를 설정하세요.
      </div>
    );
  }
  if (markers.length === 0) {
    return <div className="list-map-empty">표시할 좌표가 있는 물건이 없습니다.</div>;
  }
  return <div ref={mapDiv} className="list-map" />;
}
