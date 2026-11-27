"use client";
import { useEffect, useRef, useState } from "react";
import { Icon } from "@/core/icon";
import { takeReportUrl } from "@/modules/reports/handoff";
import { documentUrl, reportPrompt } from "@/modules/reports/prompt";
export default function ReportsPage() {
  const [url, setUrl] = useState("");
  const [prompt, setPrompt] = useState("");
  const [promptUrl, setPromptUrl] = useState("");
  const [provider, setProvider] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const text = useRef<HTMLTextAreaElement>(null);
  const stale = Boolean(prompt && url !== promptUrl);
  const canUsePrompt = Boolean(
    prompt.trim() && promptUrl && !stale && provider,
  );
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      const handoff = takeReportUrl();
      if (handoff) {
        setUrl(handoff);
        try {
          setPrompt(reportPrompt(documentUrl(handoff)));
          setPromptUrl(handoff);
        } catch {
          /* Validate in form. */
        }
      }
      try {
        const saved = localStorage.getItem("levelup-report-provider");
        if (saved === "chatgpt" || saved === "claude") setProvider(saved);
      } catch {
        /* Optional preference. */
      }
    });
    return () => {
      active = false;
    };
  }, []);
  function generate(event: React.FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      setPrompt(reportPrompt(documentUrl(url)));
      setPromptUrl(url);
      setError("");
    } catch {
      setError(
        "인증 정보가 없는 공개 HTTP(S) 문서 주소를 입력하세요. 내부 주소와 IP 주소는 사용할 수 없습니다.",
      );
    }
  }
  async function copy() {
    if (!canUsePrompt) return;
    try {
      await navigator.clipboard.writeText(prompt);
      setError("");
      setMessage(
        "요청문을 복사했습니다. 외부 서비스에 붙여 넣고 직접 실행하세요.",
      );
    } catch {
      text.current?.focus();
      text.current?.select();
      setError("자동 복사에 실패했습니다. 선택된 요청문을 직접 복사하세요.");
    }
  }
  return (
    <>
      <div className="page-heading">
        <h1>리포트 분석</h1>
        <p>공개 웹페이지나 텍스트형 PDF의 URL로 요약 요청문을 준비합니다.</p>
      </div>
      <ol className="report-steps">
        <li>
          <span>1</span>문서 URL 입력
        </li>
        <li>
          <span>2</span>요청문 확인·복사
        </li>
        <li>
          <span>3</span>AI 서비스에서 직접 실행
        </li>
      </ol>
      <form className="report-form" onSubmit={generate}>
        <label>
          문서 URL
          <input
            type="url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setMessage("");
              setError("");
            }}
            maxLength={2048}
            placeholder="https://example.com/report.pdf"
            required
            autoComplete="off"
          />
        </label>
        <p className="muted">
          로그인 없는 공개 HTML·텍스트형 PDF를 사용하세요. 사이트는 문서를
          요청하거나 분석 이력을 저장하지 않습니다. URL 접근 성공은 외부
          서비스에서 확인하세요.
        </p>
        <fieldset className="report-providers">
          <legend>사용할 AI 서비스</legend>
          {["chatgpt", "claude"].map((value) => (
            <label
              className={provider === value ? "provider-selected" : ""}
              key={value}
            >
              <input
                type="radio"
                name="provider"
                value={value}
                checked={provider === value}
                required
                onChange={() => {
                  setProvider(value);
                  try {
                    localStorage.setItem("levelup-report-provider", value);
                  } catch {
                    /* Optional. */
                  }
                }}
              />
              {value === "chatgpt" ? "ChatGPT" : "Claude"}
            </label>
          ))}
        </fieldset>
        {!provider && (
          <p className="muted">사용할 AI 서비스를 먼저 선택해주세요.</p>
        )}
        <div>
          <button className="secondary" type="submit">
            <Icon name="refresh" />
            {prompt ? "요청문 다시 만들기" : "요청문 만들기"}
          </button>
        </div>
        {stale && (
          <p className="muted" role="status">
            문서 URL이 변경되었습니다. 편집한 요청문은 유지되며, 다시 만들기
            전에는 복사하거나 외부 서비스에서 열 수 없습니다.
          </p>
        )}
        <label>
          요약 요청문
          <textarea
            ref={text}
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value);
              setMessage("");
            }}
            placeholder="문서 URL을 입력하고 요청문 만들기를 눌러주세요."
            spellCheck={false}
          />
        </label>
        {error && (
          <p className="error-callout" role="alert">
            {error}
          </p>
        )}
        <div className="feature-actions">
          <button
            className="primary"
            type="button"
            disabled={!canUsePrompt}
            onClick={copy}
          >
            <Icon name="copy" />
            요청문 복사
          </button>
          {canUsePrompt ? (
            <a
              className="secondary"
              href={
                provider === "claude"
                  ? "https://claude.ai/"
                  : "https://chatgpt.com/"
              }
              target="_blank"
              rel="noopener noreferrer"
            >
              <Icon name="external" />
              {provider === "claude" ? "Claude" : "ChatGPT"}에서 열기
            </a>
          ) : (
            <button className="secondary" type="button" disabled>
              <Icon name="external" />
              {provider === "claude"
                ? "Claude"
                : provider === "chatgpt"
                  ? "ChatGPT"
                  : "AI 서비스"}
              에서 열기
            </button>
          )}
        </div>
        {message && (
          <p className="status-message" role="status">
            {message}
          </p>
        )}
        <p className="caption">
          복사한 요청문을 새 탭에 붙여 넣고 직접 실행하세요. 읽지 못한 PDF는
          해당 서비스에서 파일을 제공하세요. 계정 비밀번호·API 키는 받지
          않습니다.
        </p>
      </form>
    </>
  );
}
