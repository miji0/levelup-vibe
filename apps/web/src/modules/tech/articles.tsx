"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, apiPage } from "@/core/api";
import { Icon } from "@/core/icon";
import { useSession } from "@/core/shell";
import { handoffReport } from "@/modules/reports/handoff";
import {
  kstToday,
  timestamp,
  type Article,
  type ArticlePage,
  type ArticleState,
  type Page,
  type Source,
} from "./models";

const states: Record<string, string> = {
  scheduled: "오늘의 브리핑 미리보기",
  delayed: "발송 준비 지연 · 아직 확정되지 않았습니다",
  missed: "작업 시작 누락 · 유효한 미발송 글은 다음 정상 아침에 합칩니다",
  not_scheduled: "이 날짜에는 브리핑이 예약되지 않았습니다",
  empty: "이 날짜에 알림 대상 글이 없습니다",
  paused: "알림 중지 · 브리핑을 확정했지만 메일은 보내지 않았습니다",
  ready: "브리핑 확정 · 발송 준비",
  sending: "Gmail에 요청 중입니다",
  accepted: "Gmail 접수 · 브리핑 확정",
  unknown: "Gmail 접수 여부 확인 필요 · 자동 재전송을 보류합니다",
  failed: "미발송 · 상태 화면에서 원인을 확인해주세요",
};
export function ArticlesScreen({ saved = false }: { saved?: boolean }) {
  const query = useSearchParams();
  const router = useRouter();
  const session = useSession();
  const view = saved
    ? "saved"
    : query.get("view") === "all"
      ? "all"
      : query.get("view") === "saved"
        ? "saved"
        : "today";
  const day = query.get("date") || kstToday();
  const [sources, setSources] = useState<Source[]>([]);
  const [source, setSource] = useState("");
  const [read, setRead] = useState("all");
  const [hidden, setHidden] = useState("exclude");
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState<Page<ArticlePage> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  const params = new URLSearchParams({ q: search, read, hidden });
  if (source) params.set("sourceId", source);
  if (view === "saved") params.set("view", "saved");
  const path =
    (view === "today"
      ? `/api/v1/tech/digests/${encodeURIComponent(day)}`
      : "/api/v1/tech/articles") +
    "?" +
    params.toString();
  useEffect(() => {
    let active = true;
    api<{ items: Source[] }>("/api/v1/tech/sources")
      .then((data) => {
        if (active) setSources(data.items);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    generation.current += 1;
    queueMicrotask(() => {
      if (active) setPage(null);
    });
    apiPage<ArticlePage>(path)
      .then((data) => {
        if (active) {
          setPage(data);
          setError("");
        }
      })
      .catch((err) => {
        if (active) {
          setPage(null);
          setError(
            err instanceof Error ? err.message : "글을 불러오지 못했습니다.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [path, refresh]);
  async function more() {
    if (!page?.meta.nextCursor || busy) return;
    setBusy("more");
    const scope = generation.current;
    try {
      const next = await apiPage<ArticlePage>(
        path + "&cursor=" + encodeURIComponent(page.meta.nextCursor),
      );
      if (scope !== generation.current) return;
      setPage({
        ...next,
        data: { ...next.data, items: [...page.data.items, ...next.data.items] },
      });
      setError("");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "다음 글을 불러오지 못했습니다.",
      );
    } finally {
      setBusy("");
    }
  }
  async function change(article: Article, updates: Partial<ArticleState>) {
    if (!session || busy) return;
    setBusy(article.id);
    setError("");
    try {
      const state = await api<ArticleState>(
        `/api/v1/tech/articles/${article.id}/state`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": session.csrfToken,
            "If-Match": `"${article.state.version}"`,
          },
          body: JSON.stringify(updates),
        },
      );
      setPage((previous) => {
        if (!previous) return previous;
        const items = previous.data.items
          .map((item) => (item.id === article.id ? { ...item, state } : item))
          .filter(
            (item) =>
              (hidden !== "exclude" || !item.state.isHidden) &&
              (hidden !== "only" || item.state.isHidden) &&
              (view !== "saved" || item.state.isSaved) &&
              (read === "all" || item.state.isRead === (read === "read")),
          );
        const removed = previous.data.items.length - items.length;
        return {
          ...previous,
          data: {
            ...previous.data,
            items,
            filteredCount:
              previous.data.filteredCount === null
                ? null
                : previous.data.filteredCount - removed,
          },
        };
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "상태를 변경하지 못했습니다.",
      );
    } finally {
      setBusy("");
    }
  }
  return (
    <>
      <div className="page-heading">
        <h1>{view === "saved" ? "저장한 글" : "기술블로그"}</h1>
        <p>
          구독한 출처의 새 글을 날짜별 브리핑으로 모읍니다. 채용·행사·기업
          소식도 같은 목록에 들어갑니다.
        </p>
      </div>
      <div className="tech-toolbar">
        <nav className="tech-tabs" aria-label="글 보기">
          {[
            ["today", "오늘의 글"],
            ["all", "전체 글"],
            ["saved", "저장한 글"],
          ].map(([value, label]) => (
            <Link
              key={value}
              href={
                value === "today"
                  ? "/tech"
                  : value === "saved"
                    ? "/tech/saved"
                    : `/tech?view=${value}`
              }
              aria-current={view === value ? "page" : undefined}
            >
              {label}
            </Link>
          ))}
        </nav>
        <Link className="secondary" href="/tech/subscriptions">
          <Icon name="rss" />
          구독 설정
        </Link>
      </div>
      {view === "today" && (
        <>
          <label className="brief-date">
            브리핑 날짜
            <input
              type="date"
              value={day}
              max={kstToday()}
              onChange={(e) =>
                e.target.value && router.replace(`/tech?date=${e.target.value}`)
              }
            />
          </label>
          <div className="brief-banner" role="status">
            <p>
              {page
                ? (states[page.data.state ?? ""] ?? "브리핑 상태 확인")
                : "브리핑 상태를 불러오는 중…"}
            </p>
            <p className="caption">
              {page?.data.fullCount == null
                ? "대상을 아직 확정하지 못했습니다."
                : `${page.data.isPreview ? "미리보기" : "전체"} ${page.data.fullCount}개 · 메일에는 최신 20개까지 표시합니다.`}{" "}
              Gmail 접수는 받은편지함 도착을 뜻하지 않습니다.
            </p>
          </div>
        </>
      )}
      <form
        className="feature-filters"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(input);
        }}
      >
        <label>
          제목 검색
          <input
            placeholder="제목으로 찾기"
            maxLength={200}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </label>
        <button className="secondary">
          <Icon name="search" />
          검색
        </button>
        <label>
          출처
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">출처 전체</option>
            {[
              ...new Map(
                [
                  ...sources,
                  ...(page?.data.items.map((article) => article.source) ?? []),
                ].map((item) => [item.id, item]),
              ).values(),
            ].map((item) => (
              <option value={item.id} key={item.id}>
                {item.name}
                {item.status === "deleted" ? " (삭제된 출처)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          읽음 상태
          <select value={read} onChange={(e) => setRead(e.target.value)}>
            <option value="all">읽음 상태 전체</option>
            <option value="unread">안 읽음</option>
            <option value="read">읽음</option>
          </select>
        </label>
        <label>
          숨긴 글
          <select value={hidden} onChange={(e) => setHidden(e.target.value)}>
            <option value="exclude">숨긴 글 제외</option>
            <option value="include">모두 보기</option>
            <option value="only">숨긴 글만</option>
          </select>
        </label>
        <span className="feature-count">
          {page?.data.filteredCount == null
            ? "대상 미확정"
            : `${page.data.filteredCount}개`}
        </span>
      </form>
      <p className="caption">
        목록에서만 숨깁니다. 아침 메일에는 포함될 수 있습니다. 원문·리포트
        분석을 열어도 읽음으로 바뀌지 않습니다.
      </p>
      {error && (
        <div className="error-callout" role="alert">
          {error}
          <button
            className="secondary"
            onClick={() => setRefresh((n) => n + 1)}
          >
            다시 조회
          </button>
        </div>
      )}
      {!page && !error ? (
        <p role="status" className="feature-empty">
          글을 불러오는 중…
        </p>
      ) : page && !page.data.items.length ? (
        <div className="feature-empty">
          <p>
            {view === "today" && page.data.fullCount === null
              ? "이 날짜의 대상이 확정되지 않았습니다."
              : search || source || read !== "all" || hidden !== "exclude"
                ? "조건에 맞는 글이 없습니다."
                : view === "saved"
                  ? "글 목록에서 저장을 누르면 여기에 모입니다."
                  : "아직 모은 글이 없습니다."}
          </p>
          <button
            className="secondary"
            onClick={() => {
              setInput("");
              setSearch("");
              setSource("");
              setRead("all");
              setHidden("exclude");
            }}
          >
            필터 초기화
          </button>
        </div>
      ) : (
        <div className="article-list">
          {page?.data.items.map((article) => (
            <article
              key={article.id}
              className={`article-card ${article.state.isRead ? "article-read" : ""}`}
            >
              <span className="source-mark" aria-hidden="true">
                {article.source.name.slice(0, 2)}
              </span>
              <div className="article-content">
                <div className="article-meta">
                  <span>{article.source.name}</span>
                  <span>
                    {timestamp(article.publishedAt || article.firstSeenAt)}
                    {["invalid", "missing"].includes(
                      article.publicationPrecision,
                    )
                      ? " · 발견 시각"
                      : ""}
                  </span>
                  {article.source.status === "deleted" && (
                    <span className="badge neutral">삭제된 출처</span>
                  )}
                  {article.state.isRead && (
                    <span className="badge neutral">읽음</span>
                  )}
                </div>
                <h2>{article.title}</h2>
                {article.intro && <p>{article.intro}</p>}
                <div className="article-tags">
                  {article.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
                <div className="article-actions">
                  <a
                    href={article.originalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Icon name="external" />
                    원문 열기
                  </a>
                  <button
                    aria-pressed={article.state.isRead}
                    disabled={!!busy}
                    onClick={() =>
                      change(article, { isRead: !article.state.isRead })
                    }
                  >
                    <Icon name="success" />
                    {article.state.isRead ? "읽음 해제" : "읽음 표시"}
                  </button>
                  <button
                    aria-pressed={article.state.isSaved}
                    disabled={!!busy}
                    onClick={() =>
                      change(article, { isSaved: !article.state.isSaved })
                    }
                  >
                    <Icon name="bookmark" />
                    {article.state.isSaved ? "저장됨" : "저장"}
                  </button>
                  <button
                    disabled={!!busy}
                    onClick={() =>
                      change(article, { isHidden: !article.state.isHidden })
                    }
                  >
                    <Icon name="eye" />
                    {article.state.isHidden ? "목록에 복원" : "목록에서 숨기기"}
                  </button>
                  <Link
                    href="/reports"
                    onClick={() => handoffReport(article.originalUrl)}
                  >
                    <Icon name="report" />
                    리포트 분석
                  </Link>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
      {page?.meta.hasMore && (
        <div className="more-articles">
          <button className="secondary" disabled={!!busy} onClick={more}>
            {busy === "more" ? "불러오는 중…" : "더 보기"}
          </button>
          <small>
            전체 {page.data.filteredCount}개 중 {page.data.items.length}개 표시
          </small>
        </div>
      )}
    </>
  );
}
