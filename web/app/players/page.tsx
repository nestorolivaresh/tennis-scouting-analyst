import type { Metadata } from "next";
import { Suspense } from "react";
import { PlayerStatsLoading, PlayerStatsView } from "@/components/stats/PlayerStatsView.tsx";

export const metadata: Metadata = {
  title: "Player stats | Tennis Scouting Analyst",
  description: "ATP tour-level singles records, serve and return numbers from tested database queries, with no AI model involved.",
};

export default function PlayersPage() {
  return (
    <Suspense fallback={<PlayerStatsLoading />}>
      <PlayerStatsView />
    </Suspense>
  );
}
