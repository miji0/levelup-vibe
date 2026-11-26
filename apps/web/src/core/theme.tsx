"use client";
import {
  createContext,
  useContext,
  useId,
  useState,
  useSyncExternalStore,
} from "react";
import { Icon } from "./icon";

type Theme = "dark" | "light";
const ThemeContext = createContext<{
  theme: Theme;
  select: (theme: Theme) => void;
} | null>(null);
function readTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}
function subscribe(listener: () => void) {
  const storage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== "levelup.theme") return;
    try {
      document.documentElement.dataset.theme =
        localStorage.getItem("levelup.theme") === "light" ? "light" : "dark";
    } catch {
      return;
    }
    listener();
  };
  window.addEventListener("levelup-theme", listener);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener("levelup-theme", listener);
    window.removeEventListener("storage", storage);
  };
}
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore<Theme>(subscribe, readTheme, () => "dark");
  const [notice, setNotice] = useState<{
    text: string;
    failed: boolean;
  } | null>(null);
  function select(next: Theme) {
    document.documentElement.dataset.theme = next;
    window.dispatchEvent(new Event("levelup-theme"));
    try {
      localStorage.setItem("levelup.theme", next);
      setNotice({
        text: `${next === "dark" ? "다크" : "라이트"} 모드로 변경하고 저장했습니다.`,
        failed: false,
      });
    } catch {
      setNotice({
        text: `${next === "dark" ? "다크" : "라이트"}로 바꿨지만 저장하지 못했습니다`,
        failed: true,
      });
    }
  }
  return (
    <ThemeContext.Provider value={{ theme, select }}>
      {children}
      {notice && (
        <div
          role="status"
          className={notice.failed ? "theme-toast" : "sr-only"}
        >
          {notice.failed && <Icon name="warning" />}
          <div>
            {notice.text}
            {notice.failed && (
              <small>다음에 새로 열면 선택이 유지되지 않을 수 있습니다.</small>
            )}
          </div>
        </div>
      )}
    </ThemeContext.Provider>
  );
}
function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("ThemeProvider is required");
  return value;
}
export function ThemeButton() {
  const { theme, select } = useTheme();
  const [visible, setVisible] = useState(false);
  const id = useId();
  const label = theme === "dark" ? "라이트로 전환" : "다크로 전환";
  return (
    <span
      className="theme-button-wrap"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      <button
        className="icon-button"
        aria-label={label}
        aria-describedby={visible ? id : undefined}
        onFocus={() => setVisible(true)}
        onBlur={() => setVisible(false)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setVisible(false);
        }}
        onClick={() => select(theme === "dark" ? "light" : "dark")}
      >
        <Icon name={theme === "dark" ? "sun" : "moon"} />
      </button>
      {visible && (
        <span className="tooltip" role="tooltip" id={id}>
          {label}
        </span>
      )}
    </span>
  );
}
export function ThemeChoices() {
  const { theme, select } = useTheme();
  return (
    <fieldset className="theme-choices">
      <legend>
        <Icon name="contrast" />
        화면 테마
      </legend>
      <div className="radio-options">
        {(["dark", "light"] as const).map((value) => (
          <label key={value}>
            <input
              type="radio"
              name="theme"
              value={value}
              checked={theme === value}
              onChange={() => select(value)}
            />
            {value === "dark" ? "다크" : "라이트"}
          </label>
        ))}
      </div>
      <p className="caption theme-helper">
        고르면 바로 바뀌고 이 브라우저에 저장됩니다. 다른 기기와는 동기화하지
        않습니다.
      </p>
    </fieldset>
  );
}
