"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api, ApiError, type Session, type Settings } from "./api";
import { Brand, GoogleIcon, Icon, type IconName } from "./icon";
import { ThemeButton } from "./theme";

const SessionContext = createContext<Session | null>(null);
const SettingsContext = createContext<{
  settings: Settings | null;
  error: string;
  refresh: () => Promise<void>;
}>({ settings: null, error: "", refresh: async () => {} });
export const useSession = () => useContext(SessionContext);
export const useSettings = () => useContext(SettingsContext);
type NavItem = { path: string; label: string; icon: IconName; parent?: string };
const sectionMenu: Record<string, { icon: IconName; children?: NavItem[] }> = {
  tech: {
    icon: "newspaper",
    children: [
      {
        path: "/tech/saved",
        label: "저장한 글",
        icon: "bookmark",
        parent: "/tech",
      },
      {
        path: "/tech/subscriptions",
        label: "구독 설정",
        icon: "rss",
        parent: "/tech",
      },
      {
        path: "/tech/status",
        label: "수집·발송 상태",
        icon: "clock",
        parent: "/tech",
      },
    ],
  },
  reports: { icon: "report" },
};
function menuItems(sections: Session["sections"]): NavItem[] {
  return [
    { path: "/", label: "홈", icon: "home" },
    ...sections.flatMap((section) => [
      {
        path: section.path,
        label: section.label,
        icon: sectionMenu[section.id]?.icon ?? "newspaper",
      },
      ...(sectionMenu[section.id]?.children ?? []),
    ]),
    { path: "/settings", label: "설정", icon: "settings" },
  ];
}
export function GmailBadge({ settings }: { settings: Settings | null }) {
  const { error } = useSettings();
  const connected = settings?.gmail.state === "connected";
  const label = !settings
    ? error
      ? "연결 상태 조회 불가"
      : "연결 상태 확인 중"
    : connected
      ? "Gmail 연결됨"
      : settings.gmail.state === "reauth_required"
        ? "재연결 필요"
        : "발송 권한 필요";
  return (
    <span
      className={`badge ${!settings ? "neutral" : connected ? "success" : "warning"}`}
    >
      <Icon name={!settings ? "pending" : connected ? "success" : "warning"} />
      {label}
    </span>
  );
}
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [current, setCurrent] = useState<Session | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [settingsError, setSettingsError] = useState("");
  const [error, setError] = useState("");
  const [menu, setMenu] = useState(false);
  const drawer = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const login = pathname === "/login" || pathname === "/privacy";
  const navigation = current ? menuItems(current.sections) : [];
  async function refreshSettings() {
    const value = await api<Settings>("/api/v1/settings");
    setSettings(value);
    setSettingsError("");
  }
  useEffect(() => {
    if (login) return;
    let active = true;
    api<Session>("/api/v1/session")
      .then((data) => {
        if (!active) return;
        setCurrent(data);
        setError("");
        api<Settings>("/api/v1/settings")
          .then((value) => {
            if (active) {
              setSettings(value);
              setSettingsError("");
            }
          })
          .catch(() => {
            if (active) {
              setSettings(null);
              setSettingsError("연결 정보를 불러오지 못했습니다.");
            }
          });
      })
      .catch((err: unknown) => {
        if (!active) return;
        setCurrent(null);
        setSettings(null);
        if (err instanceof ApiError && err.status === 401)
          router.replace(`/login?returnTo=${encodeURIComponent(pathname)}`);
        else
          setError(
            err instanceof Error ? err.message : "서버에 연결할 수 없습니다.",
          );
      });
    return () => {
      active = false;
    };
  }, [login, pathname, router]);
  function closeMenu() {
    if (drawer.current?.open) drawer.current.close();
    setMenu(false);
  }
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const resize = () => {
      if (media.matches) closeMenu();
    };
    media.addEventListener("change", resize);
    return () => media.removeEventListener("change", resize);
  }, []);
  useEffect(() => {
    if (!menu) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [menu]);
  async function signout() {
    if (!current) return;
    try {
      await api("/api/auth/signout", {
        method: "POST",
        headers: { "X-CSRF-Token": current.csrfToken },
      });
      closeMenu();
      setCurrent(null);
      setSettings(null);
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그아웃에 실패했습니다.");
    }
  }
  function nav() {
    return (
      <nav aria-label="주 메뉴">
        {navigation
          .filter((item) => !item.parent || pathname.startsWith(item.parent))
          .map((item) => (
            <Link
              key={item.path}
              href={item.path}
              aria-current={pathname === item.path ? "page" : undefined}
              onClick={closeMenu}
            >
              <Icon name={item.icon} />
              {item.label}
            </Link>
          ))}
      </nav>
    );
  }
  function account() {
    return (
      <div className="account-status">
        <p className="next-briefing">
          <Icon name="clock" />
          매일 08:00 아침 브리핑
        </p>
        <GmailBadge settings={settings} />
        <p className="account-email">
          <GoogleIcon />
          {current?.owner.email}
        </p>
      </div>
    );
  }
  function actions() {
    return (
      <>
        <ThemeButton />
        <span className="action-divider" />
        <button className="text-button" onClick={signout}>
          <Icon name="logout" />
          로그아웃
        </button>
      </>
    );
  }
  if (login) return <>{children}</>;
  if (!current)
    return (
      <main className="center" id="main-content">
        <p role="status">{error || "로그인 상태를 확인하고 있습니다…"}</p>
        {error && <Link href="/login">로그인 화면으로</Link>}
      </main>
    );
  const title =
    navigation.find((item) => item.path === pathname)?.label ?? "기술블로그";
  return (
    <SessionContext.Provider value={current}>
      <SettingsContext.Provider
        value={{ settings, error: settingsError, refresh: refreshSettings }}
      >
        <div className="app-shell">
          <aside className="sidebar">
            <Link className="brand-link" href="/" aria-label="LevelUp 홈">
              <Brand />
            </Link>
            {nav()}
            <footer>{account()}</footer>
          </aside>
          <div className="main-panel">
            <header className="topbar desktop-topbar">
              <span>{title}</span>
              <div className="top-actions">{actions()}</div>
            </header>
            <header className="topbar mobile-topbar">
              <button
                className="icon-button menu-button"
                ref={opener}
                aria-label="메뉴"
                aria-controls="mobile-navigation"
                aria-expanded={menu}
                onClick={() => {
                  drawer.current?.showModal();
                  setMenu(true);
                }}
              >
                <Icon name="menu" />
              </button>
              <Link className="brand-link" href="/" aria-label="LevelUp 홈">
                <Brand />
              </Link>
              <span className="mobile-page-label">{title}</span>
            </header>
            <main className="content" id="main-content">
              {error && (
                <p role="alert" className="error-callout">
                  {error}
                </p>
              )}
              {children}
            </main>
          </div>
          <dialog
            ref={drawer}
            className="navigation-drawer"
            id="mobile-navigation"
            aria-label="모바일 메뉴"
            onClose={() => {
              setMenu(false);
              opener.current?.focus();
            }}
            onClick={(event) => {
              const bounds = event.currentTarget.getBoundingClientRect();
              if (
                event.target === event.currentTarget &&
                (event.clientX < bounds.left ||
                  event.clientX > bounds.right ||
                  event.clientY < bounds.top ||
                  event.clientY > bounds.bottom)
              )
                closeMenu();
            }}
          >
            <div className="drawer-inner">
              <div className="drawer-head">
                <Brand />
                <button
                  className="icon-button"
                  aria-label="메뉴 닫기"
                  autoFocus
                  onClick={closeMenu}
                >
                  <Icon name="close" />
                </button>
              </div>
              {nav()}
              <footer>
                {account()}
                <div className="drawer-actions">{actions()}</div>
                <p className="caption">
                  Escape 또는 바깥을 누르면 닫히고, 포커스는 메뉴 버튼으로
                  돌아갑니다.
                </p>
              </footer>
            </div>
          </dialog>
        </div>
      </SettingsContext.Provider>
    </SessionContext.Provider>
  );
}
