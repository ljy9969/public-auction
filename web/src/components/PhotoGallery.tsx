import { useCallback, useEffect, useState } from "react";

interface Props {
  urls: string[];
  alt?: string;
}

/**
 * 사진 갤러리 — 썸네일 클릭 시 lightbox 프리뷰.
 *
 *  - 평소: 작은 ELGM 썸네일 (20KB)
 *  - 클릭: lightbox + CLG 큰 사진 (~300KB)
 *  - 좌우 nav (썸네일 / lightbox 둘 다)
 *  - ESC / 백드롭 클릭 → lightbox 닫기
 *  - 로드 실패 자동 hide
 */
function _toFullSize(url: string): string {
  // ELGM (감정평가서 썸네일) → CLG (공매 본 파일, 더 큼)
  return url.replace("ELGM_FILE_NM", "CLG_FILE_NM");
}

export default function PhotoGallery({ urls, alt }: Props) {
  const [validUrls, setValidUrls] = useState<string[]>(urls);
  const [idx, setIdx] = useState(0);
  const [lightbox, setLightbox] = useState(false);

  useEffect(() => {
    setValidUrls(urls);
    setIdx(0);
  }, [urls]);

  const total = validUrls.length;
  const current = validUrls[idx];
  const hasMultiple = total > 1;

  const prev = useCallback(
    () => setIdx((i) => (i - 1 + total) % total),
    [total]
  );
  const next = useCallback(
    () => setIdx((i) => (i + 1) % total),
    [total]
  );

  // ESC / 화살표 키
  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(false);
      else if (e.key === "ArrowLeft") prev();
      else if (e.key === "ArrowRight") next();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [lightbox, prev, next]);

  if (total === 0) return null;

  const handleError = () => {
    const remaining = validUrls.filter((u) => u !== current);
    setValidUrls(remaining);
    setIdx((i) => Math.min(i, Math.max(0, remaining.length - 1)));
  };

  return (
    <>
      <section className="property-photo">
        <img
          src={current}
          alt={alt || "매물 사진"}
          referrerPolicy="no-referrer"
          onError={handleError}
          onClick={() => setLightbox(true)}
          style={{ cursor: "zoom-in" }}
        />
        {hasMultiple && (
          <>
            <button
              type="button"
              className="photo-gallery-nav prev"
              onClick={(e) => {
                e.stopPropagation();
                prev();
              }}
              aria-label="이전 사진"
            >
              ‹
            </button>
            <button
              type="button"
              className="photo-gallery-nav next"
              onClick={(e) => {
                e.stopPropagation();
                next();
              }}
              aria-label="다음 사진"
            >
              ›
            </button>
            <span className="photo-gallery-count">
              {idx + 1} / {total}
            </span>
          </>
        )}
      </section>

      {lightbox && (
        <div
          className="lightbox-backdrop"
          onClick={() => setLightbox(false)}
          role="dialog"
          aria-modal="true"
          aria-label="사진 확대 보기"
        >
          <button
            type="button"
            className="lightbox-close"
            onClick={() => setLightbox(false)}
            aria-label="닫기"
          >
            ×
          </button>
          <img
            src={_toFullSize(current)}
            alt={alt || "매물 사진 확대"}
            referrerPolicy="no-referrer"
            className="lightbox-img"
            onClick={(e) => e.stopPropagation()}
            onError={(e) => {
              // CLG 실패 시 ELGM 원본으로 폴백
              (e.currentTarget as HTMLImageElement).src = current;
            }}
          />
          {hasMultiple && (
            <>
              <button
                type="button"
                className="lightbox-nav prev"
                onClick={(e) => {
                  e.stopPropagation();
                  prev();
                }}
                aria-label="이전 사진"
              >
                ‹
              </button>
              <button
                type="button"
                className="lightbox-nav next"
                onClick={(e) => {
                  e.stopPropagation();
                  next();
                }}
                aria-label="다음 사진"
              >
                ›
              </button>
              <span className="lightbox-count">
                {idx + 1} / {total}
              </span>
            </>
          )}
        </div>
      )}
    </>
  );
}
