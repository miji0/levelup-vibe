# API 설계서

| 항목 | 내용 |
|---|---|
| 프로젝트 | LevelUp — 개인용 웹사이트 / 모닝 테크 |
| 문서 ID | API-LEVELUP-v0.10 |
| 작성일·버전 | 2026-11-26 / v0.10 |
| 작성자 | Codex — 사용자 요청과 저장소 자료 기반 |
| 상태 | 검토용 설계 초안. G0·G1·G2 승인 기록 없음 |
| 검토·승인 담당 | 사이트 소유자. 고정 출시일 없이 실제 검토 수행 시 일자 기록 |
| 대상 | 첫 릴리스의 P1·P2 전체. 구현·연동·테스트 완료를 의미하지 않음 |

## 변경 이력

| 버전 | 날짜 | 변경 내용 | 승인 |
|---|---|---|---|
| v0.6 | 2026-11-25 | CR-MIN-001: Python 호스트 통합·당일 자동 재발송 제외·단일 호출 결과 통합·템플릿 적용 범위 분리 | 변경 범위 사용자 확인·전체 문서 미승인 |
| v0.7 | 2026-11-26 | 확정 PRD v0.28 대조·과거 문구/참조 정정, Mac Chrome + iPhone Safari·모든 글 목록 최신순 확정, 실행 검증과 분리 | PRD·기기 범위 사용자 확정 / 개별 단계 승인 전 |
| v0.8 | 2026-11-26 | 00~04 미결·권장안 통합, 확정/설계/환경/검증/후속 보류 구분·잔여 문구/참조 정정. 권장안 미채택·실행 미검증 | 정정 요청 반영 / 개별 문서 미승인 |
| v0.9 | 2026-11-26 | G2 검토 결정 반영(PRD v0.29): 웹·API 한 Vercel 프로젝트·같은 origin, OAuth 앱 프로덕션 게시(검증 미신청) | 소유자 결정 / G2 전체 승인 전 |
| v0.10 | 2026-11-26 | 사용자 채택: Services 한 프로젝트·DB 저장 세션(auth_sessions 추가, 총 14개)·외부 클라우드 자동 백업. 실제 설정/검증은 미완료 | 세 가지 설계 사용자 채택 / 전체 단계 미승인 |

## 참고 문서와 적용 기준

- [작성 가이드](../AGENTS.md), [PRD v0.30](../../PRD.md), [디자인 분석](../../DESIGN.md)
- [서비스 기획서 v0.12](../00-기획/서비스기획서.md), [비즈니스 정책서 v0.11](../00-기획/비즈니스정책서.md)
- [SRS v0.12](../01-요구사항분석/요구사항명세서-SRS.md), [유스케이스 v0.10](../01-요구사항분석/유스케이스명세서.md), [RTM v0.12](../01-요구사항분석/요구사항추적매트릭스-RTM.md)

요구사항의 FR/NFR·UC·SCR·BP 식별자를 유지한다. PRD v0.30의 제품 정책과 ISSUE-001의 지원 조합은 확정이며 재결정하지 않는다. DEC-001·002·003·006·007의 남은 구현 결정/환경 설정과 실제 검증, DEC-005·008·ISSUE-001의 실행 검증, DEC-004의 후속 보류를 구분한다. 통합 상태·권장안은 [서비스 기획서 7.4](../00-기획/서비스기획서.md#74-prd-확정-후-순차-검토-2026-11-26)를 따른다. 세 가지 채택 항목은 통합 표의 확정 기록을 따르고, 나머지 권장안 기재는 채택·개별 단계 승인·테스트 통과를 뜻하지 않는다.

## 1. API 설계 원칙

같은 origin의 TypeScript 웹과 Python API 사이 공개 계약이다. 단일 Vercel Services 프로젝트에서 /api/*를 Python API로 고정 라우팅하며 Python API가 권한·업무 정책을 담당한다. 기본 경로는 `/api/v1`이며 공개 개발자 API·회원가입·글 작성 CRUD는 없다. Python API와 worker는 같은 Python 서비스를 직접 호출한다. TypeScript SSR는 cookie를 고정 API에 전달하고 인증 결과를 확인하며, 브라우저처럼 Python 코드를 직접 import하지 않는다. API 직접 URL 접근도 인증을 우회하지 못한다.

Gmail 연결은 사용자가 확인한 첫 릴리스 범위다. 연결한 계정이 발신·수신 주소가 되며 임의 수신 주소·대량 발송·메일함 읽기 API는 제공하지 않는다. 리포트 URL·요청문을 받는 서버 API도 없다.

## 2. 인증/인가

### 2.1 사이트 인증

Google OIDC 로그인과 동일 Google 계정의 Gmail 연결 정책은 확정(PRD 8.2)이다. Python 서버가 검증한 Google sub를 구성된 소유자 ID와 비교하고 email_verified=true를 검사한다. Python API가 Secure·HttpOnly·SameSite=Lax·host-only cookie의 무결성·수명·소유자를 매 요청에서 검사한다. provider access/refresh token은 cookie나 브라우저 JSON에 넣지 않는다. 사이트 세션은 Google 로그인 성공 시점부터 7일(604,800초) 고정 만료다. 일반 요청·페이지 방문·cookie 재발급으로 최초 만료 시각을 연장하지 않는다. 만료 시 개인 API는 401로 응답하고 화면은 Google 로그인 후 안전한 원래 내부 경로로 복귀한다. 로그아웃은 즉시 세션을 종료한다. 사이트 세션 만료·로그아웃은 Gmail 발송 token이나 정기 작업을 해제하지 않는다. 서버는 발급 시각과 고정 만료를 검증하고 cookie 만료도 이를 넘기지 않는다. 사이트 세션은 auth_sessions의 token_hash·소유자·expires_at·revoked_at을 확인하는 DB 저장 방식으로 확정했다. cookie는 난수 token만 담고 로그아웃은 현재 세션의 revoked_at과 cookie 만료를 처리한다. 다른 기기의 로그인은 유지한다. OAuth 라이브러리(Authlib 제안)·실제 구현 검증은 남으며 cookie 교체로 최초 7일 만료를 연장하지 않는다.

변경 요청은 정확한 Origin + 세션 CSRF 토큰을 검증한다. Python 인증 경로도 라이브러리와 서버의 CSRF/state 처리를 적용한다. site_login과 gmail_connect의 state purpose를 혼용하지 않는다. Gmail callback은 일회성 state·세션 바인딩·PKCE·nonce·ID token 검증을 수행한다. CORS는 외부 origin을 허용하지 않는다. 웹과 API는 한 Vercel 프로젝트의 같은 origin에서 제공하므로(PRD 8.1) 브라우저는 API를 같은 origin 경로로만 호출하고 별도 API origin을 두지 않는다. Google OAuth 앱은 외부 사용자 유형·프로덕션 게시(검증 미신청)이며, Testing 상태의 7일 refresh token 만료를 정기 발송 연결에 쓰지 않는다(PRD 8.2). 개인 응답은 `Cache-Control: private, no-store`다.

### 2.2 소유·외부 URL 검사

source/article/digest/delivery/job ID가 현재 소유자의 관계에 속하는지 조회한다. 비소유자의 리소스는 404로 응답한다. 수집 요청은 DNS·실제 연결 IP·각 redirect를 검증하는 서버 전용 클라이언트만 사용한다. 단순 URL 정규식만으로 SSRF를 막았다고 보지 않는다.

## 3. 공통 규격

| 항목 | 규격 |
|---|---|
| 본문 | application/json; UTF-8. Gmail callback은 browser redirect |
| 식별자 | 내부 ID는 UUID, Google message ID는 불투명 문자열 |
| 시각·날짜 | ISO 8601 UTC instant, 업무 날짜 YYYY-MM-DD KST |
| 응답 | 성공 `{data, meta?}`, 실패 `{error:{code,message,fields?,requestId}}` |
| 페이지 | limit 기본 20·최대 100 제안, opaque cursor·nextCursor·hasMore |
| 동시 변경 | GET/변경 응답의 version, 변경 시 `If-Match: "숫자"`; 누락 428·충돌 412 |
| 테스트 중복 | API-017의 `Idempotency-Key: UUID` 필수. 동일 owner/key 재요청은 기존 job 반환 |
| 비밀 | 토큰·비밀번호·DB 연결 문자열·OAuth code를 JSON/로그에 반환하지 않음 |

필드명은 camelCase, 경로는 복수 명사·소문자를 사용한다. 문서의 JSON은 계약 예시이며 실제 수집/발송 결과가 아니다. 본문 최대 16KiB, 제목 검색어 200자·URL UTF-8 2,048바이트 제한은 검토용 제안이다. 원문 요청문은 로컬 처리이므로 서버 본문 제한과 무관하다.

## 4. API 엔드포인트 목록

| ID | Method · 경로 | 주요 책임 | FR·SCR |
|---|---|---|---|
| API-001 | Python OAuth·세션 `/api/auth/*` | 로그인·callback·로그아웃, 구체 메서드는 라이브러리 계약 | FR-001 / SCR-001 |
| API-002 | GET /session | owner 최소 정보·CSRF token | FR-001 / 공통 |
| API-003 | GET /home | 활성 sections·기능별 homeCards·준비 카드 2개 | FR-002 / SCR-002 |
| API-004 | POST /tech/sources/resolve | 공개 연결 확인·피드 후보 반환 | FR-003 / SCR-005 |
| API-005 | GET /tech/sources | active/paused 출처·상태 목록 | FR-003~006 / SCR-005 |
| API-006 | POST /tech/sources | 재검증·중복 검사·추가/재추가·기준 job | FR-004 / SCR-005 |
| API-007 | PATCH /tech/sources/{id} | 구독 켜기·끄기 | FR-005 / SCR-005 |
| API-008 | DELETE /tech/sources/{id} | 논리 삭제·미발송 중단 | FR-006 / SCR-005 |
| API-009 | GET /tech/articles | 전체/저장 목록·검색·출처/읽음 필터 | FR-011·012·023 / SCR-003·004 |
| API-010 | PATCH /tech/articles/{id}/state | 읽음·저장·숨김·복원 | FR-012·013 / SCR-003·004 |
| API-011 | GET /tech/collection-status | 출처별 수집 건강·실패 원인 | FR-018 / SCR-006 |
| API-012 | GET /tech/digests/{date} | 오늘 미리보기 또는 날짜별 전체 목록 | FR-010·015 / SCR-003 |
| API-013 | GET /settings | 정기 알림·Gmail 연결 요약 | FR-014·019 / SCR-008 |
| API-014 | PATCH /settings | 정기 알림 설정 | FR-014 / SCR-008 |
| API-015 | GET /tech/deliveries | 정기/테스트 발송 결과 목록 | FR-016·018 / SCR-006 |
| API-016 | GET /tech/deliveries/{id} | 접수/불명확·확인 기록 상세 | FR-016·018 / SCR-006 |
| API-017 | POST /tech/test-emails | 별도 테스트 작업 생성 | FR-017 / SCR-008 |
| API-018 | GET /jobs/{id} | 작업 진행·결과 조회 | FR-004·017·018 / SCR-005·008 |
| API-019 | POST /integrations/gmail/connect | 연결용 Google OAuth 시작 | FR-014 / SCR-008 |
| API-020 | GET /integrations/gmail/callback | code 교환·연결 저장 후 설정으로 redirect | FR-014 / SCR-008 |
| API-021 | DELETE /integrations/gmail | 발송 연결 해제·토큰 삭제/철회 시도 | FR-014 / SCR-008 |
| API-022 | GET /tech/digests | 날짜별 정기 상태·미발송/지연/누락, delivery 결합 | FR-015·018 / SCR-006 |

`/api/auth/*`만 기본 경로 예외다. API-002~022는 모두 `/api/v1` 아래다. 수집/정기 발송을 인증 없는 HTTP cron endpoint로 노출하지 않는다.

## 5. API 상세 명세

### 5.1 API-002·003: 공통 세션·홈

API-001의 사이트 인증 경로는 `/api/auth/signin`(GET), `/api/auth/callback/google`(GET), `/api/auth/signout`(POST)로 Python에 구현하는 안이다. 로그인 전 바인딩 cookie와 site_login state를 확인한 뒤 소유자 subject에 대해서만 보호된 세션을 발급한다. 기존 Auth.js 클라이언트를 요구하지 않으며 브라우저 공개 경로·소유자 제약은 유지한다. 실제 라이브러리·callback URI는 배포 전 검증한다.


API-002는 기존 `{owner:{id,email,provider:"google"},csrfToken}`을 반환한다. csrfToken은 현재 auth_sessions의 값을 사용하고 raw 세션 token/hash는 JSON에 반환하지 않는다. email은 검증된 로그인 계정이며 연결 해제 후에도 표시한다. 사이트 인증용 공급업체 자격증명은 없다. API-003은 기존 `sections:[{id,label,path}]`, `tech:{digestDate,count,isPreview}`를 유지하고 `homeCards:[{id,label,status,path,description,summary}]`를 추가한다. count는 오늘 브리핑 기준이며 수집 호출 횟수가 아니다. reports는 sections에 항상 포함하고 homeCards에는 넣지 않는다(CR-UX-004). tech 요약 조회 실패 시 해당 카드에 unavailable을 표시하고 다른 섹션 탐색은 유지한다. CR-FLOW-001로 tech에 state/reasonCode를 추가하고 count는 number 또는 null로 정의한다. isPreview=true이면 API-012의 예상 건수, 확정 후에는 실제 건수, missed/not_scheduled면 null이다. 조회가 정상인 missed는 unavailable 오류로 바꾸지 않고 준비된 기술블로그 카드의 요약에 “작업 시작 누락”을 표시한다.


API-001의 최초 로그인 요청은 `openid email https://www.googleapis.com/auth/gmail.send`와 offline access를 함께 요청한다. 일회성 state·pre-login 바인딩·PKCE·nonce·ID token 검증과 고정 owner sub 비교를 마친 뒤 세션을 발급한다. 실제 granted scope와 refresh token(또는 동일 sub의 기존 유효 token)을 확인한 경우에만 발송 연결을 저장한다. 발송 scope만 누락된 성공 로그인은 disconnected 연결 행·검증 이메일을 저장하고 권한 필요를 안내한다. 전체 동의 취소·OIDC 실패는 로그인 실패다. 기존 연결 행이 있는 일반 로그인은 `openid email`만 요청하고 연결 상태/token을 복원하지 않는다. 연결 이메일이 달라지면 reauth_required로 전환한다. 최초 연결 저장도 기존 소유자 발송 잠금·connection version 규칙을 사용하고 정기 알림을 자동으로 켜지 않는다.

### 5.1.1 API-003의 홈 카드 계약 (CR-UX-001)

status는 ready/planned/unavailable이다. ready 카드는 실제 활성 기능의 path와 기능별 summary 문자열을 갖고, unavailable은 제공 중 기능의 요약 조회 오류 안내이며 path는 유지한다. planned는 path=null·summary=null이며 설명만 표시한다. sections는 계속 활성 탐색 항목만 포함하므로 준비 카드가 메뉴로 섞이지 않는다. 아래는 미래 기능 2개의 정적 계약 예시이며 수집/AI 결과가 아니다.

```json
{
  "homeCards": [
    {"id":"inbox-summary","label":"수신 이메일 요약","status":"planned","path":null,"description":"아직 상세 설계 전인 기능입니다.","summary":null},
    {"id":"daily-news","label":"데일리 기사 요약","status":"planned","path":null,"description":"아직 상세 설계 전인 기능입니다.","summary":null}
  ]
}
```

실제 응답은 공통 data envelope 안에 기존 필드 및 활성 기능 카드와 함께 반환한다. 카드 순서는 기술블로그·준비 카드 2개다(CR-UX-004). 기술블로그 카드의 구독 출처 상태는 `tech.sources`로 반환한다.

```json
{
  "tech": {
    "digestDate": "2026-11-25", "count": 21, "isPreview": false,
    "sources": {"total": 5, "failedCount": 0, "lastCollectedAt": "2026-11-24T22:30:00Z"}
  }
}
```

위 예시는 sources 위치만 보이며 state/reasonCode 등 기존 필드는 생략했다. 초기 미수집 출처의 상태는 서비스기획서 7.4의 채택 전 검토 대상이다. 아래 failedCount 기준만으로 수집 대기 여부를 판정할 수 없으며, 보완 응답 필드·상태 우선순위 확정 전 이를 구현 완료 계약으로 사용하지 않는다. `sources` 설계 제안(CR-UX-004): total은 켜져 있는 구독 출처 수, failedCount는 그중 가장 최근 수집 시도가 실패 또는 부분 성공(격리 항목 있음)인 출처 수, lastCollectedAt은 그 출처들의 가장 최근 수집 종료 시각이다(아직 수집 전이면 null). 화면은 failedCount=0이면 ‘모두 정상’, 1 이상이면 ‘N개 확인 필요’를 표시하고 [수집·발송 상태]로 안내한다. total=0이면 첫 방문 안내를 표시한다. 출처별 실패 원인은 이 응답에 담지 않고 수집·발송 상태 화면에서 조회한다. `sources` 조회만 실패하면 tech 카드 전체를 unavailable로 바꾸지 않고 출처 상태 줄만 ‘확인 불가’로 표시한다. planned의 ‘준비 중’ 배지는 status의 UI 표시이며 count/lastUpdatedAt/출시일·실행 URL은 없다. GET /home 때문에 미래 기능의 API·Gmail 읽기·AI/작업을 호출하지 않는다.

### 5.2 API-004: URL 연결 확인

요청 `{inputUrl:string}`. 입력 중에는 호출하지 않고 ‘연결 확인’ 조작 후 실행한다. 공백·fragment·host·기본 포트를 정규화하고 공개 HTTP(S)·기본 포트만 허용하는 제안이다. 출처 응답과 RSS/Atom 후보를 같은 안전한 클라이언트로 검증한다. HTML은 등록된 adapter가 있을 때만 성공한다.

**피드 탐색 순서(FUP-004).** ① HTML의 RSS/Atom 안내 링크. ② 링크가 없거나 알린 주소가 모두 쓸 수 없으면 같은 사이트의 흔한 주소를 우선순위 순서로 확인한다: 루트 `/feed`, `/feed/`, `/rss`, `/rss.xml`, `/atom.xml`, `/feed.xml`, `/index.xml`, `/ko/feed`, `/ko/rss`와 입력 주소 경로 아래 `/feed`, `/rss`, `/feed.xml`(합계 최대 12개). ③ 검토된 사이트별 피드 주소 표(예: `d2.naver.com` → `/d2.atom`). 후보 확인은 모두 같은 안전한 클라이언트(사설 주소·시간·크기·리다이렉트 상한)로 하고 전체 시간 예산은 20초이며, 초과하면 그때까지 찾은 것만 쓴다. 실제 RSS/Atom으로 해석되는 응답만 후보로 인정하며(존재하지 않는 경로가 HTML을 200으로 돌려주는 사이트는 제외), 여러 개가 맞으면 우선순위가 가장 높은 하나만 반환한다. 등록 때의 재확인도 같은 순서를 쓰므로 선택 결과가 같다. 모두 실패하면 `UNSUPPORTED_SOURCE`(링크는 있으나 쓸 수 없던 경우는 `INVALID_FEED`)이고 안내 문구는 "이 사이트에서 RSS·Atom 피드를 찾지 못했습니다. 사이트가 RSS를 제공하지 않을 수 있습니다. RSS·Atom 주소를 직접 입력해주세요."이다. 분당 요청 한도(연결 확인과 등록 합계 5회)는 그대로이며 한 번의 확인이 외부 요청 최대 13건을 만들 수 있다.

```json
{
  "data": {
    "inputUrl": "https://example.org/blog",
    "options": [
      {"name": "Example Blog", "collectionUrl": "https://example.org/feed.xml", "collectorType": "rss", "adapterKey": null}
    ],
    "requiresSelection": false
  }
}
```

후보가 여러 개면 requiresSelection=true이며 사용자 선택 없이 첫 후보를 자동 등록하지 않는다. 이 응답은 등록 완료/원문 전체 접근 보장이 아니다. URL이 동일 출처로 이미 등록됐으면 해당 후보에 existingSourceId를 붙여 재등록을 안내한다. 확인 후 입력이 바뀌면 클라이언트는 후보 상태를 지운다.

### 5.3 API-005·006: 목록·추가·재추가

GET은 삭제된 항목을 기본 목록에 반환하지 않으며 name, inputUrl, collectionUrl, collectorType, enabled, initializationState, lastSuccessAt, lastError, version을 제공한다. 같은 도메인 다른 피드는 별도 행이다. CR-FLOW-001로 lastUsableAt/lastResult/openIssueCount를 추가하여 partial·미해결 항목을 구독 행에서도 표시한다.

POST 요청 `{inputUrl,collectionUrl}`. 선택 URL이 입력 URL의 검증 결과에 속하는지 서버에서 다시 확인하고 collector/표시 이름을 신뢰 가능한 수집 결과에서 결정한다. 클라이언트가 주는 adapter 이름을 실행하지 않는다.

성공은 **202 Accepted**와 `{source:{id,name,initializationState:"pending",version},jobId}`다. sources·새 epoch·job을 한 트랜잭션으로 저장한다. 이미 active/paused인 수집 URL은 **409 SOURCE_ALREADY_EXISTS**와 existingSourceId를 반환한다. soft-deleted URL은 같은 ID로 재추가하고 새 generation·baseline을 만든다. 최초 snapshot은 과거 글로 처리하며 알림을 보내지 않는다. baseline 실패는 source를 지우지 않고 실패·다음 재시도를 표시한다.

### 5.4 API-007·008: 구독 토글·삭제

PATCH는 `{enabled:boolean}`과 If-Match가 필요하다. 끄기는 source를 paused로 남기고 epoch를 종료한다. 켜기는 새 epoch·baseline job을 만들고 **202**, 끄기는 **200**으로 최신 source/version을 반환한다. 같은 목표 상태는 현재 결과를 반환하며 중복 epoch를 만들지 않는다.

DELETE는 If-Match가 필요하고 **200** `{id,status:"deleted",preserved:{articles:true,readingState:true,deliveryHistory:true}}`를 반환한다. 이미 삭제된 동일 소유자 항목의 반복 요청은 삭제 상태를 반환한다. 아직 존재하는 항목의 잘못된 version은 412다.

두 요청 모두 SAD 7.2·7.3의 소유자 발송 잠금 → source 행 잠금을 따른다. 진행 중 결과는 generation 검사로 폐기한다. 잠금 대기는 제한하며 실패하면 **409 RESOURCE_BUSY**로 재시도를 안내한다. 이미 Gmail에 요청한 메시지의 취소를 응답으로 약속하지 않는다.

### 5.5 API-009·010: 글 목록·개인 상태

GET query는 `view=all|saved`, `q`, `sourceId`, `read=all|read|unread`, `hidden=exclude|include|only`, `cursor`, `limit`다. 숨김은 기본 제외하며 include/only로 확인·복원한다. 이 필터는 오늘/전체/저장 목록에만 적용하며 이메일 자격·브리핑의 필터 전 전체 건수는 변경하지 않는다. read/hidden 같은 enum 밖 입력은 400이다. 제목 포함 검색만 지원하고 sourceId는 삭제된 출처의 기존 글도 필터할 수 있다. 전체/저장은 `(publishedAt ?? firstSeenAt, id)` 내림차순으로 고정하고 sort 옵션은 받지 않는다. 오늘 미리보기에도 같은 기준을 사용하며 확정 브리핑은 구성 당시 sort_position을 보존한다.

응답 글은 `id,source:{id,name,status},title,originalUrl,publishedAt,publicationPrecision,firstSeenAt,intro,tags,state:{isRead,isSaved,isHidden,version}`이다. 정렬은 `(publishedAt ?? firstSeenAt,id)` 내림차순. source/글 metadata는 HTML escape하여 표시한다. 원문은 이 API를 경유한 추적 redirect 없이 직접 연다.

PATCH body는 아래 boolean 중 최소 하나이고 지정하지 않은 필드는 유지한다. false 값도 실제 변경으로 취급한다.

```json
{"isRead": true, "isSaved": false}
```

If-Match로 상태 version을 검사하며 상태 행이 없으면 version=0이다. 성공은 **200**과 서버가 기록한 최신 state다. 원문/리포트 버튼은 API-010을 호출하지 않는다. 읽음·저장·숨김은 수집/발송 metadata와 분리한다.

### 5.6 API-011·012: 수집 상태·날짜별 전체 브리핑

API-011은 source별 lastAttemptAt, lastSuccessAt(완전 성공), lastUsableAt(정상 저장/정상 빈 응답), lastResult(success/partial/failed), initializationState, openIssueCount, lastErrorCode/message와 최근 job 결과를 반환한다. job resultSummary는 validCount/rejectedCount/newCount/updatedCount와 정제 issue 코드 집계를 제공하며 partial도 polling 종료 상태다. 오류가 없는 최초 대기는 성공과 다르다. 수집 수·신규 수·실패 횟수는 각각 명명한다. 한 source 오류 때문에 응답 전체를 실패시키지 않는다.

API-012의 date는 YYYY-MM-DD다. 오늘 첫 snapshot 전에는 08:00 이후 지연 중이라도 `isPreview=true`이며 확정 후는 false다. isPreview만으로 발송 가능/완료를 추정하지 않고 state/reasonCode/startedAt/snapshotAt을 표시한다. 미리보기의 fullCount/filteredCount는 읽기 전용 예상 건수이며 반드시 미리보기 라벨과 함께 표시한다. API-022의 fullCount는 확정 이력 전용이므로 미확정이면 null이다. 마감 후 missed/not_scheduled는 isPreview=false·items=[]·fullCount=null이며 실시간 예상 목록을 확정 이력처럼 반환하지 않는다. 응답은 `{date,state,reasonCode,scheduledAt,startDeadlineAt,startedAt,snapshotAt,isPreview,fullCount,filteredCount,items,deliveryState}`와 페이지 meta다. row가 없을 때의 state 계산도 API-022와 동일하다. q/sourceId/read/hidden/cursor/limit는 API-009와 같은 의미다. fullCount는 필터 전 전체 유효 대상, filteredCount는 적용 후 건수다. 20개 초과도 페이지를 넘겨 **모든 대상**을 볼 수 있다.

이메일 전체 보기 링크는 `/tech?date=YYYY-MM-DD`로 연결한다. 비로그인은 SCR-001을 거친 뒤 같은 내부 경로로 복귀한다. 과거의 확정 item은 당시 제목/출처/URL snapshot을 사용하며 읽음·저장 상태는 현재 값을 조합한다. snapshot이 없는 과거/마감 후 조회는 **200** `{state:"missed",reasonCode:"START_DEADLINE_MISSED",isPreview:false,items:[],fullCount:null,filteredCount:null}`처럼 API-022의 상태 규칙으로 명시한다. 설치 전 날짜는 not_scheduled다. 이전 not_created를 별도 외부 enum으로 유지하지 않는다. missed·미확정의 null은 대상 0개가 아니다. 정상 empty snapshot만 fullCount=0이다. GET은 digest/job 생성·발송을 실행하지 않는다.

### 5.6.1 API-022: 날짜별 정기 브리핑 상태

GET `/api/v1/tech/digests`는 `dateFrom`, `dateTo`(KST, 기본 최근 7일·최대 31일, 미래 날짜 거절), `cursor`, `limit`를 받는다. 날짜 내림차순의 opaque cursor이며 날짜 범위/필터를 고정한다. 기존 delivery 목록 API-015와 다른 책임이다.

각 날짜는 `{date,state,reasonCode,scheduledAt,startDeadlineAt,startedAt,snapshotAt,delaySeconds,fullCount,delivery}`다. delivery는 마지막 revision의 안전한 `{id,state,kind,providerMessageId}` 또는 null이며 테스트는 섞지 않는다. 최초 scheduledAt은 D 08:00, startDeadlineAt은 D 08:20이다. startedAt은 owner 잠금·첫 snapshot 확보 시점, delaySeconds는 그 지연값이며 미시작이면 null이다. fullCount는 실제 snapshot이 있을 때만 숫자다.

DB digest가 있으면 그 상태/이유를 우선한다. 아직 행이 없으면 owner.created_at>scheduledAt인 날짜는 not_scheduled, 예약 전은 scheduled, [08:00,08:20)은 delayed, 마감 후 미시작은 missed를 **읽기 전용으로 계산**한다. worker 복구가 나중에 같은 날짜 missed 행을 멱등 저장할 수 있다. 이 파생 상태는 가짜 외부 발송 기록이 아니다. startedAt이 있거나 sending/unknown/accepted인 건을 missed로 덮어쓰지 않는다.

빈 대상 empty, 알림 중지 paused, Gmail 미연결 failed+GMAIL_NOT_CONNECTED는 각각 delivery=null이어도 반환한다. snapshot의 유효 항목 0개는 empty를 우선하고, 1개 이상이면 알림 중지→Gmail 연결 상태→발송 준비 순으로 판정한다. 원인/상태를 정확히 표시하고 fullCount=null을 0으로 렌더링하지 않는다. 기존 과거 이력은 보존한다.

```json
{"data":{"items":[{"date":"2026-11-25","state":"missed","reasonCode":"START_DEADLINE_MISSED","scheduledAt":"2026-11-24T23:00:00Z","startDeadlineAt":"2026-11-24T23:20:00Z","startedAt":null,"snapshotAt":null,"delaySeconds":null,"fullCount":null,"delivery":null}]},"meta":{"nextCursor":null,"hasMore":false}}
```

위 날짜/상태는 계약 예시이며 실제 발송 결과가 아니다. enum·범위·cursor 오류는 기존 INVALID_REQUEST/INVALID_CURSOR이며 새 인증 우회 경로를 만들지 않는다.

### 5.7 API-013·014: 설정

GET 예시에서 이메일은 연결 계정이 결정하는 읽기 전용 값이다.

```json
{
  "data": {
    "version": 3,
    "notificationsEnabled": false,
    "timezone": "Asia/Seoul",
    "gmail": {"state": "connected", "email": "owner@gmail.com", "version": 1}
  }
}
```

주소는 가상 예시다. gmail.email은 API-002와 같은 로그인 계정 이메일로 미연결/해제 후에도 표시하고 state=disconnected로 발송 불가를 구분한다. 주소 표시만으로 connected를 추론하지 않는다. PATCH는 `{notificationsEnabled?}`만 허용하며 If-Match는 공통 설정 version이다. email/provider/token 같은 알 수 없는 쓰기 필드는 400이다.

CR-UX-002의 다크/라이트 선택은 SCR-008 일반 설정에서 브라우저 `levelup.theme`로 즉시 저장한다. API-013·014에 theme 필드·쿠키·요청을 추가하지 않으며 PATCH의 theme 등 알 수 없는 필드는 기존대로 INVALID_REQUEST다. 테마 선택에 If-Match나 서버 [저장] 버튼을 요구하지 않는다.

설정 UI는 일반/연결 계정/기능별 그룹으로 나누지만 API-013·014 필드와 version 검사는 유지한다. notificationsEnabled는 현재 기술블로그 정기 메일만 제어한다. 준비 카드 상태는 정적 registry에서 오며 API-014로 켤 수 없다. inboxSummaryEnabled 같은 미정 필드는 INVALID_REQUEST다.

알림을 새로 켤 때 Gmail 연결이 유효하지 않으면 **409 GMAIL_NOT_CONNECTED**다. 연결 해제로 발송이 막혀도 수집·읽기·reports 사용은 유지한다. 알림 중지는 테스트 메일을 금지하지 않는다. 서버는 분석 URL을 받지 않는다.

### 5.8 API-015·016·017·018: 발송 결과·테스트

API-015는 `kind=digest|test|all`, `state`, `cursor`, `limit`로 실제 delivery 기록을 조회한다. 정기 상태의 날짜별 탭은 API-022를 쓰고 테스트 탭은 API-015의 kind=test를 쓴다. 미연결/empty/missed 때문에 delivery가 없는 날짜를 API-015에 가짜 발송 행으로 채우지 않는다. API-016은 providerMessageId(Gmail ID), mimeMessageId(RFC ID), subject, fromAddress/toAddress, kind, digestDate, state, preparedAt/submittedAt/acceptedAt, 정제한 오류, verificationOutcome/note/verifiedAt을 반환한다. MIME 원문·토큰은 반환하지 않는다. accepted의 표시 이름은 ‘Gmail 접수’이며 배달/열람 확인이 아니다.

API-017은 빈 JSON과 필수 Idempotency-Key를 받는다. 수신 주소·메일 본문을 임의 입력받지 않는다. 유효한 Gmail 연결이 있어야 하며 고정 테스트 템플릿으로 **202** `{jobId,kind:"test"}`를 반환한다. job·delivery는 정기 digest FK가 없고 정기 글의 상태/예약을 변경하지 않는다. 중복 요청은 같은 job ID를 반환한다.

API-018은 `{id,state,resultCode,resultSummary}`를 반환한다. UI polling은 화면이 보일 때만 수행하고 succeeded/partial/failed/skipped 종료 상태에서 멈춘다. 상세 간격은 구현 시 정한다. Gmail token이 만료·철회되면 reauth_required로 기록하고 연결 복구를 안내한다.

### 5.9 API-019·020·021: Gmail 연결 생명주기

1. POST connect: 현재 소유자 세션에 바인딩한 gmail_connect purpose의 일회성 OAuth state·nonce·PKCE를 생성한다. `oauth_states`의 만료는 10분 제안이다. 로그인 Google sub를 login_hint로 사용한 고정 Google authorization URL을 반환하고 브라우저가 이동한다.
2. 요청 범위는 `openid email https://www.googleapis.com/auth/gmail.send`. offline access를 요청하여 서버 worker가 브라우저 종료 후에도 갱신할 수 있게 한다. 기존 유효 refresh token이 있고 새 응답에 token이 없으면 검증된 동일 subject에 대해서만 기존 것을 유지한다.
3. callback: code/state 또는 error를 받는다. state의 세션·만료·1회성을 검사하고 서버에서 교환한다. ID token 서명·issuer·audience·nonce·verified email을 확인하고 sub가 로그인 소유자 sub와 같은지 검사한다. 불일치는 403 GOOGLE_ACCOUNT_MISMATCH로 기존 연결을 보존한다. code/error query는 접근 로그에서 가린다.
4. 성공: 소유자 발송 잠금 후 gmail_connections의 암호화 token·Google subject·email·scope·version을 저장한다. 표시된 연결 계정이 발신/수신 모두에 사용된다. **303**으로 `/settings?gmail=connected`에 복귀한다. 알림은 사용자가 별도로 켠다.
5. 거절/오류: 기존 정상 연결을 임의 삭제하지 않고 `/settings?gmail=error`로 복귀한다. 상세 토큰/Google 원문은 query에 넣지 않는다. 검증된 Google 계정이어도 Gmail 사용이 불가하면 테스트/최초 요청의 GMAIL_UNAVAILABLE로 안내하고 정상 발송을 보장하지 않는다. 취소·권한 부족·만료를 화면 안내로 구분한다.
6. DELETE 연결: 소유자 발송 잠금 후 connection version을 올리고 disconnected·로컬 token 삭제를 먼저 확정한다. Google 권한 철회는 제한 시간 내 시도한다. **200** `{state:"disconnected",remoteRevocation:"confirmed|unconfirmed"}`. 후자는 사용자가 Google 계정 권한 화면에서 제거하도록 안내한다. 이미 접수된 메일과 과거 기록은 유지한다.

로그인 계정과 다른 Gmail 연결은 제공하지 않는다. 재연결은 동일 sub에 대한 발송 권한 복구다. 연결 해제는 표시 계정을 지우거나 로그아웃시키지 않으며 다음 일반 로그인으로 발송을 복원하지 않는다. 원격 철회는 같은 OAuth 앱의 로그인 grant에도 영향을 줄 수 있으나 기존 사이트 세션과 발송 token은 따로 관리한다. Google OAuth 테스트 게시 상태에서 refresh token 유효기간이 제한될 수 있으므로 지속 운영 전 동의 화면·게시 상태·개인용 적용 조건을 확인한다. [Google OAuth 서버 흐름](https://developers.google.com/identity/protocols/oauth2/web-server), [토큰 만료 조건](https://developers.google.com/identity/protocols/oauth2#expiration).

### 5.10 외부 Gmail API 계약

Gmail API `POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send`에 base64url 인코딩한 MIME의 raw를 전달한다. From/To는 연결 email로 고정하고 제목은 `모닝 테크 · YYYY-MM-DD · N개` 제안이다. HTML과 text 대체 본문, escape된 제목/직접 원문 링크·전체 보기 링크를 구성한다. Gmail API 응답 id는 접수 기록으로 저장한다. [공식 전송 가이드](https://developers.google.com/workspace/gmail/api/guides/sending), [send 메서드](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send).

이 메서드의 공개 계약에는 제공업체 멱등 키가 명시되어 있지 않으므로 원격 중복 제거를 전제로 설계하지 않는다. Gmail send에 대한 SDK/HTTP 계층의 자동 재시도는 비활성화하고 앱의 상태 판정만 통과하게 한다. timeout으로 연결을 닫아도 Gmail 서버 처리 취소가 보장되는 것은 아니다. 고정 RFC Message-ID도 확인 보조 식별자일 뿐 중복 제거 보장이 아니다. Gmail send 요청 timeout은 전체 15초의 검토용 제안이다. timeout·5xx·접수 뒤 DB 실패는 unknown으로 두고 자동 재전송하지 않는다. 로컬 DB 키·잠금은 동시 실행을 막고 원격 불확실성은 OP-01로 관리한다.

Gmail 발송 한도·토큰 오류와 일시 오류를 구분한다. 정기 메일은 당일 자동 재발송하지 않는다. 명확한 미접수는 다음 정상 아침에 합치고 unknown은 수동 확인 전 예약을 유지한다(CR-MIN-001). HTTP 200도 받은편지함 도착을 증명하지 않으므로 ‘배달 완료’로 표현하지 않는다. [Gmail 오류·발송 한도 문서](https://developers.google.com/workspace/gmail/api/guides/handle-errors).

### 5.11 내부 작업·로컬 동작 계약

| ID | 실행자·입력 | 결과·부작용 |
|---|---|---|
| JOB-01 | worker, sourceId·generation·slot·leaseToken | 일반/최종 수집, source별 실패 격리, 5가지 콘텐츠 전부 동일 처리 |
| JOB-02 | worker, sourceId·generation·epochId | 초기 snapshot baseline, 성공 전 ready 금지 |
| JOB-03 | worker, ownerId·KST date | 전체 대상·발송 잠금·영속 메시지·Gmail 처리 |
| OP-01 / 제안 | 소유자 Gmail 수동 대조 + 운영 명령 | accepted/not accepted/unresolved 근거를 deliveries에 기록. 자동 재발송 버튼 없음 |
| REPORT-01 | 브라우저 메모리, URL·선택 provider | 공개 HTTP(S) 문법 검사 + PRD 5.3 고정 요청문. 네트워크 없음 |
| REPORT-02 | 명시적 클릭, 현재 편집 prompt | clipboard 또는 수동 복사 대안. 요약 완료 기록 없음 |
| REPORT-03 | 명시적 클릭, provider enum | ChatGPT/Claude 공식 홈 새 탭, URL/query로 문서·prompt 전송 없음 |

OP-01은 미결인 수동 기록 위치의 설계 제안이다. 확인 담당은 소유자, 고정 확인 기한 없이 필요할 때 대조하는 정책은 확정했다. 확인 기록 위치·안전한 운영 명령·보존은 DEC-002·006·007 검토 뒤 상세/운영 설계에서 작성한다. unknown의 시간 경과만으로 예약을 해제하거나 재전송하지 않으며 다른 정상 글의 발송은 유지한다. 메일 읽기 scope를 추가하여 자동 대조하지 않는다.

## 6. 에러 코드 테이블

| HTTP | code | UI 동작 |
|---|---|---|
| 400 | INVALID_REQUEST / INVALID_URL / INVALID_CURSOR | 입력별 라벨·수정 방법 |
| 401 | UNAUTHENTICATED | 로그인, 안전한 내부 returnTo 유지 |
| 403 | OWNER_REQUIRED / CSRF_INVALID | 접근 거절/다시 로그인, 개인 데이터 없음 |
| 404 | RESOURCE_NOT_FOUND | 현재 소유자의 대상인지 확인 후 안내 |
| 409 | SOURCE_ALREADY_EXISTS | 기존 항목으로 이동 |
| 409 | RESOURCE_BUSY | 진행 중 작업 종료 후 다시 시도, 삭제 완료 표시 금지 |
| 403 | GOOGLE_ACCOUNT_MISMATCH | 로그인한 Google 계정으로 재연결, 기존 연결 보존 |
| 409 | GMAIL_NOT_CONNECTED / GMAIL_REAUTH_REQUIRED | 설정의 Gmail 연결·재연결로 이동 |
| 412·428 | VERSION_CONFLICT / VERSION_REQUIRED | 최신 상태 재조회 후 사용자 변경 재시도 |
| 422 | PRIVATE_URL / UNSUPPORTED_SOURCE / INVALID_FEED | 공개 주소·직접 feed 입력 등 대안 |
| 429 | RATE_LIMITED | Retry-After에 맞춰 대기, 중복 테스트 요청 방지 |
| 502·504 | SOURCE_UNREACHABLE / SOURCE_TIMEOUT / SOURCE_TOO_LARGE | 출처 확인 실패, 등록 성공으로 표시하지 않음 |
| 500 | INTERNAL_ERROR | requestId와 재시도 안내, DB/토큰 원문 없음 |

비동기 Gmail 실패는 HTTP 202의 성공 메시지를 뒤집는 대신 job/delivery 상태로 표시한다. ‘요청 접수’와 ‘Gmail 접수’를 구분한다. 외부 Gmail 오류 HTTP 코드를 브라우저에 그대로 프록시하지 않는다.

## 7. Rate Limiting 정책

아래는 **구현 시작값 제안**, 성능·가용성 보장이 아니다. 실제 계정·운영 환경과 함께 DEC-002·003·006에서 확정한다. 소유자별 제한을 우선하고 인증 전에는 IP 제한을 별도로 적용한다.

| 작업 | 제안 상한 |
|---|---|
| 목록·상태 조회 | 분당 120회, job polling 포함 |
| 일반 변경 | 분당 30회 |
| URL 연결 확인·등록 재확인 | 합계 분당 5회 |
| 테스트 메일 | 분당 2회, 동일 idempotency 요청은 새 발송 아님 |
| Gmail 연결 시작 | 분당 5회 |

Gmail 자체 계정별 발송 한도는 다른 Gmail 사용량과 공유되므로 이 앱의 임의 상한과 별개다. 한도 초과를 연결 해제/기록 초기화로 처리하지 않는다. 영구 숫자를 문서에 추정하여 Gmail 보장으로 쓰지 않는다.

## 8. API 변경 관리

v1의 필수 필드 삭제·의미 변경은 UI/worker/DB와 함께 검토하고 버전을 변경한다. 선택 응답 필드 추가는 소비자 호환성을 확인한다. 코드 구현 시 OpenAPI 계약과 실제 schema를 함께 작성하되 현재 존재하지 않는 spec 파일을 완료로 기록하지 않는다.

## 부록. 검증 인계

인증·CSRF·version 충돌, URL SSRF/redirect, 동일 feed 중복·다중 feed 선택, 삭제 중 수집·발송, 제목 수정/전체 5유형, 0·20·21개, Gmail 토큰 철회·발송 unknown·worker 중단·테스트 분리, 로컬 reports 네트워크 부재를 후속 TC로 연결한다. 현재는 계약 초안 검토이며 API 서버나 Google OAuth 앱을 생성·호출한 결과가 아니다. [SAD 추적표](시스템아키텍처설계서-SAD.md#부록-a-요구사항--설계-연결)를 기준으로 RTM을 동기화한다.

### CR-IMP-001 라우팅 검증

한 Vercel 프로젝트(Beta)에 웹·FastAPI API를 배포하고 정기 실행 방식을 검증한 뒤 cookie·Set-Cookie·redirect·OAuth query 비밀·실제 APP_ORIGIN/CSRF·SSR·직접 backend URL 거절을 함께 확인한다. Python FastAPI의 기본 validation 응답은 공통 error envelope로 변환하고 JSON camelCase·If-Match·Idempotency-Key·API-001~022의 현재 범위는 유지한다. 이 기록은 배포/테스트 성공이 아니다.

### CR-MIN-001 최소 구현 기준

배포 구성·발송 최소화 범위는 서비스기획서의 CR-MIN-001 최소 구현 기준을 따른다.

단일 외부 호출·실패 이월·불명확 예약은 비즈니스정책서의 CR-MIN-001 규칙을 따른다.
