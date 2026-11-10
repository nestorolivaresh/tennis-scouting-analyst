import type { ComponentPropsWithoutRef } from "react";
import styles from "./Board.module.css";

const CORNERS = [styles.topLeft, styles.topRight, styles.bottomLeft, styles.bottomRight];

/** The green board with four brass rivets. Passes className, aria-labelledby and any other section attribute through. */
export function Board({ className, children, ...section }: ComponentPropsWithoutRef<"section">) {
  return (
    <section {...section} className={`on-green ${styles.board}${className ? ` ${className}` : ""}`}>
      {CORNERS.map((corner) => (
        <span key={corner} className={`rivet ${corner}`} aria-hidden="true" />
      ))}
      {children}
    </section>
  );
}
