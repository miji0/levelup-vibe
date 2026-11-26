// Memory only: document URLs and prompts never enter a route, persistent storage or server API.
let documentUrl = "";
export function handoffReport(url: string) {
  documentUrl = url;
}
export function takeReportUrl() {
  const value = documentUrl;
  documentUrl = "";
  return value;
}
