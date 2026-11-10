import type { Metadata } from "next";
import { Suspense } from "react";
import { PlayerStatsLoading, PlayerStatsView } from "@/components/stats/PlayerStatsView.tsx";
import { MESSAGES } from "@/lib/i18n.ts";
import { requestLocale } from "@/lib/request-locale.ts";

export async function generateMetadata(): Promise<Metadata> {
  const t = MESSAGES[await requestLocale()];
  return { title: t.playersTitle, description: t.playersDescription };
}

export default function PlayersPage() {
  return (
    <Suspense fallback={<PlayerStatsLoading />}>
      <PlayerStatsView />
    </Suspense>
  );
}
