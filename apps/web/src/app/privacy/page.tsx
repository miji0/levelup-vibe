import Link from "next/link";
export default function PrivacyPage() {
  return (
    <main className="content" id="main-content">
      <div className="page-heading">
        <h1>개인정보 및 Google 계정 권한 안내</h1>
        <p>LevelUp은 지정된 소유자 한 명이 사용하는 개인 웹사이트입니다.</p>
      </div>
      <section className="feature-section">
        <h2>계정과 Gmail</h2>
        <p>
          Google 계정 식별자·이메일은 소유자 로그인 확인에 사용합니다. 허용한
          경우 Gmail 발송 권한만 사용하여 같은 계정으로 아침 브리핑과 테스트
          메일을 보냅니다. 받은편지함·외부 AI 대화 내용은 읽지 않습니다.
        </p>
        <h2>저장 및 해제</h2>
        <p>
          로그인 세션은 7일간 유지됩니다. 발송 토큰은 서버에서 암호화해 저장하며
          브라우저에 제공하지 않습니다. 설정에서 Gmail 연결을 해제하면 저장된
          발송 토큰을 삭제합니다. 기존 글·읽음·저장·브리핑 기록은 보존합니다.
          Google 계정의 연결 앱 설정에서도 권한을 철회할 수 있습니다.
        </p>
        <h2>리포트 분석</h2>
        <p>
          URL과 요청문은 화면에서만 편집하며 분석 이력으로 보관하지 않습니다.
          복사 후 ChatGPT·Claude에서 직접 실행하며 각 서비스의 정책이
          적용됩니다. 마지막 AI 서비스 선택만 브라우저에 저장할 수 있습니다.
        </p>
        <h2>보관 및 문의</h2>
        <p>
          글·출처·사용 상태·발송 중복 방지 기록은 자동 삭제하지 않습니다. 사이트
          소유자는 운영 데이터베이스와 암호화 백업을 직접 관리하며 프로젝트
          저장소를 통해 삭제·보안 문의를 접수합니다. 제삼자 광고·판매 용도로
          데이터를 제공하지 않습니다.
        </p>
        <Link href="/login">로그인으로 돌아가기</Link>
      </section>
    </main>
  );
}
