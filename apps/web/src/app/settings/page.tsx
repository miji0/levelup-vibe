"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/core/api";
import { Icon } from "@/core/icon";
import { GmailBadge, useSession, useSettings } from "@/core/shell";
import { ThemeChoices } from "@/core/theme";
export default function SettingsPage() {
  const session = useSession();
  const { settings, error, refresh } = useSettings();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [job, setJob] = useState<string | null>(null);
  const testKey = useRef<string | null>(null);
  const confirm = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const result = new URL(window.location.href).searchParams.get("gmail");
    if (!result) return;
    queueMicrotask(() => {
      if (result === "connected") setNotice("Gmail 발송 권한을 연결했습니다.");
      else
        setActionError(
          "Gmail 권한을 연결하지 못했습니다. 같은 계정과 발송 권한을 확인한 뒤 다시 시도하세요. 기존 연결은 유지됩니다.",
        );
    });
    window.history.replaceState(null, "", "/settings");
  }, []);
  useEffect(() => {
    if (!job) return;
    let active = true;
    async function poll() {
      try {
        const value = await api<{ state: string; resultCode: string | null }>(
          `/api/v1/jobs/${job}`,
        );
        if (!active) return;
        if (value.state !== "queued" && value.state !== "running") {
          setJob(null);
          testKey.current = null;
          setNotice(
            value.state === "succeeded"
              ? "Gmail이 테스트 메일을 접수했습니다. 받은편지함에서 도착을 확인하세요."
              : `테스트 메일 상태: ${value.resultCode ?? value.state}. 발송 상태 화면을 확인하세요.`,
          );
        }
      } catch (err) {
        if (active)
          setActionError(
            err instanceof Error ? err.message : "상태를 조회하지 못했습니다.",
          );
      }
    }
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void poll();
    }, 4000);
    void poll();
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [job]);
  async function act(kind: "connect" | "disconnect" | "toggle" | "test") {
    if (!session || !settings || busy) return;
    setBusy(true);
    setNotice("");
    setActionError("");
    const headers: Record<string, string> = {
      "X-CSRF-Token": session.csrfToken,
      "Content-Type": "application/json",
    };
    try {
      if (kind === "connect") {
        const value = await api<{ authorizationUrl: string }>(
          "/api/v1/integrations/gmail/connect",
          { method: "POST", headers, body: "{}" },
        );
        const target = new URL(value.authorizationUrl);
        if (
          target.protocol !== "https:" ||
          target.hostname !== "accounts.google.com"
        )
          throw new Error("Google 인증 주소를 확인하지 못했습니다.");
        window.location.assign(target.href);
      } else if (kind === "disconnect") {
        headers["If-Match"] = `"${settings.gmail.version}"`;
        const value = await api<{ remoteRevocation: string }>(
          "/api/v1/integrations/gmail",
          { method: "DELETE", headers },
        );
        confirm.current?.close();
        await refresh();
        setNotice(
          value.remoteRevocation === "confirmed"
            ? "발송 연결을 해제했습니다."
            : "사이트의 발송 연결을 해제했습니다. Google 측 권한 해제는 확인되지 않았습니다. Google 계정의 연결 앱에서도 확인하세요.",
        );
      } else if (kind === "toggle") {
        headers["If-Match"] = `"${settings.version}"`;
        await api("/api/v1/settings", {
          method: "PATCH",
          headers,
          body: JSON.stringify({
            notificationsEnabled: !settings.notificationsEnabled,
          }),
        });
        await refresh();
        setNotice("이메일 알림 설정을 저장했습니다.");
      } else {
        testKey.current ??= crypto.randomUUID();
        headers["Idempotency-Key"] = testKey.current;
        const value = await api<{ jobId: string }>("/api/v1/tech/test-emails", {
          method: "POST",
          headers,
          body: "{}",
        });
        setJob(value.jobId);
        setNotice(
          "테스트 메일 발송을 예약했습니다. Gmail 접수 결과를 기다립니다.",
        );
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 412) await refresh();
      setActionError(
        err instanceof Error ? err.message : "요청을 완료하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <h1>설정</h1>
        <p>
          공통 설정, 연결한 계정, 기능별 설정을 나눠 관리합니다. 비밀번호나 AI
          키는 받지 않습니다.
        </p>
      </div>
      {notice && (
        <p className="status-message" role="status">
          {notice}
        </p>
      )}
      {actionError && (
        <p className="error-callout" role="alert">
          {actionError}
        </p>
      )}
      <section className="settings-section" aria-labelledby="general-title">
        <h2 id="general-title">일반 설정</h2>
        <div className="settings-panel">
          <div className="timezone-row">
            <Icon name="timezone" />
            <span>시간대</span>
            <span>Asia/Seoul (읽기 전용)</span>
          </div>
          <ThemeChoices />
        </div>
      </section>
      <section className="settings-section" aria-labelledby="account-title">
        <h2 id="account-title">연결 계정</h2>
        <p className="muted">
          로그인한 Google 계정으로 Gmail을 보내고 받습니다. 알림 중지와 발송
          연결 해제는 영향 범위가 다릅니다.
        </p>
        <div className="settings-panel">
          <div className="group-head">
            <span className="accent">
              <Icon name="mail" />
            </span>
            <h3>Gmail</h3>
            <span className="badge neutral">발송 전용</span>
            <GmailBadge settings={settings} />
          </div>
          <div className="account-field">
            <small>Google 로그인 계정 · 발신·수신 (변경 불가)</small>
            <p>{session?.owner.email}</p>
          </div>
          <div className="usage-row">
            <span className="muted">사용처</span>
            <span>기술블로그 알림·테스트 메일</span>
          </div>
          <p>받은편지함을 읽지 않습니다. 발송 권한만 사용합니다.</p>
          {error && (
            <p role="alert" className="error-callout">
              {error}
            </p>
          )}
          <div className="gmail-actions">
            <button
              className="secondary"
              disabled={busy || !settings}
              onClick={() => void act("connect")}
              aria-describedby="gmail-help"
            >
              <Icon name="refresh" />
              다시 연결
            </button>
            <button
              className="danger-button"
              disabled={
                busy || !settings || settings.gmail.state === "disconnected"
              }
              onClick={() => confirm.current?.showModal()}
              aria-describedby="gmail-help"
            >
              <Icon name="unlink" />
              발송 연결 해제
            </button>
          </div>
          <p className="caption" id="gmail-help">
            같은 Google 계정으로 발송 권한을 연결합니다. 발송 연결 해제는 로그인
            계정이나 기존 기록을 삭제하지 않습니다.
          </p>
        </div>
      </section>
      <section className="settings-section" aria-labelledby="features-title">
        <h2 id="features-title">기능별 설정</h2>
        <p className="muted">
          기술블로그 이메일 알림과 테스트 메일을 관리합니다.
        </p>
        <div className="settings-panel">
          <div className="group-head">
            <span className="accent">
              <Icon name="rss" />
            </span>
            <h3>기술블로그 · 모닝 테크</h3>
          </div>
          <p>
            매일 08:00(한국 시간)에 발송 작업을 시작합니다. 대상 글이 없는
            날에는 보내지 않습니다.
          </p>
          <div className="notification-row">
            <div>
              <p>기술블로그 이메일 알림</p>
              <small>
                메일만 일시 중지합니다. 다시 켜면 미발송 글을 다음 아침에 모아
                보냅니다.
              </small>
            </div>
            <button
              className="switch"
              role="switch"
              aria-label="기술블로그 이메일 알림"
              aria-checked={settings?.notificationsEnabled ?? false}
              disabled={
                busy ||
                !settings ||
                (!settings.notificationsEnabled &&
                  settings.gmail.state !== "connected")
              }
              onClick={() => void act("toggle")}
              aria-describedby="mail-help"
            >
              <span />
            </button>
          </div>
          <div className="test-email-row">
            <div>
              <p>테스트 메일</p>
              <small>
                알림을 꺼 둔 상태에서도 보낼 수 있습니다. 도착 여부는
                받은편지함에서 직접 확인하세요.
              </small>
            </div>
            <button
              className="secondary"
              disabled={busy || !!job || settings?.gmail.state !== "connected"}
              onClick={() => void act("test")}
              aria-describedby="mail-help"
            >
              <Icon name="send" />
              테스트 메일 보내기
            </button>
          </div>
          <p className="caption" id="mail-help">
            정기 메일은 매일 08:00 이후 시작하며, 테스트 메일도 Gmail 접수와
            실제 도착을 구분합니다. 발송 기능이 비활성화된 환경에서는 실패
            사유를 표시합니다.
          </p>
        </div>
      </section>
      <dialog
        ref={confirm}
        className="confirm-dialog"
        aria-labelledby="disconnect-title"
      >
        <h2 id="disconnect-title">Gmail 발송 연결을 해제할까요?</h2>
        <p>
          이후 메일 발송을 중단하고 저장된 발송 토큰을 삭제합니다. 로그인과
          글·발송 기록은 유지됩니다. 이미 Gmail에 요청한 메일은 취소할 수
          없습니다.
        </p>
        <div className="dialog-actions">
          <button
            className="secondary"
            onClick={() => confirm.current?.close()}
          >
            취소
          </button>
          <button
            className="danger-button"
            disabled={busy}
            onClick={() => void act("disconnect")}
          >
            발송 연결 해제
          </button>
        </div>
      </dialog>
    </>
  );
}
