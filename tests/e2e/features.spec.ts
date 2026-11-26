import {
  test,
  expect,
  type Page,
} from "../../apps/web/node_modules/@playwright/test";
async function signin(page: Page) {
  await page.goto("/login");
  await page
    .getByRole("link", { name: "Google로 로그인", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "오늘의 LevelUp" }),
  ).toBeVisible();
}
test("subscription, collection, explicit saved/read state and private report handoff", async ({
  page,
}) => {
  await signin(page);
  await page.goto("/tech/subscriptions");
  await page
    .getByLabel("출처 URL", { exact: true })
    .fill("https://example.com/feed.xml");
  await page.getByRole("button", { name: "연결 확인", exact: true }).click();
  await expect(
    page.getByText("Fixture Tech", { exact: true }).first(),
  ).toBeVisible();
  const add = page.getByRole("button", { name: "추가", exact: true });
  // Other browser project may already have subscribed to the shared fixture.
  if (await add.isEnabled()) {
    await add.click();
    await expect(
      page.getByText("초기 수집 대기", { exact: true }).first(),
    ).toBeVisible();
  }
  const collected = await page.request.post("/api/__test/collect");
  expect(collected.ok()).toBeTruthy();
  await page.goto("/tech?view=all");
  await expect(
    page.getByRole("heading", {
      name: "Fixture engineering article",
      exact: true,
    }),
  ).toBeVisible();
  const row = page.locator(".article-card").filter({
    has: page.getByRole("heading", {
      name: "Fixture engineering article",
      exact: true,
    }),
  });
  const save = row.getByRole("button", { name: /저장/ });
  if ((await save.getAttribute("aria-pressed")) === "true") await save.click();
  await save.click();
  await expect(save).toHaveAttribute("aria-pressed", "true");
  await row.getByRole("link", { name: "리포트 분석", exact: true }).click();
  await expect(page.getByLabel("문서 URL", { exact: true })).toHaveValue(
    "https://example.com/article",
  );
  expect(
    await page
      .getByRole("textbox", { name: "요약 요청문", exact: true })
      .inputValue(),
  ).toContain("https://example.com/article");
  expect(page.url()).not.toContain("example.com");
  await expect(page.getByRole("link", { name: /에서 열기/ })).toHaveAttribute(
    "href",
    "https://chatgpt.com/",
  );
  await page.getByRole("radio", { name: "Claude", exact: true }).check();
  await expect(
    page.getByRole("link", { name: "Claude에서 열기", exact: true }),
  ).toHaveAttribute("href", "https://claude.ai/");
  await page
    .getByLabel("문서 URL", { exact: true })
    .fill("https://example.com/report.pdf");
  await page.getByRole("button", { name: "요청문 다시 만들기" }).click();
  expect(
    await page
      .getByRole("textbox", { name: "요약 요청문", exact: true })
      .inputValue(),
  ).toContain("report.pdf");
  await page.evaluate(() => {
    let copied = "";
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          copied = value;
        },
        readText: async () => copied,
      },
    });
  });
  await page.getByRole("button", { name: "요청문 복사", exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    await page
      .getByRole("textbox", { name: "요약 요청문", exact: true })
      .inputValue(),
  );
  await page.evaluate(() =>
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => {
          throw new Error("blocked");
        },
      },
    }),
  );
  await page.getByRole("button", { name: "요청문 복사", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "자동 복사에 실패" }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "요약 요청문", exact: true }),
  ).toBeFocused();
  await page.goto("/tech/saved");
  await expect(
    page.getByRole("heading", {
      name: "Fixture engineering article",
      exact: true,
    }),
  ).toBeVisible();
});
test("feature screens fit desktop/mobile in both themes", async ({
  page,
}, info) => {
  await signin(page);
  for (const theme of ["dark", "light"]) {
    await page.evaluate(
      (value) => localStorage.setItem("levelup.theme", value),
      theme,
    );
    for (const path of [
      "/tech?view=all",
      "/tech/subscriptions",
      "/tech/saved",
      "/tech/status",
      "/reports",
      "/settings",
    ]) {
      await page.goto(path);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.locator(".content h1")).toBeVisible();
      if (path === "/tech/status")
        await expect(
          page
            .locator(".record-list a")
            .filter({ hasText: /\d{4}-\d{2}-\d{2}/ }),
        ).toHaveCount(7);
      await expect(page.locator('.content [role="alert"]')).toHaveCount(0);
      await expect(
        page.getByText("불러오는 중…", { exact: false }),
      ).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBeTruthy();
      await page.screenshot({
        path: info.outputPath(
          `${theme}-${path.split("?")[0].replaceAll("/", "_")}.png`,
        ),
        fullPage: true,
        style: "nextjs-portal { visibility: hidden; }",
      });
    }
  }
});
