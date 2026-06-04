import { useMemo, useState } from "react";
import { formatPrice, type Property } from "../api";

/** 카테고리별 취득세율 — 한국 표준 (2025 기준).
 * - 주거 1주택: 1.1% (전용 85㎡↓ 농특세 면제 → 1.0% + 지방교육세 0.1%)
 * - 비주거(상가/오피스텔 업무용/토지): 4.6% (취득 4.0% + 농특세 0.2% + 지방교육세 0.4%)
 * - 농지: 3.4%. 공익지구 토지: 별도 — 본 시뮬은 표준만 제공.
 */
function acquisitionTaxRate(prop: Property): { rate: number; label: string } {
  const cat = `${prop.category ?? ""}${prop.title ?? ""}`;
  if (/도로|토지|전 \/|답 \/|과수원|임야|대지/.test(cat)) {
    return { rate: 0.046, label: "토지/도로 4.6%" };
  }
  if (/오피스텔|용도복합|상가/.test(cat)) {
    return { rate: 0.046, label: "오피스텔/상가 4.6%" };
  }
  // 주거 — 면적별
  const area = prop.area_build_m2 ?? 0;
  if (area > 0 && area <= 85) {
    return { rate: 0.011, label: "주거 ≤85㎡ 1.1%" };
  }
  return { rate: 0.013, label: "주거 >85㎡ 1.3%" };
}

/** 명도비 휴리스틱.
 * - 임차인 존재 + 대항력 의심: 평당 100만 원 (높음)
 * - 일반 거주: 평당 30만 원
 * - 빈집/지분/토지: 최소 50만 원
 */
function evictionCostEstimate(prop: Property): { amount: number; basis: string } {
  const cat = `${prop.category ?? ""}${prop.title ?? ""}`;
  const isLand = /도로|토지|전 \/|답 \/|과수원|임야|대지/.test(cat);
  const isShare = prop.share_yn === "Y" || prop.building_shared === true;
  if (isLand || isShare) {
    return { amount: 500_000, basis: "토지/지분 기본 50만" };
  }
  const pyeong = (prop.area_build_m2 ?? 0) / 3.3058;
  const hasTakeoverRisk =
    prop.rights_analysis?.flags?.some((f) => f.kind === "takeover_risk") ?? false;
  const perPyeong = hasTakeoverRisk ? 1_000_000 : 300_000;
  const base = Math.max(perPyeong * pyeong, 500_000);
  return {
    amount: Math.round(base),
    basis: hasTakeoverRisk
      ? `평당 100만 × ${pyeong.toFixed(1)}평 (인수 위험)`
      : `평당 30만 × ${pyeong.toFixed(1)}평`,
  };
}

export default function BidSimulator({ prop }: { prop: Property }) {
  const minBid = prop.min_price ?? 0;
  const defaultBid = prop.predicted_price_median ?? minBid;
  const [bidStr, setBidStr] = useState<string>(String(defaultBid));
  const [evictionOverride, setEvictionOverride] = useState<string>("");

  const bid = Math.max(0, Math.round(Number(bidStr) || 0));

  const taxInfo = acquisitionTaxRate(prop);
  const evictionEst = useMemo(() => evictionCostEstimate(prop), [prop]);

  const eviction = evictionOverride.trim()
    ? Math.max(0, Math.round(Number(evictionOverride) || 0))
    : evictionEst.amount;

  const deposit = Math.round(minBid * 0.1);  // 입찰 보증금은 최저가의 10%
  const balance = Math.max(0, bid - deposit);  // 잔금
  const tax = Math.round(bid * taxInfo.rate);
  const registration = Math.round(bid * 0.002);  // 등기비 ~0.2%
  const total = bid + tax + registration + eviction;

  const market = prop.market_median_price ?? 0;
  const marketDiff = market > 0 ? ((total - market) / market) * 100 : null;
  const marketDiffLabel =
    marketDiff == null
      ? null
      : marketDiff > 5
      ? `시세보다 ${marketDiff.toFixed(1)}% 비쌈`
      : marketDiff < -5
      ? `시세보다 ${Math.abs(marketDiff).toFixed(1)}% 저렴`
      : `시세 ±5% 이내 (적정)`;

  const bidVsMin = minBid > 0 ? ((bid - minBid) / minBid) * 100 : 0;
  const belowMin = bid < minBid;

  return (
    <section className="detail-section bid-simulator">
      <h3 className="section-title">모의입찰 시뮬레이션</h3>
      <p className="section-hint">
        입찰가를 넣으면 보증금·취득세·명도비·등기비를 자동 계산해 총 매수 비용을 추정합니다. 실제 비용은 매물·법무사·세무사 조건에 따라 달라질 수 있습니다.
      </p>

      <div className="bid-sim-inputs">
        <label>
          <span>입찰가 (원)</span>
          <input
            type="text"
            inputMode="numeric"
            value={bidStr ? Number(bidStr).toLocaleString("ko-KR") : ""}
            onChange={(e) => setBidStr(e.target.value.replace(/[^\d]/g, ""))}
          />
          {minBid > 0 && (
            <small className={belowMin ? "bid-warn" : "bid-info"}>
              {belowMin
                ? `⚠️ 최저가 ${formatPrice(minBid)} 미만 — 입찰 무효`
                : `최저가 대비 ${bidVsMin >= 0 ? "+" : ""}${bidVsMin.toFixed(1)}%`}
            </small>
          )}
        </label>
        <label>
          <span>명도비 (override, 옵션)</span>
          <input
            type="text"
            inputMode="numeric"
            placeholder={evictionEst.amount.toLocaleString("ko-KR")}
            value={
              evictionOverride
                ? Number(evictionOverride).toLocaleString("ko-KR")
                : ""
            }
            onChange={(e) =>
              setEvictionOverride(e.target.value.replace(/[^\d]/g, ""))
            }
          />
          <small className="bid-info">기본: {evictionEst.basis}</small>
        </label>
      </div>

      <dl className="info-table bid-sim-result">
        <div className="info-row">
          <dt>입찰 보증금 (최저가 10%)</dt>
          <dd>{formatPrice(deposit)}</dd>
        </div>
        <div className="info-row">
          <dt>잔금 (낙찰 시)</dt>
          <dd>{formatPrice(balance)}</dd>
        </div>
        <div className="info-row">
          <dt>취득세 등 ({taxInfo.label})</dt>
          <dd>{formatPrice(tax)}</dd>
        </div>
        <div className="info-row">
          <dt>등기비 (0.2%)</dt>
          <dd>{formatPrice(registration)}</dd>
        </div>
        <div className="info-row">
          <dt>명도비 (추정)</dt>
          <dd>{formatPrice(eviction)}</dd>
        </div>
        <div className="info-row bid-sim-total">
          <dt>총 매수 비용</dt>
          <dd>
            <strong>{formatPrice(total)}</strong>
            {marketDiffLabel && (
              <small
                className={
                  marketDiff! > 5
                    ? "bid-warn"
                    : marketDiff! < -5
                    ? "bid-good"
                    : "bid-info"
                }
              >
                {marketDiffLabel}
              </small>
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}
