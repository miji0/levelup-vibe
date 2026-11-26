# LevelUp

개인용 기술 동향 웹사이트입니다. Next.js 화면과 Python FastAPI를 한 Vercel Services 프로젝트로 구성합니다.

현재 구현: 소유자 Google 로그인·7일 고정 세션, 구독·공개 RSS/Atom/등록 출처 수집, 오늘/전체/저장 글과 독립 읽음·숨김, 아침 브리핑 전체 스냅샷과 Gmail 발송·설정·상태, URL→요청문 복사→외부 AI 수동 인계, Schedules 유한 배치와 암호화 백업/복원입니다. **기본 실발송은 꺼져 있으며 실제 Google·클라우드 배포 인수는 남아 있습니다.** [현재 단계와 남은 순서](waterfall/04-구현/구현진행현황.md)를 확인하세요.

## 개발 환경

Node.js 24 LTS, Python 3.12, pnpm 12.18.0, uv 0.10.8, PostgreSQL 17을 사용합니다. 웹과 Python 의존성은 각각 lockfile로 고정합니다.

```sh
pnpm --dir apps/web install --frozen-lockfile
uv sync --project backend --frozen
docker compose up -d db
cp backend/.env.example backend/.env
```

`backend/.env`의 Google client ID/secret, 고정 소유자 Google sub·이메일, 토큰 암호화 키를 설정하세요. 키 생성 명령은 예시 파일에 있습니다. 소유자는 Google sub로 판정하고 이메일만 일치한다고 허용하지 않습니다. 파일·로그·클라이언트 환경변수에 비밀값을 넣지 마세요.

Google의 로컬 콜백 URI는 `http://localhost:3000/api/auth/callback/google`과 `http://localhost:3000/api/v1/integrations/gmail/callback` 두 개입니다. 앱 origin과 콜백은 정확히 일치해야 합니다. 외부 주소에는 HTTPS가 필수이며 localhost 개발에서만 비보안 cookie를 사용합니다. 환경 설정이 없으면 로그인은 503으로 닫히며 인증 우회 모드는 없습니다.

```sh
cd backend
uv run python -m levelup.migrate
uv run uvicorn levelup.api.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

다른 터미널에서 실행합니다.

```sh
pnpm --dir apps/web dev
```

`http://localhost:3000`을 엽니다. 개발용 Next.js가 `/api/*`를 고정 loopback Python 서버로 전달합니다. OAuth code가 접근 로그에 남지 않도록 위 명령의 `--no-access-log`를 유지하세요.

## 데이터베이스

`db/migrations/001_identity.sql`은 owner_settings·oauth_states·auth_sessions·gmail_connections 네 업무 테이블을 만듭니다. `002_collection.sql`은 나머지 업무 테이블을 추가하며 `003_request_limits.sql`은 별도의 단기 API 쿼터 카운터입니다. `schema_migrations`는 14개 업무 테이블에 포함되지 않는 적용 버전 관리 테이블입니다.

마이그레이션은 명시적으로 실행하며 적용된 SQL의 checksum을 확인합니다. 기존 migration 파일은 수정하지 않고 후속 파일을 추가합니다. 소유자 설정이 기존 DB와 다르면 자동 교체하지 않습니다. 운영 DB에는 테스트 URL을 사용하지 마세요.

## 자동 검사

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

DB 테스트는 `TEST_DATABASE_URL`에 임시 UUID 스키마를 만들고 종료 시 제거합니다. 전용 로컬/테스트 DB만 지정하세요. 이 변수가 없으면 DB 테스트는 skip되므로 전체 검증 완료로 볼 수 없습니다.

```sh
pnpm --dir apps/web exec playwright install chromium webkit
TEST_DATABASE_URL=postgresql+psycopg://levelup:levelup@127.0.0.1:5432/levelup pnpm --dir apps/web test:e2e --workers=1
```

E2E는 자체 웹·API 서버를 시작하므로 기본 3000/8000 포트를 비워 두세요. 기존 개발 서버와 병행하려면 `E2E_WEB_PORT=3001 E2E_API_PORT=8001 E2E_DIST_DIR=.next-e2e`를 함께 지정하세요. 테스트 전용 모듈만 가짜 Google 공급자를 주입하며 실제 FastAPI·PostgreSQL·cookie 흐름을 통과합니다. 프로덕션 진입점은 이 모듈을 import하지 않습니다. Chromium 1280px와 WebKit 390px를 검사하며 실제 Google 연결·Mac Chrome·iPhone Safari 실기기 검증은 별도입니다.

GitHub Actions에는 같은 검사 명령을 구성했습니다. workflow 작성과 원격 CI 실행 성공은 구분합니다.

## 배포와 남은 검증

루트 `vercel.json`이 웹과 Python 서비스를 정의하며 `/api/*`를 Python으로 고정 라우팅합니다. 배포 환경에는 실제 HTTPS `APP_ORIGIN`, Google 운영 callback과 서버 비밀값을 설정해야 합니다. DB schema 적용은 별도로 수행합니다. 배포 전에 Vercel Services의 패키지 설치·라우팅·Set-Cookie·무료 한도를 실제 확인하세요. 외부 연결과 배포는 아직 실행하지 않았습니다.

[확정 설계와 착수 승인](waterfall/08-검토/단계별검토-체크리스트.md)을 따릅니다. 실제 운영 수집·Gmail 발송·클라우드 백업 검증과  Figma Pretendard 교체와 UI 실기기 검증은 인수 전 조건으로 남아 있습니다. 브랜치·커밋·push는 자동 수행하지 않습니다.

## 공통 화면 검증

로그인·첫 방문 홈·설정 기반의 Figma 대조와 다크/라이트·1280/390 캡처 결과는 [구현 인계 3.4](waterfall/04-구현/구현-테스트-인계서.md#34-공통-화면로그인-ux-보완-2026-11-27)에 기록합니다. E2E는 `apps/web/test-results/`에 캡처를 재생성합니다. `apps/web/public/figma/`는 소유자의 Figma 목업에서 내보낸 SVG입니다. 구독·Gmail 제어는 API와 연결되어 있습니다. 실발송 비활성·연결 해제·버전 충돌·실패는 서버 결과대로 표시합니다. 새 기능의 화면 비교 기록은 [구현 진행 현황](waterfall/04-구현/구현진행현황.md)에 있습니다.


## 정기 실행과 실발송

`vercel.json`의 Vercel Schedules(Beta)는 한국 시간 매시·07:30·08:00, 총 3개입니다. 서버의 `CRON_SECRET`(16자 이상 난수)와 Vercel path target의 Bearer 인증을 사용합니다. 비밀값을 쿼리에 넣지 마세요. `ce-vssscheduledat`으로 원래 예약 시각을 읽고 실제 시각과 비교합니다. Hobby의 최대 15분 시작 분산을 수용하며 첫 스냅샷 시작이 08:20 이후면 missed 처리합니다. 요청 중 늦게 온 접수는 보존합니다.

상시 worker/응답 후 무한 루프는 없습니다. 호출당 수집 슬롯 2개·메일 슬롯 1개를 사용하고 최대 240초 유한 배치로 대기 작업을 처리합니다. 종료 시 남은 작업·임대는 다음 실행에서 복구합니다. 일반 등록의 초기 수집은 다음 스케줄에서 실행됩니다. 테스트 메일은 같은 idempotency key의 단일 작업을 요청 중 유한 처리합니다. 기본 `MAIL_DELIVERY_ENABLED=false`이면 Google에 발송 요청하지 않고 실패 사유를 남깁니다. 실제 운영 자원 한도·5개 출처 동시 처리 시간은 배포 후 확인해야 합니다.

수동 로컬 스케줄 검증은 실제 환경 대신 테스트 DB에서 `backend/tests/test_scheduler.py`를 실행하세요. 운영 endpoint 수동 호출은 실발송/수집을 발생시킬 수 있습니다.

## 백업·복원과 접수 불명 처리

PostgreSQL 17 클라이언트가 필요합니다. macOS는 `brew install libpq@17` 후 `PATH=/opt/homebrew/opt/libpq@17/bin:$PATH`를 해당 명령에 지정할 수 있습니다. 전체 백업 통합 테스트는 전용 테스트 DB 안에서 임시 데이터베이스 두 개를 만들고 제거하므로 테스트 계정에 CREATEDB 권한도 필요합니다.

비공개 저장소에서 Artifact 보관 한도 400일을 허용하고, 서버용 `BACKUP_DATABASE_URL`(직접 PostgreSQL 연결), 별도 32바이트 base64 `BACKUP_ENCRYPTION_KEY` secrets와 `BACKUP_ENABLED=true` repository variable을 설정하세요. 공개 저장소에서는 백업 workflow가 실행되지 않습니다. 키는 토큰 암호화 키와 별도로 생성·보관하며 저장소/Artifact에 넣지 않습니다. 매주 월요일 03:00 한국 시간에 실행하며 새 백업을 업로드한 뒤 다운로드·동일 바이트·복호화·archive를 검증하고 최근 성공본 4개로 정리합니다. 400일을 넘긴 Artifact는 자동 만료됩니다. 로컬 plaintext와 암호화 결과는 Git에 넣지 않습니다.

```sh
cd backend
uv run python -m levelup.backup create /private/tmp/levelup-backup.lup
uv run python -m levelup.backup verify /private/tmp/levelup-backup.lup
# RESTORE_DATABASE_URL은 반드시 별도의 비어 있는 격리 DB. 운영 URL로 복원하지 마세요.
uv run python -m levelup.backup restore /private/tmp/levelup-backup.lup --isolated-target
```

복원 검증 중에는 `MAIL_DELIVERY_ENABLED=false`, Schedules 비활성 상태를 유지합니다. 마지막 백업 이후 이미 접수된 메일은 백업에 없을 수 있으므로 운영 전환 전에 소유자가 Gmail의 Message-ID와 최신 기록을 대조하고 누락 접수를 반영해야 합니다. 복원만으로 발송을 자동 재개하지 마세요.

Gmail 접수 불명은 보낸편지함에서 MIME Message-ID·제목·수신자·시각을 직접 대조합니다. 단순히 메일이 안 보인다는 이유로 미접수를 확정하지 않습니다. 서버 운영자의 OP-01 명령은 메일을 보내지 않으며 확인 메모와 결과만 남깁니다.

```sh
cd backend
uv run python -m levelup.verify_delivery --delivery UUID --outcome unresolved --note '확인 근거 위치'
# 확실한 접수: confirmed_accepted + --provider-id 실제GmailID
# 확실한 미접수: confirmed_not_accepted. 유효한 미발송 글은 다음 아침 후보로만 반환합니다.
```

`/privacy`는 로그인 없이 계정·발송 권한·저장·리포트 인계를 안내합니다. OAuth 공개 설정의 실제 도메인/개인정보 URL 등록은 운영 환경에서 확인하세요.
