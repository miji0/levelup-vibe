import { Suspense } from "react";
import { ArticlesScreen } from "@/modules/tech/articles";
export default function SavedPage() {
  return (
    <Suspense fallback={<p role="status">저장한 글을 불러오는 중…</p>}>
      <ArticlesScreen saved />
    </Suspense>
  );
}
