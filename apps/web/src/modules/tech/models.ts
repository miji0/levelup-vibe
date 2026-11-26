export type Source = {
  id: string;
  name: string;
  inputUrl: string;
  collectionUrl: string;
  collectorType: string;
  status: "active" | "paused" | "deleted";
  enabled: boolean;
  initializationState: string;
  version: number;
  lastAttemptAt: string | null;
  lastSuccessAt: string | null;
  lastUsableAt: string | null;
  lastResult: string | null;
  openIssueCount: number;
  lastError: { code: string; message: string } | null;
};
export type Option = {
  name: string;
  collectionUrl: string;
  collectorType: string;
  existingSourceId?: string;
};
export type ArticleState = {
  isRead: boolean;
  isSaved: boolean;
  isHidden: boolean;
  version: number;
};
export type Article = {
  id: string;
  title: string;
  originalUrl: string;
  publishedAt: string | null;
  publicationPrecision: string;
  firstSeenAt: string;
  intro: string | null;
  tags: string[];
  source: { id: string; name: string; status: string };
  state: ArticleState;
};
export type ArticlePage = {
  items: Article[];
  filteredCount: number | null;
  fullCount?: number | null;
  isPreview?: boolean;
  state?: string;
  reasonCode?: string | null;
};
export type Page<T> = {
  data: T;
  meta: { nextCursor: string | null; hasMore: boolean };
};
export function timestamp(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
export function kstToday(): string {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
export function sourceStatus(source: Source): string {
  if (!source.enabled) return "구독 꺼짐";
  if (source.initializationState === "pending") return "초기 수집 대기";
  if (source.initializationState === "running") return "초기 수집 중";
  if (source.lastResult === "failed") return "수집 실패";
  if (source.openIssueCount || source.lastResult === "partial")
    return "일부 항목 확인 필요";
  return source.lastSuccessAt ? "정상 수집" : "수집 대기";
}
