## 디자인 참고

- [LevelUp Figma 화면 시안](https://www.figma.com/design/GhMsLi8oyVJDNNQkZ4sUrf/%EB%B0%94%EC%9D%B4%EB%B8%8C%EC%BD%94%EB%94%A9_levelup?node-id=0-1)
- 화면 구성과 시각적 표현은 Figma를 참고하며, 동작과 정책은 PRD 및 설계 문서를 따른다.

## Overview

daily.dev의 Feeds 문서 페이지는 **고정 탐색 영역, 차분한 다크 캔버스, 보라색 상태 강조**를 중심으로 구성된다. 왼쪽 사이드바가 탐색을 담당하고, 둥근 메인 패널 안에서 제목·설명·표·제품 스크린샷이 이어진다. 넓은 화면에는 오른쪽 목차가 추가되어 긴 글에서도 현재 위치를 찾기 쉽다.

첨부된 Apple 분석 문서의 섹션 구성과 `{token.reference}` 표기 방식을 따른다. 아래 토큰 이름은 이 분석을 위해 붙인 별칭이며, 원본 사이트의 토큰 이름과 동일하다는 뜻은 아니다.

**분석 범위와 근거**

- 1차 대상: [Feeds 문서 페이지](https://docs.daily.dev/feeds/)의 실제 렌더링과 computed style. 라이트·다크 테마, 검색창 기본 상태, 390·768·1023·1024·1279·1280px 너비를 확인했다.
- 2차 대상: 본문에 포함된 [For you 피드 이미지](https://docs.daily.dev/images/feeds/for-you-feed.jpg). 앱의 카드·탭 구성은 이미지 관찰이며, 앱 DOM이나 실제 상호작용을 측정한 결과가 아니다.
- 분석일: 2026-11-24. 문서 UI와 이미지 속 앱 UI는 별도 화면으로 취급한다.
- **측정**은 브라우저에서 확인한 값, **추정**은 이미지 관찰, **적용 제안**은 LevelUp을 위한 설계 선택이다.

**Key Characteristics:**

- 다크 모드에서 바깥 배경보다 본문 패널이 더 어둡다. 흰 카드를 겹치는 일반적인 대시보드와 다른 표면 관계다.
- 보라색은 주요 버튼·선택 상태에, 파란색은 본문 링크에 사용된다.
- Plus Jakarta Sans의 굵은 제목과 작은 UI 글자가 정보 위계를 만든다.
- 256px 고정 사이드바, 유동적인 본문, 조건부 오른쪽 목차로 구성된다.
- 대부분 평면적이지만 주요 CTA·검색 모달·문서 이미지에는 그림자가 있다.
- 앱 스크린샷은 문서와 달리 썸네일을 포함한 카드 그리드와 상단 피드 탭을 사용한다.

## Colors

### Brand & Accent

| Token | 측정값 | 용도 |
|---|---|---|
| `{colors.primary}` | `#9333ea` | 주요 CTA. 원본 `--theme-accent` |
| `{colors.accent-soft}` | `#c084fc` | 다크 모드에서 선택한 사이드바 항목의 왼쪽 선 |
| `{colors.selected-ink}` | `#e8d5ff` | 선택한 사이드바 항목의 글자 |
| `{colors.toc-selected}` | `rgba(168, 85, 247, 0.18)` | 선택한 오른쪽 목차 항목 배경 |
| `{colors.link-dark}` | `oklch(0.707 0.165 254.624)` | 다크 모드 본문 링크 |
| `{colors.link-light}` | `oklch(0.546 0.245 262.881)` | 라이트 모드 본문 링크 |

보라색과 파란색의 역할이 구분된다. 모든 링크를 브랜드 보라색으로 통일하면 원본과 달라진다. 성공·오류 색상은 이 페이지의 실제 알림 상태에서 검증하지 않았다.

### Surface

| Token | Dark | Light | 용도 |
|---|---|---|---|
| `{colors.canvas}` | `#17171c` | `#f9f7fa` | 바깥 배경, 사이드바 뒤 캔버스 |
| `{colors.surface}` | `#0f0f12` | `#ffffff` | 본문 패널, 상단 바 |
| `{colors.surface-raised}` | `#17171c` | 미측정 | 다크 검색 모달 |
| `{colors.surface-code}` | `#1f1f25` | 미측정 | 인라인 코드 배경 |
| `{colors.callout}` | `rgba(88, 28, 135, 0.16)` | `#faf5ff` | AI 요약 안내 박스 |
| `{colors.utility-button}` | `#f4f4f5` | 미측정 | 다크 모드의 밝은 요약 아이콘 버튼 |

### Text

| Token | Dark | Light | 용도 |
|---|---|---|---|
| `{colors.heading}` | `#f3f4f6` | `#111827` | 페이지 제목 |
| `{colors.body}` | `#d4d4d8` | `oklch(0.373 0.034 259.733)` | 본문 문단 |
| `{colors.text-muted}` | `#a1a1aa` | 미측정 | 다크 모드 수정일·보조 정보 |
| `{colors.on-primary}` | `#ffffff` | `#ffffff` | 주요 CTA 글자 |

페이지 제목과 섹션 제목에는 미세한 색상 차이가 있다. 이 문서의 별칭은 구현에 필요한 역할을 정리한 것이며, 모든 요소가 하나의 원본 CSS 변수를 공유한다는 의미는 아니다.

### Hairlines & Borders

- **Panel border** (`{colors.border}`): 다크 `#2a2a30`, 라이트 `#e5e7eb`. 메인 패널과 검색 트리거에 사용한다.
- **Subtle border** (`{colors.border-subtle}`): 다크 `#1a1a20`, 라이트 `#f3f4f6`. 원본 `--theme-border-subtle` 값이다.
- **Content divider** (`{colors.content-divider}`): 다크 `#1f1f25`. 섹션 제목 아래, 표의 행, 이미지 테두리에 사용한다.
- **Strong divider** (`{colors.border-strong}`): 다크 `#3f3f46`. 표 머리글 아래 2px 선, 인라인 코드 테두리에 사용한다.
- **Callout border** (`{colors.callout-border}`): 다크 `rgba(147, 51, 234, 0.22)`, 라이트 `#e9d5ff`.

### Brand Gradient

큰 배경에는 그라디언트가 없지만 **선택한 사이드바 항목에는 작은 수평 그라디언트가 있다.**

`{colors.selected-gradient}` = `linear-gradient(90deg, rgba(168, 85, 247, 0.22), rgba(168, 85, 247, 0.04))`

주요 CTA는 단색 배경이며 보라색 그림자가 빛 번짐을 만든다. 이 효과를 페이지 전체의 배경 장식으로 확대하지 않는다.

## Typography

### Font Family

- **Display / Body / UI, 측정:** `"Plus Jakarta Sans", -apple-system, system-ui, "Segoe UI", Roboto, sans-serif`.
- **Monospace, 원본 CSS 변수:** `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace`.
- 영문 제목은 별도 디스플레이 서체 대신 같은 sans-serif 계열의 크기·굵기·자간으로 구분한다.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.page-title}` | 40px | 700 | 46px | -0.8px | 데스크톱 페이지 제목 |
| `{typography.page-title-mobile}` | 32px | 700 | 36.8px | -0.64px¹ | 작은 화면 페이지 제목 |
| `{typography.section-title}` | 30px | 700 | 36px | -0.75px | 본문 H2 |
| `{typography.subsection-title}` | 24px | 700 | 28.8px | -0.6px | 본문 H3 |
| `{typography.body}` | 15px | 400 | 23.25px | normal | 본문 문단 |
| `{typography.meta}` | 14px | 400 | 21px | normal | 마지막 수정일 |
| `{typography.nav-selected}` | 14px | 600 | 20.3px | normal | 선택한 사이드바 항목 |
| `{typography.table-heading}` | 14px | 700 | 20px | 0.7px | 대문자 표 머리글 |
| `{typography.table-body}` | 14px | 400 | 20px | normal | 표 내용 |
| `{typography.callout-title}` | 15px | 700 | 18.75px | -0.15px | 요약 안내 제목 |
| `{typography.footer}` | 12px | 400 | 16.8px | normal | 하단 보조 링크 |

¹ 모바일 제목의 -0.64px는 데스크톱의 -0.02em을 적용한 **재현 제안**이다. 모바일 자간 자체는 별도로 측정하지 않았다.

### Principles

- 제목은 700, 선택 상태는 600, 본문은 400을 중심으로 구분한다.
- 큰 제목은 음수 자간을 사용하고, 표 머리글은 양수 자간으로 대비시킨다.
- 본문 행간은 약 1.55다. 정보 밀도를 높여도 문단을 지나치게 압축하지 않는다.
- 16px인 body 기본값과 15px인 실제 문단 스타일을 구분한다.

### Note on Font Substitutes

**LevelUp 적용 확정(2026-11-26):** 한국어는 Pretendard로 확정한다. 워드마크·영문 강조·숫자·URL은 Plus Jakarta Sans를 사용한다. system-ui는 대체 글꼴이며 실제 설치·로딩·줄바꿈·굵기 검증은 구현 단계에서 수행한다. Pretendard는 원본에서 측정된 서체가 아닌 프로젝트 선택이다. Figma의 Noto Sans KR 대체 표시는 후속 목업에서 교체한다. 한국어 긴 제목의 자간·줄바꿈은 실제 렌더링으로 확인한다.

## Layout

### Spacing System

측정된 반복 간격은 8·12·16·20·24·32·40·48·56·64px다. 하나의 엄격한 8px 배수 체계라기보다 작은 UI 간격과 큰 문서 간격을 구분한다.

| Token | Value | 용도 |
|---|---|---|
| `{spacing.xs}` | 8px | 아이콘과 글자 사이 |
| `{spacing.sm}` | 12px | 표 셀 내부 여백 |
| `{spacing.md}` | 16px | 패널 내부 간격, 안내 박스 가로 여백 |
| `{spacing.mobile-gutter}` | 20px | 390px 화면 본문 좌우 여백 |
| `{spacing.lg}` | 24px | 제목 영역과 안내 박스 사이 |
| `{spacing.tablet-gutter}` | 32px | 768px 화면 본문 좌우 여백 |
| `{spacing.block}` | 40px | 표 상하 간격, H3 위 간격 |
| `{spacing.desktop-gutter}` | 48px | 데스크톱 본문 좌우 여백, 이미지 상하 간격 |
| `{spacing.section}` | 56px | H2 위 간격 |
| `{spacing.column-gap}` | 64px | 본문과 오른쪽 목차 사이 |

### Grid & Container

- `{layout.sidebar-width}` = **256px**. 데스크톱에서 화면 왼쪽에 고정된다.
- `{layout.topbar-height}` = **56px**. 본문 패널 상단의 탐색·CTA 바다.
- `{layout.body-max}` = **1216px**. 데스크톱 본문 래퍼의 측정된 max-width다.
- `{layout.toc-width}` = **260px**. 넓은 화면의 오른쪽 목차 열이다.
- 1280px 화면: 본문 패널은 x=256px에서 시작하고, 글 본문은 약 **586px**, 목차는 260px, 열 간격은 64px다.
- 오른쪽 목차가 없는 1279px 화면에서는 글 본문이 **800px**로 측정되었다. 본문 폭은 화면과 목차 표시 여부에 따라 달라진다.
- 앱 스크린샷에서는 세로 아이콘 레일 + 텍스트 사이드바 + 3열 카드 그리드가 보인다. 이는 이미지 속 배치이며 문서 페이지의 그리드 규칙과 다르다.

### Whitespace Philosophy

탐색 메뉴는 조밀하게, 문서 본문은 넉넉하게 구성한다. 작은 메뉴의 반복 간격과 큰 본문 블록의 간격을 동일하게 만들지 않는다. 상단은 제목·수정일·도구 상자를 묶고, 설명과 표는 별도의 읽기 블록으로 분리한다.

## Elevation & Depth

| Level | 측정된 처리 | Use |
|---|---|---|
| Flat | 그림자 없음 | 본문, 표, 사이드바 |
| Bordered panel | 1px `{colors.border}` | 메인 패널, 검색 트리거 |
| Selected inset | `inset 0 0 0 1px rgba(192,132,252,0.1)` | 선택한 사이드바 항목 |
| CTA glow | `inset 0 1px 0 rgba(255,255,255,0.08), 0 6px 18px rgba(147,51,234,0.35)` | 주요 CTA |
| Image elevation | `0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1)` | 본문 스크린샷 |
| Dialog elevation | `inset 0 0 0 1px rgba(255,255,255,0.02), 0 25px 60px -12px rgba(0,0,0,0.55), 0 8px 24px -4px rgba(147,51,234,0.12)` | 검색 모달 |

### Decorative Depth

보라색 빛 번짐은 주요 동작과 모달에 제한된다. 본문 전체에 그림자를 반복하지 않는다. 확인한 주요 표면에 유리 효과나 배경 블러를 재현해야 할 근거는 없으므로 기본 구현에 추가하지 않는다.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.none}` | 0px | 모바일 메인 패널, 표 셀 |
| `{rounded.nav}` | 6px | 선택한 사이드바 항목 |
| `{rounded.control}` | 8px | 주요 CTA, 검색 트리거, 모바일 메뉴 버튼 |
| `{rounded.icon}` | 10px | 요약 도구 아이콘 버튼 |
| `{rounded.chip}` | 12px | 오른쪽 목차 선택 항목, 인라인 코드 |
| `{rounded.panel}` | 14px | 데스크톱 메인 패널, 요약 안내 박스 |
| `{rounded.media}` | 16px | 문서 스크린샷, 검색 모달 |

### Image Geometry

- 문서의 For you 스크린샷은 원본 **1600 × 1000**, 비율 **8:5**다. 본문에서는 가로 100%에 맞추고 비율을 유지한다.
- 문서 이미지에는 `{rounded.media}`와 얇은 테두리가 적용된다.
- 앱 이미지에서는 카드 안의 가로형 썸네일과 작은 출처 아바타가 보인다. 카드의 정확한 radius·패딩·이미지 비율은 추정치로도 확정하지 않는다.
- 스크린샷의 밝은 보라색 외곽 강조선은 설명용 주석일 수 있다. 앱 탭의 기본 테두리나 키보드 포커스 규칙으로 복사하지 않는다.

## Components

### Top Navigation

**`sidebar-navigation`** — `{layout.sidebar-width}` 고정 영역. 로고·테마 전환·검색·그룹별 메뉴·하단 지원 링크로 구성한다. 그룹은 접고 펼칠 수 있으며 현재 페이지가 속한 그룹은 펼쳐져 있었다.

**`sidebar-item-selected`** — `{colors.selected-gradient}`, 2px `{colors.accent-soft}` 왼쪽 선, `{colors.selected-ink}`, `{typography.nav-selected}`, `{rounded.nav}`. 선택 상태는 색상 외에 선과 굵기로도 구분된다.

**`content-topbar`** — `{layout.topbar-height}` 높이의 sticky 바. 데스크톱에서는 breadcrumb와 오른쪽 CTA, 모바일에서는 메뉴 버튼·로고·CTA를 배치한다. 데스크톱 상단 모서리는 `{rounded.panel}`, 모바일에서는 직각이다.

**`toc-rail`** — `{layout.toc-width}` 열 안에서 top **80px**에 sticky 배치. 공유 아이콘과 목차를 포함한다. 현재 섹션은 `{colors.toc-selected}` 배경과 `{rounded.chip}`으로 강조한다.

### Buttons

**`button-primary`** — `{colors.primary}` 배경, `{colors.on-primary}` 글자, 높이 **36px**, 좌우 **16px** 패딩, `{rounded.control}`, CTA glow. 주요 동작 하나에 시선을 모은다.

**`button-icon-utility`** — 요약 안내 박스 안의 **36 × 36px** 버튼. `{colors.utility-button}` 배경과 `{rounded.icon}`을 사용하며, 보이는 글자 대신 아이콘과 접근성 이름으로 동작을 구분한다.

**`button-copy-split`** — 텍스트 복사 버튼과 추가 메뉴 버튼을 하나의 밝은 컨테이너에 묶는다. 다크 모드에서 내부 글자는 어두워야 한다.

**`text-link`** — 본문 안에서는 테마에 따라 `{colors.link-dark}` 또는 `{colors.link-light}`를 사용한다. 외부 이동·동작 버튼과 일반 텍스트를 구분한다.

버튼의 pressed transform은 측정하지 않았다. 첨부 예시의 `scale(0.95)`를 원본 동작으로 간주하지 않는다.

### Cards & Containers

**`content-shell`** — `{colors.surface}` 배경, 1px `{colors.border}`, 데스크톱 `{rounded.panel}`. 모바일에서는 바깥 테두리와 둥근 모서리를 줄여 화면 폭을 활용한다.

**`summary-callout`** — `{colors.callout}` 배경, 1px `{colors.callout-border}`, `{rounded.panel}`, 패딩 **14px 16px**, 내부 간격 **16px**. 안내 문구와 도구 버튼 묶음으로 구성되며 작은 화면에서는 버튼이 여러 줄로 재배치된다.

**`comparison-table`** — `{typography.table-body}`, 셀 패딩 `{spacing.sm}`. 머리글은 `{typography.table-heading}`, 하단 2px `{colors.border-strong}`. 본문 행은 1px `{colors.content-divider}`로 구분한다. 모바일에서는 열을 삭제하지 않고 표 내부를 가로 스크롤한다.

**`faq-accordion`** — 질문과 펼침 표시를 가로로 배치한다. 질문 버튼은 위아래 **16px** 패딩이며 답변은 아래에 이어진다. 펼침 상태는 `aria-expanded`로 표현한다.

**`feed-article-card` — 이미지 관찰:** 출처 아바타·제목·태그·날짜/읽기 시간·썸네일·하단 행동 아이콘으로 구성된다. 일부 카드는 이미지나 짧은 설명이 없는 변형이다. 라이브 앱의 치수와 상호작용은 미검증이다.

**`feed-tabs` — 이미지 관찰:** 피드 상단에 기본 탭, 주제별 탭, 추가 버튼을 가로 배치한다. 탭의 상세 상태 색상과 모바일 전환 방식은 이미지로 판단하지 않는다.

### Inputs & Forms

**`search-trigger`** — 왼쪽 메뉴 상단의 검색 버튼. 높이 **37px**, 가로 패딩 **10px**, 간격 `{spacing.xs}`, `{rounded.control}`, 1px `{colors.border}`. 검색 아이콘·라벨·키보드 단축키를 포함한다.

**`search-dialog`** — 1280px 화면에서 폭 **608px**, `{colors.surface-raised}`, `{rounded.media}`, Dialog elevation. 입력 행 패딩은 **16px 18px**이며 입력 글자는 **16px**다. 열면 입력창으로 포커스가 이동하고 Escape로 닫히는 것을 확인했다. 검색어 제출·결과 선택·오류 상태는 검사하지 않았다.

**`subscription-source-manager` — LevelUp 적용 제안:** ‘구독 설정’ 화면에 URL 입력란과 ‘연결 확인’을 배치하고, 확인된 출처명·수집 URL·피드 선택 결과 아래에 ‘추가’를 제공한다. 등록 목록의 각 행은 출처명·URL·구독 토글·수집 상태·삭제 버튼으로 구성한다. 입력·확인 중·추가 완료·이미 등록됨·연결 실패·미지원 상태를 글자와 아이콘으로 구분한다. 삭제가 수집과 미발송 알림을 중단하고 기존 글·저장 기록은 유지한다는 설명을 가까이 표시한다. 모바일에서는 URL이 줄바꿈되도록 하고 삭제·토글의 클릭 영역을 확보한다. 이 구성은 [PRD의 추가 요구](PRD.md#411-구독-설정에서-수집-대상-관리)를 반영한 제안이며 daily.dev에서 관찰한 컴포넌트가 아니다.

### Footer

**`micro-footer`** — 작은 소셜·관련 사이트·정책 링크를 묶는다. `{typography.footer}`, 다크 `{colors.text-muted}`, 옅은 상단 선. 측정된 데스크톱 패딩은 **16px 40px 20px**다. 사이드바 하단 지원 링크와 본문 하단 footer는 별도 영역이다.

## Do's and Don'ts

### Do

- 문서 UI의 측정값과 앱 스크린샷에서 관찰한 패턴을 구분한다.
- 탐색 메뉴는 작은 글자와 조밀한 간격, 읽기 본문은 넉넉한 행간으로 구성한다.
- 보라색 CTA·선택 상태와 파란색 본문 링크의 역할을 유지한다.
- 현재 위치는 배경·선·글자 굵기를 함께 사용해 표현한다.
- 긴 표는 표 영역 안에서 가로 스크롤하고 페이지 전체의 가로 넘침을 확인한다.
- 원본에 없는 한국어 글꼴·터치 영역·상태를 추가할 때는 적용 제안으로 명시한다.

### Don't

- Apple 예시의 파란색 팔레트, SF Pro, 사진 중심 히어로를 이 분석에 섞지 않는다.
- 이미지에 덧그린 탭 강조선을 제품의 기본 스타일로 확정하지 않는다.
- 모든 카드에 CTA의 보라색 발광 그림자를 반복하지 않는다.
- 문서 목차를 앱의 기본 사이드바와 동일한 컴포넌트로 취급하지 않는다.
- 관찰하지 않은 포커스 링, 로딩 애니메이션, 반응형 앱 그리드를 원본 사양으로 단정하지 않는다.

## Responsive Behavior

### Breakpoints

| 확인 너비 | 관찰된 문서 레이아웃 |
|---|---|
| 390px | 사이드바는 화면 밖 drawer, 상단 메뉴 버튼, 본문 위 접이식 목차. 좌우 20px, 제목 32px |
| 768px | drawer와 접이식 목차 유지. 본문 좌우 32px, 제목 32px |
| 1023px | drawer와 접이식 목차 유지. 제목 40px |
| 1024px | 256px 고정 사이드바 표시. 모바일 메뉴·접이식 목차 숨김. 오른쪽 목차도 숨김 |
| 1279px | 고정 사이드바와 단일 본문 열. 측정된 글 본문 폭 800px |
| 1280px | 본문 + 260px 오른쪽 목차, 64px 열 간격 |

사이드바 전환은 **1024px**, 오른쪽 목차 전환은 **1280px** 양쪽 경계에서 확인했다. 제목 크기와 세부 패딩의 정확한 전환점은 모든 너비에서 확인하지 않았다.

### Touch Targets

원본 주요 버튼은 36px 높이이며 일부 탐색 항목도 44px보다 작다. **LevelUp 적용 제안:** 모바일에서 아이콘의 시각 크기를 유지하더라도 실제 클릭 영역은 최소 44 × 44px로 확보한다. 이를 원본 측정값으로 표시하지 않는다.

### Collapsing Strategy

- 고정 왼쪽 메뉴 → 모바일 drawer.
- 오른쪽 목차 → 모바일 본문 위 접이식 목차. 1024~1279px에서는 두 목차가 모두 숨겨진다.
- breadcrumb → 작은 화면의 로고·메뉴 버튼.
- 가로형 요약 도구 모음 → 여러 줄 버튼 배치.
- 테두리와 둥근 모서리가 있는 메인 패널 → 모바일 전체 폭 본문.

### Image Behavior

본문 이미지는 원래 비율을 유지하며 본문 폭에 맞춰 축소된다. For you 이미지는 `loading="auto"`, Explore 이미지는 `loading="lazy"`로 확인되어 모든 이미지를 같은 로딩 정책으로 일반화하지 않는다. 앱 카드 이미지의 모바일 크롭은 검증하지 않았다.

## Iteration Guide

1. `{component.content-shell}` → `{component.sidebar-navigation}` → `{component.content-topbar}` 순서로 구조를 맞춘다. `{component.*}`는 위 Components 절의 같은 이름을 가리키며 별도 YAML 파일을 전제하지 않는다.
2. 색상·타이포·간격을 각각 한곳에서 정의한 뒤 컴포넌트에서는 `{token.reference}`로 참조한다. 상태 변형은 기본·선택·펼침을 구분한다.
3. 다크 테마의 구조를 먼저 검토하고 라이트 테마에서도 글자와 표면의 대비를 확인한다. 원본의 테마 지원을 프로젝트의 추가 구현 요구로 자동 확장하지 않는다.
4. **LevelUp 적용 제안:** 사이드바는 ‘오늘의 글 / 전체 글 / 저장한 글 / 구독·알림 설정’으로 치환한다. 요약 안내 박스의 시각 패턴은 아침 이메일 상태 표시 등에 재사용할 수 있다. AI 요약 기능 추가를 뜻하지 않는다.
5. **LevelUp 적용 제안:** 앱 카드의 제목·출처·태그·저장 패턴만 가져온다. 투표·댓글·광고·커뮤니티 기능은 기존 기획 범위에 포함하지 않는다.
6. 390px에서 제목 줄바꿈·버튼 터치 영역·표 내부 스크롤을, 1024px에서 메뉴 전환을, 1280px에서 열 너비를 확인한다.
7. 한 번에 한 컴포넌트를 수정하고 전후 화면을 비교한다. 미측정 값을 채우면 근거와 측정 화면을 함께 갱신한다.

## Known Gaps

- 분석은 공개 문서와 포함 이미지에 한정된다. 로그인한 앱의 실시간 DOM·설정 화면·개인화 결과는 확인하지 않았다.
- 이미지 속 카드의 정확한 색상·패딩·radius·폰트 크기·반응형 열 수는 검증하지 않았다.
- 일부 라이트 테마 세부값은 미측정으로 남겼다. 다크 값을 단순 반전한 값을 원본으로 기재하지 않는다.
- 검색 결과, 폼 유효성 검사, 수집 실패, 이메일 발송 실패 상태는 이 문서에서 원본 근거가 없다.
- 키보드 포커스 링, pressed 변형, 모션 지속시간과 reduced-motion 대응은 미검증이다.
- 화면 크기별 검토는 브라우저 viewport 기반이며 실제 터치 기기 검증은 아니다.
- 본 문서는 디자인 분석 파일이다. CSS 구현, 폰트 설치, 애플리케이션 기능 추가는 수행하지 않았다.
