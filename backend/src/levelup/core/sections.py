"""Static section registry shared by the shell menu (API-002) and the common home (API-003)."""

from dataclasses import dataclass
from typing import Literal

PLANNED_DESCRIPTION = "준비 중 · 아직 상세 설계 전인 기능입니다."


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    path: str | None
    availability: Literal["available", "planned"]
    on_home: bool
    description: str = ""
    summary: str | None = None


SECTIONS: tuple[Section, ...] = (
    Section(
        "tech",
        "기술블로그",
        "/tech",
        "available",
        on_home=True,
        description="구독한 출처의 새 글을 한곳에서 확인합니다.",
        summary="오늘의 브리핑과 수집한 전체 글을 확인하세요.",
    ),
    # CR-UX-004: reports stays in the menu only.
    Section("reports", "리포트 분석", "/reports", "available", on_home=False),
    Section("inbox-summary", "수신 이메일 요약", None, "planned", True, PLANNED_DESCRIPTION),
    Section("daily-news", "데일리 기사 요약", None, "planned", True, PLANNED_DESCRIPTION),
)


def menu_sections() -> list[dict[str, str | None]]:
    return [
        {"id": s.id, "label": s.label, "path": s.path}
        for s in SECTIONS
        if s.availability == "available"
    ]


def home_cards() -> list[dict[str, str | None]]:
    return [
        {
            "id": s.id,
            "label": s.label,
            "status": "ready" if s.availability == "available" else "planned",
            "path": s.path,
            "description": s.description,
            "summary": s.summary,
        }
        for s in SECTIONS
        if s.on_home
    ]
