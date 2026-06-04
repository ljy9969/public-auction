import { useEffect, useState } from "react";

/**
 * useState + sessionStorage 영속화.
 *
 * 상세 페이지로 갔다가 목록으로 돌아오면 컴포넌트가 remount 되면서 useState가
 * 초기값으로 리셋된다. 필터처럼 "다녀와도 유지"가 필요한 상태를 sessionStorage에
 * 저장해, 같은 브라우저 탭 세션 동안 값을 보존한다. (탭을 닫으면 초기화 — 기존
 * 활성 탭 기억(readStoredTab)과 동일한 범위.)
 */
export function usePersistentState<T>(
  key: string,
  initial: T,
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = sessionStorage.getItem(key);
      return raw != null ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* sessionStorage 차단 환경 무시 */
    }
  }, [key, value]);

  return [value, setValue];
}
