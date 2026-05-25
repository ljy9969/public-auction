import { useEffect, useRef } from "react";

interface PropertyMapProps {
  lat: number;
  lng: number;
  title?: string;
}

type NaverMaps = {
  Map: new (el: HTMLElement, opts: object) => unknown;
  LatLng: new (lat: number, lng: number) => unknown;
  Marker: new (opts: { position: unknown; map: unknown }) => unknown;
};

type NaverWindow = Window & {
  naver?: { maps?: NaverMaps };
};

/** Naver Maps embed (requires VITE_NAVER_MAP_CLIENT_ID). Falls back to OSM iframe. */
export default function PropertyMap({ lat, lng, title }: PropertyMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const naverKey = (import.meta.env.VITE_NAVER_MAP_CLIENT_ID as string | undefined)?.trim();

  useEffect(() => {
    if (!naverKey || !mapRef.current) return;

    const scriptId = "naver-map-sdk";
    const init = () => {
      const w = window as NaverWindow;
      const maps = w.naver?.maps;
      if (!maps || !mapRef.current) return;
      const center = new maps.LatLng(lat, lng);
      const map = new maps.Map(mapRef.current, { center, zoom: 16 });
      new maps.Marker({ position: center, map });
    };

    if (document.getElementById(scriptId)) {
      init();
      return;
    }
    const s = document.createElement("script");
    s.id = scriptId;
    s.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${encodeURIComponent(naverKey)}`;
    s.async = true;
    s.onload = init;
    document.head.appendChild(s);
  }, [lat, lng, naverKey]);

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
