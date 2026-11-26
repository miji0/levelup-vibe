"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/core/api";
import { Icon } from "@/core/icon";
import { useSession } from "@/core/shell";
import { sourceStatus, timestamp, type Option, type Source } from "./models";

const suggestions = [
  ["NAVER D2", "https://d2.naver.com/d2.atom"],
  ["카카오테크", "https://tech.kakao.com/feed/"],
  ["우아한형제들", "https://techblog.woowahan.com/feed/"],
  ["삼성SDS", "https://www.samsungsds.com/kr/insights/index.html"],
  ["SK플래닛 TECH TOPIC", "https://techtopic.skplanet.com/"],
];
export function SourcesScreen() {
  const session = useSession();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [url, setUrl] = useState("");
  const [options, setOptions] = useState<Option[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Source | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  async function load() {
    const data = await api<{ items: Source[] }>("/api/v1/tech/sources");
    setSources(data.items);
  }
  useEffect(() => {
    let active = true;
    api<{ items: Source[] }>("/api/v1/tech/sources")
      .then((data) => {
        if (active) setSources(data.items);
      })
      .catch(() => {
        if (active) setError("출처를 불러오지 못했습니다. 다시 시도해주세요.");
      });
    return () => {
      active = false;
    };
  }, []);
  const polling = sources?.some(
    (s) => s.enabled && ["pending", "running"].includes(s.initializationState),
  );
  useEffect(() => {
    if (!polling) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible")
        load().catch(() => setError("수집 상태를 확인하지 못했습니다."));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [polling]);
  useEffect(() => {
    if (pendingDelete) dialog.current?.showModal();
  }, [pendingDelete]);
  function changeInput(value: string) {
    setUrl(value);
    setOptions([]);
    setSelected("");
    setNotice("");
  }
  async function resolve(event: React.FormEvent) {
    event.preventDefault();
    if (!session || busy) return;
    setBusy("resolve");
    setError("");
    setOptions([]);
    setSelected("");
    try {
      const data = await api<{
        options: Option[];
        requiresSelection: boolean;
        warnings: string[];
      }>("/api/v1/tech/sources/resolve", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": session.csrfToken,
        },
        body: JSON.stringify({ inputUrl: url }),
      });
      setOptions(data.options);
      if (!data.requiresSelection)
        setSelected(data.options[0]?.collectionUrl ?? "");
      setNotice(
        data.warnings.length
          ? "일부 피드 후보를 확인하지 못했습니다. 확인된 후보에서 선택해주세요."
          : "수집할 피드를 확인했습니다.",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "연결을 확인하지 못했습니다.",
      );
    } finally {
      setBusy("");
    }
  }
  async function add() {
    if (!session || !selected || busy) return;
    setBusy("add");
    setError("");
    try {
      await api("/api/v1/tech/sources", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": session.csrfToken,
        },
        body: JSON.stringify({ inputUrl: url, collectionUrl: selected }),
      });
      setOptions([]);
      setSelected("");
      setUrl("");
      setNotice(
        "출처를 추가했습니다. 초기 수집이 끝날 때까지 대기 상태로 표시됩니다.",
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "추가하지 못했습니다.");
    } finally {
      setBusy("");
    }
  }
  async function mutate(source: Source, remove: boolean) {
    if (!session || busy) return;
    setBusy(source.id);
    setError("");
    try {
      await api(`/api/v1/tech/sources/${source.id}`, {
        method: remove ? "DELETE" : "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": session.csrfToken,
          "If-Match": `"${source.version}"`,
        },
        ...(remove
          ? {}
          : { body: JSON.stringify({ enabled: !source.enabled }) }),
      });
      setNotice(
        remove
          ? "출처를 삭제했습니다. 기존 글과 기록은 유지됩니다."
          : "구독 상태를 변경했습니다.",
      );
      if (remove) dialog.current?.close();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "변경하지 못했습니다.");
      if (err instanceof ApiError && err.status === 412) await load();
    } finally {
      setBusy("");
    }
  }
  return (
    <>
      <div className="page-heading">
        <h1>구독 설정</h1>
        <p>
          구독한 공개 피드의 새 글을 모읍니다. 채용·행사·기업 소식·홍보도
          포함하며 유형으로 자동 제외하지 않습니다.
        </p>
      </div>
      <section className="feature-section">
        <h2>출처 추가</h2>
        <p className="muted">
          블로그 주소나 RSS·Atom 주소를 넣고 연결을 확인하세요. 입력만으로는
          외부에 접속하지 않습니다.
        </p>
        <form onSubmit={resolve}>
          <label htmlFor="source-url">출처 URL</label>
          <div className="input-action">
            <input
              id="source-url"
              type="url"
              value={url}
              onChange={(e) => changeInput(e.target.value)}
              required
              placeholder="https://example.com/feed.xml"
              disabled={!!busy}
            />
            <button className="secondary" disabled={!!busy || !url}>
              <Icon name="refresh" />
              {busy === "resolve" ? "확인 중…" : "연결 확인"}
            </button>
          </div>
        </form>
        <p className="caption">
          공개 주소만 추가할 수 있습니다. 로그인이 필요한 피드와 내부 주소는
          지원하지 않습니다.
        </p>
        <div className="suggestions">
          <span>기본 후보</span>
          {suggestions.map(([name, input]) => (
            <button
              type="button"
              className="badge neutral"
              key={name}
              onClick={() => changeInput(input)}
              disabled={!!busy}
            >
              {name}
            </button>
          ))}
        </div>
        {!!options.length && (
          <div className="feed-candidates">
            <p className="accent">피드 {options.length}개 발견</p>
            <p>실제로 수집할 피드를 하나 고르세요.</p>
            <fieldset aria-label="수집할 피드">
              {options.map((option) => (
                <label
                  className={
                    selected === option.collectionUrl
                      ? "feed-option selected-option"
                      : "feed-option"
                  }
                  key={option.collectionUrl}
                >
                  <input
                    type="radio"
                    name="feed"
                    checked={selected === option.collectionUrl}
                    onChange={() => setSelected(option.collectionUrl)}
                    disabled={!!busy}
                  />
                  <span>
                    <strong>{option.name || "공개 피드"}</strong>
                    <small>{option.collectionUrl}</small>
                    {option.existingSourceId && <small>이미 등록한 출처</small>}
                  </span>
                  <span className="badge neutral">
                    {option.collectorType.toUpperCase()}
                  </span>
                </label>
              ))}
            </fieldset>
            <div className="input-action">
              <button
                className="primary"
                onClick={add}
                disabled={
                  !!busy ||
                  !selected ||
                  options.some(
                    (o) => o.collectionUrl === selected && o.existingSourceId,
                  )
                }
              >
                <Icon name="plus" />
                {busy === "add" ? "추가 중…" : "추가"}
              </button>
              <small>
                현재 글은 과거 글로 기록하고 알림을 보내지 않습니다.
              </small>
            </div>
          </div>
        )}
      </section>
      {error && (
        <div role="alert" className="error-callout">
          {error}
          <button
            className="secondary"
            onClick={() =>
              load()
                .then(() => setError(""))
                .catch(() => setError("출처를 불러오지 못했습니다."))
            }
          >
            다시 조회
          </button>
        </div>
      )}
      {notice && (
        <p role="status" className="status-message">
          {notice}
        </p>
      )}
      <section className="feature-section">
        <h2>등록한 출처 {sources === null ? "" : `${sources.length}개`}</h2>
        <p className="muted">
          구독을 끄면 이 출처의 미요청 대기 알림을 중단합니다. 다시 켜도 이전
          대기는 보내지 않습니다. 기존 글·읽음·저장은 유지됩니다.
        </p>
        {sources === null ? (
          <p role="status">출처를 불러오는 중…</p>
        ) : !sources.length ? (
          <p className="feature-empty">
            아직 등록한 출처가 없습니다. 위에서 연결을 확인하고 추가하세요.
          </p>
        ) : (
          <div className="sources-table">
            <div className="source-row source-table-head">
              <span>구독</span>
              <span>출처</span>
              <span>마지막 성공</span>
              <span>수집 상태</span>
              <span />
            </div>
            {sources.map((source) => (
              <div className="source-row" key={source.id}>
                <button
                  role="switch"
                  aria-label={`${source.name} 구독`}
                  aria-checked={source.enabled}
                  className="switch"
                  disabled={!!busy}
                  onClick={() => mutate(source, false)}
                >
                  <span />
                </button>
                <div>
                  <strong>{source.name}</strong>
                  <small className="url-text">{source.collectionUrl}</small>
                </div>
                <span className="source-date">
                  {timestamp(source.lastSuccessAt)}
                </span>
                <div>
                  <span
                    className={`badge ${!source.enabled ? "neutral" : source.lastResult === "failed" ? "error" : source.lastResult === "partial" ? "warning" : source.lastSuccessAt ? "success" : "neutral"}`}
                  >
                    {sourceStatus(source)}
                  </span>
                  {source.lastError && (
                    <small>{source.lastError.message}</small>
                  )}
                </div>
                <button
                  className="danger-button"
                  disabled={!!busy}
                  onClick={() => setPendingDelete(source)}
                  aria-label={`${source.name} 삭제`}
                >
                  <Icon name="trash" />
                  삭제
                </button>
              </div>
            ))}
          </div>
        )}
        <Link className="text-link" href="/tech/status">
          수집·발송 상태 보기
        </Link>
      </section>
      <dialog
        className="confirm-dialog"
        ref={dialog}
        onClose={() => setPendingDelete(null)}
      >
        <h2>{pendingDelete?.name}을 삭제할까요?</h2>
        <p>
          이후 수집과 아직 요청하지 않은 알림을 중단합니다. 기존
          글·읽음·저장·이미 발송한 기록은 유지됩니다. Gmail에 이미 요청한 메일은
          취소되지 않을 수 있습니다.
        </p>
        <div className="dialog-actions">
          <button
            className="secondary"
            onClick={() => dialog.current?.close()}
            disabled={!!busy}
          >
            취소
          </button>
          <button
            className="danger-button"
            onClick={() => pendingDelete && mutate(pendingDelete, true)}
            disabled={!!busy}
          >
            {busy ? "처리 중…" : "출처 삭제"}
          </button>
        </div>
      </dialog>
    </>
  );
}
