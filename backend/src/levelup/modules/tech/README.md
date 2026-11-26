# 기술블로그 모듈

현재는 구독·수집·글 조회·수동 상태·브리핑·Gmail·유한 스케줄 및 인증 API/화면을 연결했다. 등록 출처 계약, 검증 결과와 외부 환경에서 남은 확인은 [구현 진행 현황](../../../../../waterfall/04-구현/구현진행현황.md)을 기준으로 한다. 실발송은 기본 비활성이다.

- `adapters.py`: 삼성SDS/SK플래닛 고정 공개 목록 계약. 일반 RSS/Atom과 구분한다.
- `reading.py`, `digests.py`: owner/filter에 묶인 서명 커서·수동 상태 버전·읽기 전용 날짜별 브리핑.
- `mail.py`: 고정 전체 스냅샷·최신 20개 MIME·보내기 직전 재검사·단일 외부 요청·접수 불명 보류·늦은 접수 보존.
- `scheduler.py`: 매시·07:30·08:00 인증된 유한 실행. 응답 뒤 작업이나 상시 worker 없음.
- `../../api/{tech,gmail}.py`: 소유자/CSRF/쿼터·버전·비동기 작업/조회 계약.

아래는 2026-11-26 수집 코어 단계의 **과거 검증 기록**이다. 당시 미구현/미결 문구는 위 현황으로 대체한다.

# 구독·수집 코어와 DB 저장

## 상태와 범위

PRD 4.1.1~4.2, SRS FR-003~008, 상세설계 5.3~5.4 및 CR-FLOW-001을 따르는 독립 모듈이다. 화면·로그인 오류 복구·모바일 메뉴를 수정하는 작업과 분리했다. 수집 기능 전체나 운영 지원 출처가 완성된 상태는 아니다.

- `collection.py`: 연결 확인·복수 피드 후보 검증·등록 직전 선택 재검증·본문 재수집 조건.
- `feeds.py`: RSS 2.0/RSS 1.0/Atom 파싱, HTML alternate 피드 탐색, 날짜 정밀도·항목 오류 분리.
- `persistence.py`: 소유자별 구독 추가·중복 안내·끄기/켜기·소프트 삭제/재추가, epoch·작업의 원자 생성, 수집 슬롯·임대·heartbeat.
- `ingestion.py`: article/별칭/격리 저장, 항목 savepoint, generation·lease 검증과 원자적 완료, 알림 자격 보존.
- `worker.py`: 출처 session 잠금을 보유하는 유한 수집 작업 1회 실행, HTTP 중 행 transaction 해제, 임대 갱신·만료/오래된 결과 차단.
- `eligibility.py`: 최초 기준 제외, 재활성 구간 소급 억제, KST 최소 알림 날짜, 기존 상태·예약 보존, 출처 내 GUID/URL 별칭 충돌 판정.
- `../../infra/public_http.py`: 공개 목적지 검사, DNS 전체 응답 검사, 검증 IP 연결 고정·원래 TLS 호스트 검증, 리다이렉트 재검증, 프록시·쿠키·인증 전달 방지, 제한된 응답 읽기.

정상 빈 피드는 성공이며, 정상 항목과 오류가 섞인 피드는 partial이다. 모든 항목 무효·응답 손상·상한 초과를 성공으로 처리하거나 조용히 잘라내지 않는다. 날짜 누락·무효는 항목 격리 대신 publication precision으로 전달한다. 콘텐츠 종류에 따른 배제는 없다. 오류에는 정제 코드·강한 식별자 해시·내용 지문을 남기고, 원문 항목은 오류 객체에 보관하지 않는다.

## 연결 전 충족할 조건

DEC-003의 실제 기본 출처 표본, 피드 항목/후보 상한, 출처별 시간대·HTML 지원 범위는 여전히 미결이다. `FeedContract`는 검토한 상한을 필수 인자로 받으며 제품용 기본값을 임의로 제공하지 않는다. 날짜에 시간대가 없고 출처 시간대 계약도 없으면 `invalid`로 표시한다. HTML 피드 탐색은 UTF-8 문서를 지원하며 다른 인코딩은 실패로 보고한다. 사이트별 HTML 본문 수집기는 아직 등록하지 않았다.

HTTP 제한은 상세설계의 검토용 시작값(15초, 리다이렉트 3회, 압축 해제 본문 5MiB)을 적용했다. 압축 전 데이터도 5MiB를 넘으면 실패 처리한다. 동시 요청 2개 제한은 **공유한 SafePublicHTTP 인스턴스 안에서만** 적용된다. DB 작업 큐에는 소유자당 수집 슬롯 2개를 별도로 적용했다. 실제 배포 환경의 연결 고정·TLS·무료 자원 검증은 후속 작업이다. 일시 실패를 성공으로 바꾸거나 일반 fetch로 우회하지 않는다.

DB 구독/epoch·article/별칭·격리 저장, generation/lease 재검사, 잠금·트랜잭션·작업 큐를 구현했다. 매시/07:30 스케줄 진입점, 소유자 인증 API와 화면 연결은 미구현이다. 모듈 추가만으로 자동 수집·실발송·구독 등록이 활성화되지는 않는다. 호출자는 검증한 소유자 ID를 전달하고 출처별로 검토한 FeedContract를 사용해야 한다. 운영 출처별 계약 선택·등록은 DEC-003 표본 확인 후 연결한다.

## 검증 기록

2026-11-26, 저장된 합성 RSS/Atom/HTML fixture와 모의 DNS/HTTP/TCP·TLS 경계를 사용했다. 실제 외부 출처·Google·배포 환경에는 요청하지 않았다.

저장소 루트에서:

```sh
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/src
backend/.venv/bin/pytest backend/tests/test_collection.py backend/tests/test_public_http.py -q
backend/.venv/bin/pytest backend/tests -q
```

수집 코어 신규 테스트 67개 통과. 백엔드 전체 실행은 87개 통과·12개 건너뜀이었다. `TEST_DATABASE_URL`이 없어 기존 PostgreSQL 테스트 12개를 실행하지 않았으므로 전체 DB 검증 통과를 의미하지 않는다. 기존 Starlette/Authlib의 httpx 사용 중단 예정 경고 2개는 남아 있다.

검증 범위: 모든 DNS 응답·사설 주소·숫자 IP 별칭·리다이렉트 DNS 재바인딩, IP/Host/SNI 전달과 TLS 검증 설정, 전체 요청 기한·취소·동시 요청 제한, 압축 폭탄·절단·본문 상한, URL 로그 억제, XML DTD/외부 엔티티(UTF-16 포함), RSS/Atom·상대 URL·복수 피드·재검증, 전체 실패/부분 실패/빈 피드, 5가지 콘텐츠 유형, GUID/URL 식별 충돌, 초기/재활성/늦은 발견·날짜 누락·KST 경계·게시일 정정·예약 보존. DB 경합이나 실제 TLS 인증서 교환 성공을 대신하는 검증은 아니다.

## DB 통합 구현·검증 (2026-11-27)

`db/migrations/002_collection.sql`은 기존 인증 테이블 4개를 보존하며 구독·글·격리·작업 및 발송 예약 경계에 필요한 테이블 10개를 추가한다. 브리핑·메시지 저장 구조가 있다는 사실은 실제 Gmail 발송 구현을 의미하지 않는다. 기존 `001_identity.sql`은 수정하지 않았다.

구독은 소유자 session 잠금 → 출처 행 순으로 변경하며, 수집은 별도 namespace의 출처 session 잠금 → 출처 행 → 글 ID 순 행 잠금 → 작업 완료 순으로 반영한다. namespace는 owner=41082401, source=41082402, 수집 슬롯 집계=41082403이다. 후속 발송 구현에서도 동일 잠금 규약을 공유해야 한다. 직접/session 연결이 필수이며 transaction pooling 경로에서 그대로 실행하지 않는다. 잠금 해제를 확인하지 못한 연결은 폐기한다.

작업 임대 120초·heartbeat 30초·잠금 대기 2초는 상세설계의 검토용 시작값이다. 수집 슬롯은 소유자당 2개이며 메일 작업의 회수·실행에는 관여하지 않는다. 잠금 경합은 30초 뒤 대기 상태로 돌리고 즉시 무한 재시도하지 않는다. 실제 Schedules 실행·함수 시간 제한·DB 연결 수 검증은 남아 있다.

수집 전체 실패는 성공 시각·본문 검증자를 갱신하지 않는다. partial은 정상 항목과 격리를 함께 커밋하고, 이전 격리가 해결되지 않았으면 이후 피드에서 그 항목이 사라져도 완전 성공으로 표시하지 않는다. 정상 본문에서 사라진 ETag/Last-Modified는 지우며 304에서는 기존 값을 유지한다. 예상하지 못한 DB 제약 오류는 해당 시도 전체를 롤백하고 별도 실패 기록만 남긴다.

구독 끄기/삭제 시 미요청 메시지는 취소하고 해당 글의 예약을 해제·suppressed 처리한다. 이미 submitted/sending/unknown/accepted인 메시지와 held/consumed 예약, 과거 snapshot은 보존한다. 재활성·재추가는 새 epoch·기준 수집을 만들고 같은 source/article ID와 읽음·저장·숨김 상태를 보존한다. 초기 격리의 강한 식별자 복구는 최초 관측·baseline 표식을 유지한다.

격리한 로컬 PostgreSQL 17의 테스트별 UUID 스키마에서 DB 통합 테스트 **31개**, 기존 인증·수집 코어를 포함한 백엔드 전체 **134개**가 통과했다(건너뜀 없음). Ruff lint/format·mypy도 통과했다. 실제 출처 요청·배포·화면 E2E는 이번 DB 변경 검증에 포함하지 않았다. Starlette/Authlib의 기존 경고 2개는 남아 있다.

```sh
# 생성한 임시 PostgreSQL 테스트 클러스터에서 검증한 예시다. 운영 DB를 지정하지 않는다.
TEST_DATABASE_URL=postgresql+psycopg://levelup@127.0.0.1:55433/postgres backend/.venv/bin/pytest backend/tests -q
```

추가 검증: 동시 중복 등록, 활성 epoch 고유성, 소유자·version 경계, 삭제/재추가·수동 상태 보존, 출처 실패 격리, 초기 부분 실패·오류 복구, 식별 충돌 savepoint, 수집 중 삭제, 임대 만료/재회수·stale commit 차단, 동시 claim의 두 슬롯 상한, 메일 job 분리, 발송 전 취소/요청 후 보존, 게시일 정정, 재구독 소급 억제, 전체 DB 롤백, 인증 전용 DB에서 마이그레이션 후 기존 소유자·세션·checksum 보존. 임시 테스트 서버는 검증 후 종료했다.

## 구현 근거

- [HTTPCore SNI 확장](https://www.encode.io/httpcore/extensions/#sni_hostname): 검증한 IP로 연결하면서 원래 호스트의 TLS 인증서 검증을 유지한다. 현재 설치된 HTTPX/HTTPCore 전달 경로도 확인했다.
- [Python XML 보안](https://docs.python.org/3.12/library/xml.html#xml-vulnerabilities): 크기 제한과 함께 XML parser의 doctype 콜백에서 DTD를 거절한다.
- [PostgreSQL 잠금](https://www.postgresql.org/docs/17/explicit-locking.html): session advisory 잠금과 transaction 행 잠금의 수명을 구분한다. 큐 claim에만 `SKIP LOCKED`를 사용한다.
