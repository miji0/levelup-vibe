"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, apiPage } from "@/core/api";
import {
  kstToday,
  sourceStatus,
  timestamp,
  type Source,
  type Page,
} from "@/modules/tech/models";
type Delivery = {
  id: string;
  kind: string;
  state: string;
  subject: string;
  preparedAt: string;
  acceptedAt: string | null;
  lastErrorCode: string | null;
};
type Detail = Delivery & {
  fromAddress: string;
  toAddress: string;
  mimeMessageId: string;
  providerMessageId: string | null;
  submittedAt: string | null;
  verificationOutcome: string | null;
};
type Brief = {
  date: string;
  state: string;
  fullCount: number | null;
  scheduledAt: string;
  startDeadlineAt: string;
};
const labels: Record<string, string> = {
  prepared: "발송 준비",
  sending: "Gmail 요청 중",
  accepted: "Gmail 접수",
  unknown: "접수 여부 확인 필요",
  failed: "발송 실패",
  cancelled: "발송 취소",
  missed: "시작 누락",
  not_scheduled: "예약 없음",
  scheduled: "예약",
  delayed: "시작 지연",
  empty: "대상 글 없음",
  paused: "알림 중지",
  ready: "브리핑 확정",
};
export default function StatusPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [kind, setKind] = useState("digest");
  const [page, setPage] = useState<Page<{ items: Delivery[] }> | null>(null);
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const end = kstToday();
        const from = new Date(`${end}T00:00:00+09:00`);
        from.setUTCDate(from.getUTCDate() - 6);
        const start = new Intl.DateTimeFormat("sv-SE", {
          timeZone: "Asia/Seoul",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
        }).format(from);
        const [s, d, b] = await Promise.all([
          api<{ sources: Source[] }>("/api/v1/tech/collection-status"),
          apiPage<{ items: Delivery[] }>(
            `/api/v1/tech/deliveries?kind=${kind}`,
          ),
          apiPage<{ items: Brief[] }>(
            `/api/v1/tech/digests?dateFrom=${start}&dateTo=${end}`,
          ),
        ]);
        if (active) {
          setSources(s.sources);
          setPage(d);
          setBriefs(b.data.items);
          setError("");
        }
      } catch (err) {
        if (active)
          setError(
            err instanceof Error ? err.message : "상태를 불러오지 못했습니다.",
          );
      }
    }
    void load();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [kind]);
  async function more() {
    if (!page?.meta.nextCursor || busy) return;
    setBusy(true);
    try {
      const next = await apiPage<{ items: Delivery[] }>(
        `/api/v1/tech/deliveries?kind=${kind}&cursor=${encodeURIComponent(page.meta.nextCursor)}`,
      );
      setPage({
        ...next,
        data: { items: [...page.data.items, ...next.data.items] },
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "다음 기록을 불러오지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function open(id: string) {
    setDetail(null);
    try {
      setDetail(await api<Detail>(`/api/v1/tech/deliveries/${id}`));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "기록을 불러오지 못했습니다.",
      );
    }
  }
  const latest =
    sources
      .map((s) => s.lastAttemptAt)
      .filter((v): v is string => !!v)
      .sort()
      .at(-1) ?? null;
  return (
    <>
      <div className="page-heading">
        <h1>수집·발송 상태</h1>
        <p>
          출처별 수집 결과와 Gmail 접수 기록을 확인합니다. 접수는 받은편지함
          도착을 보장하지 않습니다.
        </p>
      </div>
      {!page && !error && <p role="status">상태를 불러오는 중…</p>}
      {error && (
        <p className="error-callout" role="alert">
          {error}
        </p>
      )}
      <div className="status-summary">
        <section>
          <small>마지막 수집 시도</small>
          <p>{timestamp(latest)}</p>
        </section>
        <section>
          <small>수집 일정 · 한국 시간</small>
          <p>매시 · 07:30 최종 수집</p>
        </section>
        <section>
          <small>브리핑 시작 목표</small>
          <p>매일 08:00 · 시작 마감 08:20</p>
        </section>
      </div>
      <section className="feature-section">
        <h2>출처별 수집 상태</h2>
        {sources.length === 0 ? (
          <p className="feature-empty">
            등록된 출처가 없습니다.{" "}
            <Link href="/tech/subscriptions">구독 추가</Link>
          </p>
        ) : (
          <div className="record-list">
            {sources.map((s) => (
              <article key={s.id}>
                <strong>{s.name}</strong>
                <span className="badge neutral">{sourceStatus(s)}</span>
                <span>마지막 성공 {timestamp(s.lastSuccessAt)}</span>
                {s.lastError && (
                  <small className="article-error">
                    {s.lastError.message} ({s.lastError.code})
                  </small>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
      <section className="feature-section">
        <h2>최근 7일 브리핑</h2>
        <div className="record-list">
          {briefs.map((b) => (
            <article key={b.date}>
              <Link href={`/tech?date=${b.date}`}>{b.date}</Link>
              <span>{labels[b.state] ?? b.state}</span>
              <span>
                {b.fullCount === null ? "전체 수 미확정" : `${b.fullCount}개`}
              </span>
            </article>
          ))}
        </div>
      </section>
      <section className="feature-section">
        <h2>이메일 발송 기록</h2>
        <div className="feature-actions">
          <button
            className={kind === "digest" ? "primary" : "secondary"}
            onClick={() => setKind("digest")}
          >
            아침 브리핑
          </button>
          <button
            className={kind === "test" ? "primary" : "secondary"}
            onClick={() => setKind("test")}
          >
            테스트 메일
          </button>
        </div>
        {page?.data.items.length === 0 && (
          <p className="feature-empty">발송 기록이 없습니다.</p>
        )}
        <div className="record-list">
          {page?.data.items.map((d) => (
            <article key={d.id}>
              <button className="text-button" onClick={() => void open(d.id)}>
                {d.subject}
              </button>
              <span>{labels[d.state] ?? d.state}</span>
              <span>{timestamp(d.preparedAt)}</span>
              {d.lastErrorCode && <small>{d.lastErrorCode}</small>}
            </article>
          ))}
        </div>
        {page?.meta.hasMore && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => void more()}
          >
            발송 기록 더 보기
          </button>
        )}
      </section>
      {detail && (
        <section
          className="feature-section settings-panel"
          aria-label="발송 상세"
        >
          <div className="feature-actions">
            <h2>발송 상세</h2>
            <button className="text-button" onClick={() => setDetail(null)}>
              닫기
            </button>
          </div>
          <dl className="delivery-detail">
            <dt>상태</dt>
            <dd>{labels[detail.state] ?? detail.state}</dd>
            <dt>제목</dt>
            <dd>{detail.subject}</dd>
            <dt>발신·수신</dt>
            <dd>
              {detail.fromAddress} → {detail.toAddress}
            </dd>
            <dt>준비 / 요청 / 접수</dt>
            <dd>
              {timestamp(detail.preparedAt)} / {timestamp(detail.submittedAt)} /{" "}
              {timestamp(detail.acceptedAt)}
            </dd>
            <dt>Gmail 식별자</dt>
            <dd>{detail.providerMessageId ?? "확인되지 않음"}</dd>
            <dt>MIME Message-ID</dt>
            <dd>{detail.mimeMessageId}</dd>
            <dt>오류</dt>
            <dd>{detail.lastErrorCode ?? "없음"}</dd>
          </dl>
          {detail.state === "unknown" && (
            <p className="error-callout">
              중복 발송을 막기 위해 자동 재전송을 보류합니다. Gmail
              보낸편지함에서 Message-ID를 직접 대조한 뒤 운영 절차 OP-01로 확인
              결과를 기록하세요.
            </p>
          )}
        </section>
      )}
    </>
  );
}
