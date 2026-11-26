export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
async function request(path: string, options?: RequestInit) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    cache: "no-store",
  });
  const body: unknown = await response.json();
  if (typeof body !== "object" || body === null)
    throw new Error("서버 응답을 확인할 수 없습니다.");
  if (!response.ok) {
    const error =
      "error" in body && typeof body.error === "object" && body.error !== null
        ? body.error
        : {};
    throw new ApiError(
      response.status,
      "code" in error && typeof error.code === "string"
        ? error.code
        : "REQUEST_FAILED",
      "message" in error && typeof error.message === "string"
        ? error.message
        : "요청에 실패했습니다.",
    );
  }
  if (!("data" in body)) throw new Error("서버 응답에 데이터가 없습니다.");
  return body;
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  return (await request(path, options)).data as T;
}
export async function apiPage<T>(
  path: string,
): Promise<{ data: T; meta: { nextCursor: string | null; hasMore: boolean } }> {
  const body = await request(path);
  if (
    !("meta" in body) ||
    typeof body.meta !== "object" ||
    body.meta === null ||
    !("nextCursor" in body.meta) ||
    !("hasMore" in body.meta) ||
    (body.meta.nextCursor !== null &&
      typeof body.meta.nextCursor !== "string") ||
    typeof body.meta.hasMore !== "boolean"
  )
    throw new Error("페이지 정보를 확인할 수 없습니다.");
  return {
    data: body.data as T,
    meta: { nextCursor: body.meta.nextCursor, hasMore: body.meta.hasMore },
  };
}
export type Session = {
  owner: { id: string; email: string; provider: "google" };
  csrfToken: string;
};
export type Home = {
  tech: {
    digestDate: string;
    count: number | null;
    isPreview: boolean;
    state: string;
  };
  homeCards: {
    id: string;
    label: string;
    status: "planned" | "ready" | "unavailable";
    path: string | null;
    description: string;
    summary: string | null;
  }[];
};
export type Settings = {
  notificationsEnabled: boolean;
  version: number;
  gmail: { state: string; email: string; version: number | null };
};
