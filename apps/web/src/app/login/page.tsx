import { Brand, GoogleIcon, Icon } from "@/core/icon";
const errors: Record<string, { title: string; message: string }> = {
  OWNER_ONLY: {
    title: "소유자 계정만 이용할 수 있습니다",
    message: "등록한 소유자 Google 계정으로 다시 로그인해주세요.",
  },
  OAUTH_STATE_INVALID: {
    title: "로그인 요청이 만료되었습니다",
    message:
      "이전에 시작한 요청은 다시 사용할 수 없습니다. 로그인을 다시 시작해주세요.",
  },
  OAUTH_CANCELLED: {
    title: "로그인이 취소되었습니다",
    message: "계속 이용하려면 Google 로그인을 다시 시작해주세요.",
  },
  OAUTH_INVALID: {
    title: "Google 인증을 확인하지 못했습니다",
    message: "인증 결과가 유효하지 않습니다. 다시 로그인해주세요.",
  },
  OAUTH_UNAVAILABLE: {
    title: "Google에 연결하지 못했습니다",
    message: "잠시 후 다시 로그인해주세요.",
  },
  SETUP_REQUIRED: {
    title: "로그인 설정이 필요합니다",
    message: "서비스 연결 설정을 완료한 뒤 다시 시도해주세요.",
  },
};
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ returnTo?: string; error?: string }>;
}) {
  const { returnTo = "/", error } = await searchParams;
  const problem =
    error && Object.hasOwn(errors, error) ? errors[error] : undefined;
  return (
    <main className="login-page" id="main-content">
      <section className="login-panel" aria-labelledby="login-title">
        <Brand />
        <div className="login-title-block">
          <h1 id="login-title">개인 사이트에 로그인</h1>
          <p>
            소유자 Google 계정만 이용할 수 있습니다. 로그인하면 보던 화면으로
            돌아갑니다.
          </p>
        </div>
        {problem && (
          <div role="alert" className="error-callout">
            <Icon name="warning" />
            <div>
              <strong>{problem.title}</strong>
              <p>{problem.message}</p>
            </div>
          </div>
        )}
        <a
          className="primary google-button"
          href={`/api/auth/signin?returnTo=${encodeURIComponent(returnTo)}`}
        >
          <GoogleIcon />
          {problem ? "다른 Google 계정으로 로그인" : "Google로 로그인"}
        </a>
        <p className="caption">
          처음 로그인할 때 같은 계정의 Gmail 발송 권한을 함께 요청합니다.
          받은편지함은 읽지 않습니다.
        </p>
        <p className="caption">
          공개 가입과 비밀번호 재설정은 제공하지 않습니다.
        </p>
      </section>
    </main>
  );
}
