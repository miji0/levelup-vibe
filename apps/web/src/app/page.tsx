"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Home } from "@/core/api";
import { Icon } from "@/core/icon";
import { useSettings } from "@/core/shell";
export default function HomePage() {
  const { settings } = useSettings();
  const [home, setHome] = useState<Home | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Home>("/api/v1/home")
      .then((value) => {
        if (active) setHome(value);
      })
      .catch(() => {
        if (active)
          setError("홈 정보를 불러오지 못했습니다. 잠시 후 다시 확인해주세요.");
      });
    return () => {
      active = false;
    };
  }, []);
  const connected = settings?.gmail.state === "connected";
  return (
    <>
      <div className="page-heading">
        <h1>오늘의 LevelUp</h1>
        <p>
          처음 오셨네요. 구독 출처를 추가하고, 원하면 아침 메일을 위한 Gmail
          발송 권한을 허용하세요. 순서는 상관없습니다.
        </p>
      </div>
      {error ? (
        <p className="error-callout" role="alert">
          {error}
        </p>
      ) : !home ? (
        <p role="status">홈 정보를 불러오는 중…</p>
      ) : (
        <>
          <section className="getting-started" aria-label="시작하기">
            <article className="start-card source-start">
              <div className="start-heading">
                <span className="accent-icon">
                  <Icon name="rss" />
                </span>
                <h2>구독 출처 추가</h2>
              </div>
              <p>
                블로그 주소나 RSS·Atom 주소를 넣거나 기본 후보 5곳에서 고르세요.
              </p>
              <p className="muted">
                최초 기준 수집에 포함된 글은 알림에서 제외하며, 이후 늦게 발견한
                과거 글은 알림에 포함될 수 있습니다.
              </p>
              <div className="start-action">
                <Link className="primary" href="/tech/subscriptions">
                  <Icon name="plus" />
                  구독 출처 추가
                </Link>
                <small id="source-help">
                  초기 수집이 끝나면 새 글을 확인합니다.
                </small>
              </div>
            </article>
            <article className="start-card">
              <div className="start-heading">
                <span className="accent-icon">
                  <Icon name="mail" />
                </span>
                <h2>
                  {!settings
                    ? "Gmail 연결 확인"
                    : connected
                      ? "Gmail 연결됨"
                      : settings.gmail.state === "reauth_required"
                        ? "Gmail 재연결 필요"
                        : "Gmail 발송 권한 필요"}
                </h2>
              </div>
              <p>
                {connected
                  ? "로그인한 Google 계정으로 매일 아침 새 글 목록을 보낼 수 있습니다."
                  : "로그인할 때 Gmail 발송 권한을 허용하지 않았다면, 같은 계정으로 발송 권한을 연결할 수 있습니다."}
              </p>
              <p className="muted">
                허용하지 않아도 사이트에서 글을 읽을 수 있습니다. 받은편지함은
                읽지 않습니다.
              </p>
              <div className="start-action">
                <Link className="secondary" href="/settings">
                  <Icon name="mailSmall" />
                  {connected ? "알림 설정" : "발송 권한 허용"}
                </Link>
                <small id="gmail-start-help">
                  같은 Google 계정으로 발송합니다.
                </small>
              </div>
            </article>
          </section>
          <section className="empty-brief" aria-label="기술블로그 상태">
            <Icon name="empty" />
            <p>
              {home.tech.count === null
                ? "오늘의 브리핑이 확정되지 않았습니다"
                : `${home.tech.isPreview ? "예정 브리핑" : "오늘의 브리핑"} · ${home.tech.count}개 글`}
            </p>
            <small>
              <Link href="/tech">오늘의 브리핑</Link> ·{" "}
              <Link href="/tech?view=all">수집한 전체 글 보기</Link>
            </small>
          </section>
          <section className="planned-features" aria-label="앞으로 추가할 기능">
            {home.homeCards
              .filter((card) => card.status === "planned")
              .map((card) => (
                <article className="planned" key={card.id}>
                  <div className="planned-head">
                    <Icon
                      name={
                        card.id === "inbox-summary" ? "mailSmall" : "newsSmall"
                      }
                    />
                    <h2>{card.label}</h2>
                    <span className="badge neutral">
                      <Icon name="pending" />
                      준비 중
                    </span>
                  </div>
                  <p>아직 상세 설계 전인 기능입니다.</p>
                </article>
              ))}
          </section>
        </>
      )}
    </>
  );
}
