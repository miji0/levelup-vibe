# LevelUp

> 국내 기업 기술블로그의 새 글을 모아 **매일 아침 8시에 Gmail로 보내 주는** 나만의 기술 동향 사이트

> 소유자 Google 계정만 로그인할 수 있는 서비스로 직접 접근이 불가능합니다. 기술블로그 목록·구독 설정·수집·발송 상태·메일 발송 확인 화면은 운영 중인 서비스를 직접 캡처했습니다(계정 정보는 가렸습니다).

<p align="center">
  <img src="docs/screenshots/tech-list-dark.png" alt="기술블로그 글 목록 다크 모드" width="860">
</p>

## 배경

- 기업별 기술블로그를 하나씩 찾아가 새 글을 확인하는 일이 반복되어 번거로웠습니다.
- 읽고 싶은 문서를 AI에게 요약시킬 때마다 요청문을 새로 쓰는 일도 줄이고 싶었습니다.
- 앞으로 다른 생활·업무 기능을 같은 사이트에 섹션으로 붙일 수 있게 만들었습니다.

## 주요 기능

| 기능 | 설명 |
|---|---|
| 소유자 전용 로그인 | Google 로그인 후 **Google 계정 고유 ID(sub)** 로 소유자를 판정하고, 로그인부터 7일 고정 세션을 사용합니다. 공개 가입은 없습니다. |
| 구독 출처 관리 | 블로그 주소나 RSS·Atom 주소를 넣으면 연결을 확인하고 피드를 찾아 등록합니다. 국내 기업 5곳을 기본 후보로 둡니다. |
| 기술블로그 목록 | 오늘의 글·전체 글·저장한 글을 보여 주고, 읽음·저장·목록 숨김은 서로 독립으로 관리합니다. 제목 검색과 출처·읽음 필터를 지원합니다. |
| 아침 브리핑 | 매일 08:00(시작 마감 08:20)에 그날의 새 글을 Gmail로 보냅니다. 처음 등록할 때 가져온 글은 기준선으로만 저장해 알림에서 제외합니다. |
| 수집·발송 상태 | 출처별 마지막 수집 결과, 최근 7일 브리핑, 이메일 발송 기록을 한 화면에서 확인합니다. |
| 리포트 분석 | 공개 웹페이지나 텍스트형 PDF의 URL로 요약 요청문을 만들고, ChatGPT·Claude에서 직접 실행하도록 연결합니다. 계정 비밀번호와 API 키는 받지 않습니다. |
| 백업·복원 | 데이터베이스를 암호화해 주간 백업하고, 격리된 DB에 복원해 검증하는 절차를 갖췄습니다. |

## 화면

| 구독 설정 (실제 5곳 수집 중) | 수집·발송 상태 |
|---|---|
| ![구독 설정 화면](docs/screenshots/subscriptions.png) | ![수집·발송 상태 화면](docs/screenshots/status.png) |

| 로그인 | 리포트 분석 |
|---|---|
| ![로그인 화면](docs/screenshots/login.png) | ![리포트 분석 화면](docs/screenshots/reports.png) |

**실제 Gmail 발송 확인**: 설정 화면에서 보낸 테스트 메일이 받은편지함에 도착했고(위), 앱의 이메일 발송 기록에도 "Gmail 접수"로 남았습니다(아래).

<p>
  <img src="docs/screenshots/test-mail.png" alt="받은편지함에 도착한 테스트 메일" width="640">
</p>

<p>
  <img src="docs/screenshots/email-log.png" alt="수집·발송 상태의 이메일 발송 기록" width="640">
</p>

**다크 모드와 모바일**(Mac Chrome 1280px · iPhone Safari 390px 기준으로 만들고, 캡처는 자동 테스트가 두 테마·두 화면 크기로 생성합니다)

<p>
  <img src="docs/screenshots/tech-list.png" alt="기술블로그 목록 라이트 모드" width="520">
  <img src="docs/screenshots/mobile-tech.png" alt="기술블로그 목록 모바일" width="160">
  <img src="docs/screenshots/mobile-tech-dark.png" alt="기술블로그 목록 모바일 다크 모드" width="160">
</p>

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 웹 | Next.js 16, TypeScript, Figma 목업 기준 구현 |
| API·수집 | Python 3.12, FastAPI, RSS·Atom·HTML 파서, Gmail API |
| 데이터베이스 | PostgreSQL 17(Neon Free), 되돌릴 수 없는 SQL 마이그레이션 |
| 배포·운영 | Vercel Services(웹과 API 한 프로젝트), Vercel Schedules, GitHub Actions 주간 백업 |
| 품질 | pytest, Playwright(Chromium·WebKit), ruff, mypy, ESLint, Vitest |

월 운영비 0원을 목표로 무료 한도 안에서 구성했습니다.

## 폴더 구조

```text
levelup-vibe/
├── apps/web/                    웹 화면 (Next.js, TypeScript)
│   ├── src/app/                 페이지: login, tech(글·구독·상태), reports, settings, privacy
│   ├── src/modules/             기능별 화면 코드 (tech, reports)
│   ├── src/core/                공통 코드: 레이아웃, 테마, 아이콘, API 호출
│   └── public/figma/            Figma 목업에서 내보낸 SVG
├── backend/                     API·수집 서버 (Python, FastAPI)
│   ├── main.py                  Vercel 진입점
│   ├── src/levelup/api/         HTTP 엔드포인트
│   ├── src/levelup/modules/tech/  피드 수집, 브리핑, 메일 발송, 스케줄러
│   ├── src/levelup/infra/       DB, Google·Gmail 연동, 안전한 외부 요청
│   ├── src/levelup/core/        설정, 보안
│   └── tests/                   pytest 테스트와 샘플 피드(fixtures)
├── db/migrations/               SQL 마이그레이션 (001~003)
├── tests/e2e/                   Playwright 브라우저 테스트
├── waterfall/                   단계별 산출물 (00 기획 ~ 08 검토)
├── docs/screenshots/            README 화면 캡처
├── .github/workflows/           CI 검사, 주간 DB 백업
├── vercel.json                  Vercel 배포와 정기 실행(Schedules) 설정
├── compose.yaml                 로컬 개발용 PostgreSQL
└── PRD.md · DESIGN.md · AGENTS.md   제품 요구사항 · Figma 참고 · 저장소 작업 규칙
```

## 문서 둘러보기

| 단계 | 문서 |
|---|---|
| 기획·요구사항 | [PRD](PRD.md), [요구사항 명세서](waterfall/01-요구사항분석/요구사항명세서-SRS.md) |
| 설계 | [시스템 아키텍처](waterfall/02-시스템설계/시스템아키텍처설계서-SAD.md), [API 설계서](waterfall/02-시스템설계/API설계서.md), [DB 설계서](waterfall/02-시스템설계/데이터베이스설계서.md), [화면 설계서](waterfall/02-시스템설계/화면설계서.md) |
| 구현·테스트 | [구현 진행 현황](waterfall/04-구현/구현진행현황.md), [테스트 결과 보고서](waterfall/05-테스트/테스트결과보고서.md) |
| 배포·운영 | [배포 계획서](waterfall/06-배포/배포계획서.md), [운영 가이드](waterfall/06-배포/운영가이드.md), [유지보수 계획서](waterfall/07-유지보수/유지보수계획서.md) |

## 현재 상태

| 구분 | 내용 |
|---|---|
| 구현·동작 중 | 소유자 Google 로그인과 7일 고정 세션 · 구독 출처 수집(RSS·Atom·등록 출처) · 오늘/전체/저장 글과 독립 읽음·숨김 · 아침 브리핑과 Gmail 발송 · 리포트 분석(요청문 복사 후 외부 AI 수동 인계) · 정기 수집 · 암호화 백업/복원 |
| 운영 | Vercel에 배포되어 매시 수집이 동작합니다. Google OAuth 앱을 프로덕션으로 게시했고 실제 Gmail 발송을 켜 두었습니다. 테스트 메일이 받은편지함에 도착하는 것까지 확인했습니다. |
| 남은 검증 | 정기 브리핑(매일 08:00) 도착 확인 · 게시 8일 후 Gmail 연결 재확인 · 클라우드 백업 복원 연습 · Pretendard 폰트 교체 · iPhone Safari 등 실기기 확인 · 7일 시범 운영 |

정기 브리핑 확인과 7일 시범 운영이 남아 있어 정식 출시 승인은 아직 하지 않았습니다. 현재 단계와 남은 순서는 [구현 진행 현황](waterfall/04-구현/구현진행현황.md)과 [단계별 검토 체크리스트](waterfall/08-검토/단계별검토-체크리스트.md)에 있습니다.

## 개발·운영 안내

설치·실행·검사 명령과 배포, 정기 실행, 백업·복원 절차입니다.

<details>
<summary><b>개발 환경 · 데이터베이스 · 자동 검사 · 배포 · 정기 실행 · 백업·복원 · 화면 검증 (펼치기)</b></summary>

## 개발 환경

| 도구 | 버전 |
|---|---|
| Node.js | 24 LTS |
| Python | 3.12 |
| pnpm | 12.18.0 |
| uv | 0.10.8 |
| PostgreSQL | 17 |

웹과 Python 의존성은 각각 lockfile로 고정합니다.

**1. 설치**

```sh
pnpm --dir apps/web install --frozen-lockfile
uv sync --project backend --frozen
docker compose up -d db
cp backend/.env.example backend/.env
```

**2. 환경변수 설정**: `backend/.env`에 Google client ID/secret, 소유자 Google sub·이메일, 토큰 암호화 키를 넣습니다. 키 생성 명령은 예시 파일에 있습니다.

- 소유자는 **Google sub**로 판정하며 이메일만 같다고 허용하지 않습니다.
- 비밀값을 파일·로그·클라이언트 환경변수에 넣지 마세요.
- 환경 설정이 없으면 로그인은 503으로 닫히고, 인증 우회 모드는 없습니다.

**3. Google 콜백 주소**(로컬): 앱 주소와 정확히 일치해야 합니다. 외부 주소는 HTTPS가 필수이고, 비보안 쿠키는 localhost 개발에서만 씁니다.

- `http://localhost:3000/api/auth/callback/google`
- `http://localhost:3000/api/v1/integrations/gmail/callback`

**4. DB 마이그레이션과 API 서버 실행**

```sh
cd backend
uv run python -m levelup.migrate
uv run uvicorn levelup.api.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

OAuth code가 접근 로그에 남지 않도록 `--no-access-log`를 유지하세요.

**5. 웹 실행**(다른 터미널)

```sh
pnpm --dir apps/web dev
```

`http://localhost:3000`을 엽니다. 개발용 Next.js가 `/api/*`를 로컬 Python 서버로 전달합니다.

## 데이터베이스

| 마이그레이션 | 내용 |
|---|---|
| `001_identity.sql` | owner_settings · oauth_states · auth_sessions · gmail_connections (4개 업무 테이블) |
| `002_collection.sql` | 나머지 업무 테이블 |
| `003_request_limits.sql` | 단기 API 쿼터 카운터(업무 테이블과 별개) |

`schema_migrations`는 14개 업무 테이블에 포함되지 않는 적용 버전 관리 테이블입니다.

- 마이그레이션은 직접 실행하고, 적용된 SQL의 checksum을 확인합니다.
- 기존 파일은 고치지 않고 후속 파일을 추가합니다.
- 소유자 설정이 기존 DB와 다르면 자동으로 바꾸지 않습니다.
- 운영 DB에는 테스트 URL을 쓰지 마세요.

## 자동 검사

**백엔드와 웹 검사**

```sh
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/src
TEST_DATABASE_URL=postgresql+psycopg://levelup:levelup@127.0.0.1:5432/levelup backend/.venv/bin/pytest backend/tests -q
pnpm --dir apps/web lint
pnpm --dir apps/web typecheck
pnpm --dir apps/web test
pnpm --dir apps/web build
```

- DB 테스트는 `TEST_DATABASE_URL`에 임시 UUID 스키마를 만들고 끝나면 지웁니다. **전용 로컬/테스트 DB만** 지정하세요.
- 이 변수가 없으면 DB 테스트가 건너뛰어지므로 전체 검증을 마친 것으로 보지 않습니다.

**E2E 테스트**(Playwright: Chromium 1280px, WebKit 390px)

```sh
pnpm --dir apps/web exec playwright install chromium webkit
TEST_DATABASE_URL=postgresql+psycopg://levelup:levelup@127.0.0.1:5432/levelup pnpm --dir apps/web test:e2e --workers=1
```

- E2E가 자체 웹·API 서버를 시작하므로 3000/8000 포트를 비워 두세요. 개발 서버와 함께 쓰려면 `E2E_WEB_PORT=3001 E2E_API_PORT=8001 E2E_DIST_DIR=.next-e2e`를 같이 지정합니다.
- 가짜 Google 공급자는 테스트 전용 모듈에서만 주입하고, 실제 FastAPI·PostgreSQL·쿠키 흐름을 통과합니다. 운영 진입점은 이 모듈을 가져오지 않습니다.
- 실제 Google 연결, Mac Chrome, iPhone Safari 실기기 검증은 별도입니다.

GitHub Actions에도 같은 검사를 구성했습니다. 워크플로 작성과 원격 CI 실행 성공은 구분합니다.

## 배포

루트 `vercel.json`이 웹과 Python 서비스를 정의하고 `/api/*`를 Python으로 보냅니다.

- 배포 환경에는 실제 HTTPS `APP_ORIGIN`, Google 운영 콜백, 서버 비밀값을 설정해야 합니다. `APP_ORIGIN`이 없으면 API가 시작할 때 실패합니다.
- DB 스키마 적용은 배포와 별도로 수행합니다.
- 절차는 [배포 계획서](waterfall/06-배포/배포계획서.md)와 [운영 가이드](waterfall/06-배포/운영가이드.md)를 따릅니다.

## 정기 실행과 실발송

Vercel Schedules(Beta) 3개가 한국 시간 기준으로 돌아갑니다.

| 작업 | 시각 | 하는 일 |
|---|---|---|
| hourly | 매시 정각 | 구독 출처 수집과 대기 작업 처리 |
| final | 07:30 | 브리핑 전 최종 수집 |
| digest | 08:00 | 아침 브리핑 생성과 발송(시작 마감 08:20) |

- **인증**: 서버의 `CRON_SECRET`(16자 이상 난수)과 Vercel의 Bearer 인증을 씁니다. 비밀값을 쿼리에 넣지 마세요.
- **지연 처리**: 무료(Hobby) 플랜은 시작이 최대 15분 늦어질 수 있어 이를 받아들입니다. `ce-vssscheduledat` 헤더로 원래 예약 시각을 읽어 실제 시각과 비교하고, 첫 스냅샷 시작이 08:20 이후면 missed로 처리합니다. 요청 중 늦게 들어온 접수는 보존합니다.
- **유한 배치**: 상시 worker나 응답 뒤 무한 루프가 없습니다. 호출당 수집 슬롯 2개, 메일 슬롯 1개로 최대 240초 안에 처리하고, 남은 작업은 다음 실행에서 이어 갑니다.
- **초기 수집**: 일반 등록의 첫 수집은 다음 스케줄에서 실행됩니다. 테스트 메일은 같은 idempotency key의 단일 작업을 요청 중에 처리합니다.
- **실발송 스위치**: `MAIL_DELIVERY_ENABLED=false`(기본)면 Google에 발송을 요청하지 않고 실패 사유만 남깁니다.
- **확인할 것**: 실제 운영 자원 한도와 5개 출처 동시 처리 시간은 배포 후 확인해야 합니다.

로컬에서 스케줄을 검증하려면 운영 대신 테스트 DB에서 `backend/tests/test_scheduler.py`를 실행하세요. **운영 endpoint를 손으로 호출하면 실제 수집과 발송이 일어날 수 있습니다.**

## 백업·복원

**설정**(비공개 저장소 기준)

| 항목 | 값 |
|---|---|
| 저장소 설정 | Artifact 보관 한도 400일 허용 |
| Secrets | `BACKUP_DATABASE_URL`(직접 PostgreSQL 연결), `BACKUP_ENCRYPTION_KEY`(32바이트 base64) |
| Variable | `BACKUP_ENABLED=true` |
| 실행 | 매주 월요일 03:00 한국 시간 |
| 검증 | 업로드 후 다운로드 · 동일 바이트 · 복호화 · archive 확인 |
| 보관 | 최근 성공본 4개, 400일이 지나면 자동 만료 |

- 공개 저장소에서는 백업 워크플로가 실행되지 않습니다.
- 백업 키는 토큰 암호화 키와 **따로** 만들어 보관하고, 저장소와 Artifact에 넣지 않습니다.
- 로컬의 평문·암호화 결과는 Git에 올리지 마세요.
- PostgreSQL 17 클라이언트가 필요합니다. macOS는 `brew install libpq@17` 후 `PATH=/opt/homebrew/opt/libpq@17/bin:$PATH`를 명령에 지정합니다.
- 전체 백업 통합 테스트는 임시 DB 2개를 만들고 지우므로 테스트 계정에 CREATEDB 권한이 필요합니다.

**명령**

```sh
cd backend
uv run python -m levelup.backup create /private/tmp/levelup-backup.lup
uv run python -m levelup.backup verify /private/tmp/levelup-backup.lup
# RESTORE_DATABASE_URL은 반드시 별도의 비어 있는 격리 DB. 운영 URL로 복원하지 마세요.
uv run python -m levelup.backup restore /private/tmp/levelup-backup.lup --isolated-target
```

**복원할 때 주의**

- 복원 검증 중에는 `MAIL_DELIVERY_ENABLED=false`와 Schedules 비활성 상태를 유지합니다.
- 마지막 백업 이후 이미 접수된 메일은 백업에 없을 수 있습니다. 운영 전환 전에 Gmail의 Message-ID와 최신 기록을 대조해 누락을 반영하세요.
- 복원만으로 발송을 자동 재개하지 마세요.

## 접수 불명 발송 처리

Gmail이 메일을 접수했는지 알 수 없을 때는 보낸편지함에서 Message-ID·제목·수신자·시각을 직접 대조합니다. 메일이 안 보인다는 이유만으로 미접수로 확정하지 않습니다. 아래 운영 명령은 메일을 보내지 않고 확인 메모와 결과만 남깁니다.

```sh
cd backend
uv run python -m levelup.verify_delivery --delivery UUID --outcome unresolved --note '확인 근거 위치'
# 확실한 접수: confirmed_accepted + --provider-id 실제GmailID
# 확실한 미접수: confirmed_not_accepted. 유효한 미발송 글은 다음 아침 후보로만 반환합니다.
```

## 화면 검증과 기타 안내

- **화면 검증 기록**: 로그인·첫 방문 홈·설정의 Figma 대조와 다크/라이트·1280/390 캡처 결과는 [구현 인계 3.4](waterfall/04-구현/구현-테스트-인계서.md#34-공통-화면로그인-ux-보완-2026-11-27)에 있습니다. 새 기능의 비교 기록은 [구현 진행 현황](waterfall/04-구현/구현진행현황.md)에 있습니다.
- **캡처 재생성**: E2E를 실행하면 `apps/web/test-results/`에 캡처가 다시 만들어집니다.
- **Figma 자료**: `apps/web/public/figma/`는 소유자의 Figma 목업에서 내보낸 SVG입니다.
- **화면 동작**: 구독·Gmail 제어는 API와 연결되어 있고, 실발송 비활성·연결 해제·버전 충돌·실패는 서버 결과대로 보여 줍니다.
- **개인정보 안내**: `/privacy`는 로그인 없이 계정·발송 권한·저장·리포트 인계를 설명합니다. OAuth 공개 설정의 도메인과 개인정보 URL 등록은 운영 환경에서 확인하세요.
- **Git 작업**: 브랜치·커밋·push는 자동으로 수행하지 않습니다.

</details>
