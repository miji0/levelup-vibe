import { Suspense } from "react";
import { ArticlesScreen } from "@/modules/tech/articles";
export default function TechPage() {
  return (
    <Suspense fallback={<p role="status">글을 불러오는 중…</p>}>
      <ArticlesScreen />
    </Suspense>
  );
}
