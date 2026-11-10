"use client";

// The court and the rally. Purely decorative: progress is on the board and the umpire's card,
// and nothing else on the page waits for an animation to fire.

import { useRef, useState } from "react";
import { type Shot, type Stage, nextShot } from "@/lib/loader.ts";
import type { Surface } from "@/lib/types.ts";
import styles from "./Court.module.css";

const SHOT_CLASS: Record<Shot, string> = {
  rally: styles.ballRally,
  clip: styles.ballClip,
  finish: styles.ballFinish,
};

export function Court({ surface, stage, corrections }: { surface: Surface; stage: Stage; corrections: number }) {
  const [shot, setShot] = useState<Shot>("rally");
  const clipped = useRef(0);

  // Called only while the ball is out of view, so changing shot never makes it jump.
  function changeShot() {
    const next = nextShot(stage, corrections, clipped.current);
    clipped.current = next.clipped;
    setShot(next.shot);
  }

  return (
    <div className={`slat ${styles.stage} sw-${surface.toLowerCase()} ${SHOT_CLASS[shot]}`} aria-hidden="true">
      <div className={styles.plane}>
        <div className={`${styles.along} ${styles.farSideline}`} />
        <div className={`${styles.along} ${styles.farSingles}`} />
        <div className={`${styles.along} ${styles.nearSingles}`} />
        <div className={`${styles.across} ${styles.leftBaseline}`} />
        <div className={`${styles.across} ${styles.rightBaseline}`} />
        <div className={`${styles.across} ${styles.leftService}`} />
        <div className={`${styles.across} ${styles.rightService}`} />
        <div className={`${styles.along} ${styles.centreService}`} />
        <div className={`${styles.along} ${styles.leftMark}`} />
        <div className={`${styles.along} ${styles.rightMark}`} />
      </div>
      <div className={styles.chalk} />
      {/* CSS Modules renames the keyframes, so the target and the shot identify the animation:
          the hop, squash and shadow animations bubble up to this element too. */}
      <div
        className={styles.flight}
        onAnimationIteration={(event) => {
          if (event.target === event.currentTarget && shot === "rally") changeShot();
        }}
        onAnimationEnd={(event) => {
          if (event.target === event.currentTarget && shot === "clip") changeShot();
        }}
      >
        <div className={styles.ballShadow} />
        <div className={styles.ballHop}>
          <div className={styles.ballSquash}>
            <svg width="26" height="26" viewBox="0 0 44 44" fill="none">
              <circle cx="22" cy="22" r="21" fill="#D9DD3C" />
              <path d="M7 7c9 8 9 22 0 30" stroke="#F6F7F2" strokeWidth="2.4" />
              <path d="M37 7c-9 8-9 22 0 30" stroke="#F6F7F2" strokeWidth="2.4" />
            </svg>
          </div>
        </div>
      </div>
      <svg className={styles.net} width="54" height="92" viewBox="0 0 54 92" fill="none">
        <path d="M14.4 39.5L14.4 79.4M22.8 34.2L22.8 70M30.3 28.1L30.3 61.5M37.1 21.4L37.1 53.8M43.3 14.1L43.3 46.8M5 80.8L14.4 71.4L22.8 62.8L30.3 54.8L37.1 47.3L43.3 40.2L49 33.6M5 71.6L14.4 63.5L22.8 55.6L30.3 48.1L37.1 40.8L43.3 33.7L49 26.8M5 62.4L14.4 55.5L22.8 48.5L30.3 41.4L37.1 34.3L43.3 27.2L49 20M5 53.2L14.4 47.5L22.8 41.3L30.3 34.7L37.1 27.8L43.3 20.6L49 13.2M5 90L49 40.4" stroke="#F6F7F2" strokeWidth="0.9" opacity="0.6" />
        <path d="M49 40.4V4.4" stroke="#0B261D" strokeWidth="2.6" />
        <path d="M5 44L14.4 39.5L22.8 34.2L30.3 28.1L37.1 21.4L43.3 14.1L49 6.4" stroke="#F6F7F2" strokeWidth="3.2" strokeLinejoin="round" />
        <path d="M5 90V42" stroke="#0B261D" strokeWidth="3.4" />
      </svg>
    </div>
  );
}
