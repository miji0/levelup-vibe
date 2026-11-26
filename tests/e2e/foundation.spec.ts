import {
  test,
  expect,
  type Page,
} from "../../apps/web/node_modules/@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /로 전환/ })).toHaveCount(0);
  await page
    .getByRole("link", { name: "Google로 로그인", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "오늘의 LevelUp" }),
  ).toBeVisible();
}
async function settings(page: Page, mobile: boolean) {
  if (mobile)
    await page.getByRole("button", { name: "메뉴", exact: true }).click();
  await page.getByRole("link", { name: "설정", exact: true }).click();
  await expect(page.getByRole("heading", { name: "일반 설정" })).toBeVisible();
}

test("protected real API/DB flow, shared theme and current-session logout", async ({
  page,
}, info) => {
  const mobile = info.project.name === "mobile-webkit";
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await expect(
    page.getByRole("heading", { name: "오늘의 LevelUp" }),
  ).not.toBeVisible();
  await login(page);
  await expect(page.locator("article.planned")).toHaveCount(2);
  await expect(
    page.locator("article.planned a, article.planned button"),
  ).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  if (mobile)
    await page.getByRole("button", { name: "메뉴", exact: true }).click();
  await page
    .getByRole("button", { name: "라이트로 전환", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  if (mobile) {
    await page.screenshot({
      path: info.outputPath("menu-light.png"),
      style: "nextjs-portal { visibility: hidden; }",
    });
    await page.keyboard.press("Escape");
  }
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "오늘의 LevelUp" }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await settings(page, mobile);
  await expect(
    page.getByRole("radio", { name: "라이트", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole("switch", { name: "기술블로그 이메일 알림" }),
  ).toBeDisabled();
  await expect(page.getByRole("switch")).toHaveAttribute(
    "aria-checked",
    "false",
  );
  await expect(
    page.getByRole("button", { name: "테스트 메일 보내기" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "다시 연결", exact: true }),
  ).toBeEnabled();
  if (mobile)
    await page.getByRole("button", { name: "메뉴", exact: true }).click();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  expect((await page.request.get("/api/v1/home")).status()).toBe(401);
});

test("native theme radios preserve selection when storage is blocked", async ({
  page,
}, info) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException("blocked", "SecurityError");
    };
  });
  await login(page);
  await settings(page, info.project.name === "mobile-webkit");
  const light = page.getByRole("radio", { name: "라이트", exact: true });
  await light.check();
  await expect(light).toBeChecked();
  await light.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(
    page.getByRole("radio", { name: "다크", exact: true }),
  ).toBeChecked();
  await page.keyboard.press("ArrowRight");
  await expect(light).toBeChecked();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("status")).toContainText("저장하지 못했습니다");
});

test("menu Escape/outside close returns focus; desktop has a 56px topbar", async ({
  page,
}, info) => {
  await login(page);
  if (info.project.name === "mobile-webkit") {
    const opener = page.getByRole("button", { name: "메뉴", exact: true });
    await expect(
      page.locator(".mobile-topbar").getByRole("button", { name: /로 전환/ }),
    ).toHaveCount(0);
    await opener.click();
    await expect(
      page.getByRole("dialog", { name: "모바일 메뉴" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "메뉴 닫기", exact: true }),
    ).toBeFocused();
    await page.screenshot({
      path: info.outputPath("menu-dark.png"),
      style: "nextjs-portal { visibility: hidden; }",
    });
    await page.keyboard.press("Escape");
    await expect(opener).toHaveAttribute("aria-expanded", "false");
    await expect(opener).toBeFocused();
    await opener.click();
    await page.mouse.click(370, 300);
    await expect(opener).toHaveAttribute("aria-expanded", "false");
    await expect(opener).toBeFocused();
  } else {
    const topbar = page.locator(".desktop-topbar");
    expect((await topbar.boundingBox())?.height).toBe(56);
    await topbar.getByRole("button", { name: "라이트로 전환" }).focus();
    await expect(page.getByRole("tooltip")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0);
  }
});

for (const theme of ["dark", "light"] as const) {
  test(`Figma comparison matrix: ${theme} login/home/settings`, async ({
    page,
  }, info) => {
    await page.addInitScript(
      (value) => localStorage.setItem("levelup.theme", value),
      theme,
    );
    await page.goto("/login");
    await page.evaluate(() => document.fonts.ready);
    await expect(
      page.getByRole("heading", { name: "개인 사이트에 로그인" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /로 전환/ })).toHaveCount(0);
    expect((await page.locator(".login-panel").boundingBox())?.width).toBe(
      info.project.name === "mobile-webkit" ? 350 : 420,
    );
    await page.screenshot({
      path: info.outputPath(`login-${theme}.png`),
      fullPage: true,
      style: "nextjs-portal { visibility: hidden; }",
    });
    await login(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.locator("article.planned")).toHaveCount(2);
    await expect(
      page.getByRole("heading", { name: "구독 출처 추가", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: info.outputPath(`home-${theme}.png`),
      fullPage: true,
      style: "nextjs-portal { visibility: hidden; }",
    });
    await settings(page, info.project.name === "mobile-webkit");
    await expect(
      page.getByRole("radio", {
        name: theme === "dark" ? "다크" : "라이트",
        exact: true,
      }),
    ).toBeChecked();
    const metrics = await page.evaluate(() => ({
      width: innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      font: getComputedStyle(document.body).fontFamily,
    }));
    expect(metrics.scrollWidth).toBe(metrics.width);
    expect(metrics.font).toContain("Pretendard");
    await page.screenshot({
      path: info.outputPath(`settings-${theme}.png`),
      fullPage: true,
      style: "nextjs-portal { visibility: hidden; }",
    });
  });
}

test("expired OAuth navigation recovers with a safe login page and retry", async ({
  page,
}) => {
  await page.goto("/api/auth/callback/google?state=expired&code=must-not-leak");
  await expect(page).toHaveURL(/\/login\?error=OAUTH_STATE_INVALID$/);
  await expect(
    page
      .getByRole("region", { name: "개인 사이트에 로그인" })
      .getByRole("alert"),
  ).toContainText("로그인 요청이 만료되었습니다");
  await expect(page.locator("body")).not.toContainText("must-not-leak");
  await page.getByRole("link", { name: "다른 Google 계정으로 로그인" }).click();
  await expect(
    page.getByRole("heading", { name: "오늘의 LevelUp" }),
  ).toBeVisible();
});
