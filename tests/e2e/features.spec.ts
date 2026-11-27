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
  await page.getByRole("radio", { name: "ChatGPT", exact: true }).check();
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
test("reports require an explicit first provider and restore only valid choices", async ({
  page,
}) => {
  await signin(page);
  await page.goto("/reports");
  await expect(page.getByRole("radio", { checked: true })).toHaveCount(0);
  await page
    .getByLabel("문서 URL", { exact: true })
    .fill("https://example.com/a");
  await expect(
    page.getByRole("button", { name: "요청문 복사", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("link", { name: /에서 열기/ })).toHaveCount(0);
  for (const provider of ["ChatGPT", "Claude"]) {
    await page.getByRole("radio", { name: provider, exact: true }).check();
    await page.reload();
    await expect(
      page.getByRole("radio", { name: provider, exact: true }),
    ).toBeChecked();
  }
  await page.evaluate(() =>
    localStorage.setItem("levelup-report-provider", "invalid"),
  );
  await page.reload();
  await expect(page.getByRole("radio", { checked: true })).toHaveCount(0);
});
test("reports preserve edited prompts but block stale and invalid document handoffs", async ({
  page,
}, info) => {
  await signin(page);
  await page.goto("/reports");
  await page.getByRole("radio", { name: "ChatGPT", exact: true }).check();
  const url = page.getByLabel("문서 URL", { exact: true });
  const prompt = page.getByRole("textbox", {
    name: "요약 요청문",
    exact: true,
  });
  const copy = page.getByRole("button", { name: "요청문 복사", exact: true });
  const edited = "문서 URL: https://example.com/a\n내가 편집한 요청문";
  await url.fill("https://example.com/a");
  await page
    .getByRole("button", { name: "요청문 만들기", exact: true })
    .click();
  await prompt.fill(edited);
  await url.fill("https://example.com/b");
  await expect(prompt).toHaveValue(edited);
  await expect(page.getByText(/문서 URL이 변경되었습니다/)).toBeVisible();
  await expect(copy).toBeDisabled();
  await expect(page.getByRole("link", { name: /에서 열기/ })).toHaveCount(0);
  await url.fill("http://127.0.0.1/private");
  await page
    .getByRole("button", { name: "요청문 다시 만들기", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "공개 HTTP(S) 문서 주소" }),
  ).toBeVisible();
  await expect(prompt).toHaveValue(edited);
  await expect(copy).toBeDisabled();
  await expect(page.getByRole("link", { name: /에서 열기/ })).toHaveCount(0);
  for (const theme of ["dark", "light"]) {
    await page.evaluate(
      (value) => (document.documentElement.dataset.theme = value),
      theme,
    );
    await page.screenshot({
      path: info.outputPath(`${theme}-reports-stale.png`),
      fullPage: true,
    });
  }
  await url.fill("https://example.com/b");
  await page
    .getByRole("button", { name: "요청문 다시 만들기", exact: true })
    .click();
  await expect(prompt).toHaveValue(/https:\/\/example.com\/b/);
  await expect(page.getByText(/문서 URL이 변경되었습니다/)).toHaveCount(0);
  await expect(copy).toBeEnabled();
  await expect(
    page.getByRole("link", { name: "ChatGPT에서 열기", exact: true }),
  ).toHaveAttribute("href", "https://chatgpt.com/");
});
test("article filters keep complete labels and 44px targets in both themes", async ({
  page,
}, info) => {
  await signin(page);
  for (const theme of ["dark", "light"]) {
    await page.evaluate(
      (value) => localStorage.setItem("levelup.theme", value),
      theme,
    );
    await page.goto("/tech?view=all");
    await expect(page.locator(".feature-count")).toHaveText(/^\d+개$/);
    await expect(
      page.getByText("글을 불러오는 중…", { exact: true }),
    ).toHaveCount(0);
    const metrics = await page
      .locator(".feature-filters select")
      .evaluateAll((selects) =>
        selects.map((element) => {
          const select = element as HTMLSelectElement;
          const style = getComputedStyle(select);
          const context = document.createElement("canvas").getContext("2d")!;
          context.font = style.font;
          const labelWidth = context.measureText(
            select.selectedOptions[0].text,
          ).width;
          return {
            labelWidth,
            width: select.clientWidth,
            height: select.getBoundingClientRect().height,
            padding:
              parseFloat(style.paddingLeft) + parseFloat(style.paddingRight),
          };
        }),
      );
    expect(metrics).toHaveLength(3);
    console.log(JSON.stringify({ project: info.project.name, theme, metrics }));
    for (const metric of metrics) {
      expect(metric.height).toBeGreaterThanOrEqual(44);
      expect(metric.width - metric.padding).toBeGreaterThanOrEqual(
        metric.labelWidth,
      );
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: info.outputPath(`${theme}-filters.png`),
      fullPage: true,
    });
  }
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
