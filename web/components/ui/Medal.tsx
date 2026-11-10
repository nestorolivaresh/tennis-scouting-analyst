import { initials } from "@/lib/people.ts";
import { Flag } from "./Flag.tsx";

export type MedalProps = {
  name: string;
  country: string | null | undefined;
  tone: "player" | "opponent";
  /** report: 72 px. setup: 52 px, with a white flag border for the white card. phone: 54 px. */
  size?: "report" | "setup" | "phone";
};

/** A player's monogram in a brass ring, with their flag pinned on when there is one to draw. */
export function Medal({ name, country, tone, size = "report" }: MedalProps) {
  return (
    <span className={`medal medal-${tone}${size === "report" ? "" : ` medal-${size}`}`}>
      {/* The name is always shown beside the medal, so the letters would only be read out twice. */}
      <span aria-hidden="true">{initials(name)}</span>
      <Flag country={country} className="pin" />
    </span>
  );
}
