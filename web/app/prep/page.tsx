import type { Metadata } from "next";
import { Suspense } from "react";
import { PrepLoading, PrepView } from "@/components/prep/PrepView.tsx";
import { MESSAGES } from "@/lib/i18n.ts";
import { requestLocale } from "@/lib/request-locale.ts";

export async function generateMetadata(): Promise<Metadata> {
  const t = MESSAGES[await requestLocale()];
  return { title: t.prepTitle, description: t.prepDescription };
}

export default function PrepPage() {
  return (
    <Suspense fallback={<PrepLoading />}>
      <PrepView />
    </Suspense>
  );
}
