import type { Metadata } from "next";
import { Suspense } from "react";
import { CalendarLoading, CalendarView } from "@/components/calendar/CalendarView.tsx";
import { MESSAGES } from "@/lib/i18n.ts";
import { requestLocale } from "@/lib/request-locale.ts";

export async function generateMetadata(): Promise<Metadata> {
  const t = MESSAGES[await requestLocale()];
  return { title: t.calTitle, description: t.calDescription };
}

export default function CalendarPage() {
  return (
    <Suspense fallback={<CalendarLoading />}>
      <CalendarView />
    </Suspense>
  );
}
