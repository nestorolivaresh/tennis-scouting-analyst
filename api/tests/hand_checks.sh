#!/bin/sh
# Hand checks for the stats-layer tests (api/tests/test_stats.py).
#
# These compute expected values straight from the raw CSV files with awk. They share no code
# with ingest/ or api/, so a bug there can't also hide in the expected values. Plain comma
# splitting is safe: every row has the same field count and no field is quoted (checked
# 2026-11-07). Rules applied by hand, as in docs/decisions.md: walkovers ("W/O") and
# exhibitions (Laver Cup, NextGen) don't count. Only check 14 involves an "unknown" result
# (a score that contradicts the listed winner, D-007); it prints that row so it can be read.
# The outputs are recorded in docs/stat-checks.md.
#
# Usage, from the repo root after ingest.download: sh api/tests/hand_checks.sh

S=data/raw/sackmann
T=data/raw/tml/2026.csv
EXCLUDE='W/O'
EXHIBITION='Laver Cup|Next ?Gen'

echo "== 1. Sinner 2024, win-loss by surface (Sackmann columns: 3 surface, 11 winner, 19 loser, 24 score)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  ($11 == P || $19 == P) && index($24, X) == 0 && $2 !~ E {
    if ($11 == P) won[$3]++; else lost[$3]++; seen[$3] = 1 }
  END { for (s in seen) printf "%s %d-%d\n", s, won[s], lost[s] }' "$S/atp_matches_2024.csv" | sort

echo "== 2. Sinner 2024, walkovers"
awk -F, -v P="Jannik Sinner" '($11 == P || $19 == P) && index($24, "W/O") > 0' "$S/atp_matches_2024.csv" | wc -l

echo "== 3. Sinner 2024 on clay, break points (35/36 winner saved/faced, 44/45 loser saved/faced)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" '
  ($11 == P || $19 == P) && $3 == "Clay" && index($24, X) == 0 && $30 != "" && $39 != "" {
    if ($11 == P) { saved += $35; faced += $36; chances += $45; conv += $45 - $44 }
    else          { saved += $44; faced += $45; chances += $36; conv += $36 - $35 } }
  END { printf "saved %d/%d, converted %d/%d\n", saved, faced, conv, chances }' "$S/atp_matches_2024.csv"

echo "== 4. Alcaraz 2023 on clay: first serves in, serve points, aces, matches with stats"
awk -F, -v P="Carlos Alcaraz" -v X="$EXCLUDE" '
  ($11 == P || $19 == P) && $3 == "Clay" && index($24, X) == 0 && $30 != "" && $39 != "" {
    n++; if ($11 == P) { fi += $31; sp += $30; ac += $28 } else { fi += $40; sp += $39; ac += $37 } }
  END { printf "first_in %d / serve_points %d, aces %d over %d matches\n", fi, sp, ac, n }' "$S/atp_matches_2023.csv"

echo "== 5. Sinner vs Alcaraz, every season (Sackmann 2015-2025 + TML 2026)"
for y in $(seq 2015 2025); do
  f="$S/atp_matches_$y.csv"
  awk -F, -v X="$EXCLUDE" -v E="$EXHIBITION" '
    (($11 == "Jannik Sinner" && $19 == "Carlos Alcaraz") || ($11 == "Carlos Alcaraz" && $19 == "Jannik Sinner")) &&
    index($24, X) == 0 && $2 !~ E { print $6, $3, ($11 == "Jannik Sinner" ? "W" : "L"), $2, $26 }' "$f"
done
awk -F, -v X="$EXCLUDE" -v E="$EXHIBITION" '
  (($12 == "Jannik Sinner" && $22 == "Carlos Alcaraz") || ($12 == "Carlos Alcaraz" && $22 == "Jannik Sinner")) &&
  index($29, X) == 0 && $2 !~ E { print $7, $3, ($12 == "Jannik Sinner" ? "W" : "L"), $2, $31 }' "$T"

echo "== 6. Sinner's last 5 matches in TML 2026 (columns: 7 match date, 12 winner, 22 loser, 31 round, 17/27 ranks)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" '
  ($12 == P || $22 == P) && index($29, X) == 0 {
    print $7, $2, $31, ($12 == P ? "W" : "L"), ($12 == P ? $22 : $12), "rank=" ($12 == P ? $17 : $27) }' "$T" | sort -r | head -5

echo "== 7. Alcaraz 2026 (TML), win-loss"
awk -F, -v P="Carlos Alcaraz" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  ($12 == P || $22 == P) && index($29, X) == 0 && $2 !~ E { if ($12 == P) w++; else l++ }
  END { printf "%d-%d\n", w, l }' "$T"

echo "== 8. Alexander Zverev 2024: exhibition matches, other counted matches"
awk -F, -v P="Alexander Zverev" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  ($11 == P || $19 == P) && index($24, X) == 0 { if ($2 ~ E) ex++; else n++ }
  END { printf "exhibitions %d, other matches %d\n", ex, n }' "$S/atp_matches_2024.csv"

echo "== 9. Player IDs (atp_players.csv: id, first, last)"
grep -E "^(206173|100644|104999|207352|200000|207989|104925|106421|104755|133975|200031)," "$S/atp_players.csv" | cut -d, -f1-3

echo "== 10. Sinner 2024 against left-handers (opponent hand from the match row: 12 winner_hand, 20 loser_hand)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  ($11 == P || $19 == P) && index($24, X) == 0 && $2 !~ E {
    hand = ($11 == P ? $20 : $12); if (hand == "L") { if ($11 == P) w++; else l++ } else if (hand != "R") u++ }
  END { printf "against L %d-%d, opponents with unknown hand %d\n", w, l, u }' "$S/atp_matches_2024.csv"

echo "== 11. Sinner, tournaments starting exactly 2024-01-15 (column 6)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" '
  ($11 == P || $19 == P) && index($24, X) == 0 && $6 == "20240115" { t[$2] = 1; if ($11 == P) w++; else l++ }
  END { for (n in t) printf "%s ", n; printf "%d-%d\n", w, l }' "$S/atp_matches_2024.csv"

echo "== 12. Sinner 2024 by tournament level (column 5)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  ($11 == P || $19 == P) && index($24, X) == 0 && $2 !~ E { if ($11 == P) w[$5]++; else l[$5]++; seen[$5] = 1 }
  END { for (v in seen) printf "%s %d-%d\n", v, w[v], l[v] }' "$S/atp_matches_2024.csv" | sort

echo "== 13. Alcaraz 2022: matches, matches with stats, aces over the matches with stats"
awk -F, -v P="Carlos Alcaraz" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  ($11 == P || $19 == P) && index($24, X) == 0 && $2 !~ E {
    n++; if ($30 != "" && $39 != "") { ws++; ac += ($11 == P ? $28 : $37) } }
  END { printf "matches %d, with stats %d, aces %d\n", n, ws, ac }' "$S/atp_matches_2022.csv"

echo "== 14. Gasquet 2018: matches that aren't walkovers, and the Davis Cup row whose score contradicts its winner"
awk -F, -v P="Richard Gasquet" -v X="$EXCLUDE" '($11 == P || $19 == P) && index($24, X) == 0' "$S/atp_matches_2018.csv" | wc -l
awk -F, -v P="Richard Gasquet" '($11 == P || $19 == P) && $2 ~ /Davis Cup/ && $24 ~ /\[/ { print $2 ": winner", $11, "score", $24 }' "$S/atp_matches_2018.csv"

echo "== 15. Benjamin Hassan 2023: matches with no surface (column 3 empty)"
awk -F, -v P="Benjamin Hassan" -v X="$EXCLUDE" '($11 == P || $19 == P) && index($24, X) == 0 && $3 == "" { print $2, $24 }' "$S/atp_matches_2023.csv"

echo "== 16. Sinner bio (atp_players.csv: 1 id, 4 hand, 6 country, 7 height; birth date not printed)"
grep "^206173," "$S/atp_players.csv" | cut -d, -f1,4,6,7

echo "== 17. Data window: first Sackmann 2015 tournament date, last TML 2026 tournament start and match date"
awk -F, 'NR > 1 { print $6 }' "$S/atp_matches_2015.csv" | sort | head -1
awk -F, 'NR > 1 { if (!($1 in s) || $7 < s[$1]) s[$1] = $7; if ($7 > last) last = $7 }
  END { for (t in s) if (s[t] > start) start = s[t]; printf "last tournament start %s, last match %s\n", start, last }' "$T"

echo "== 18. Sinner 2024: matches ended by a retirement or default (the player who quit is the loser)"
awk -F, -v P="Jannik Sinner" '($11 == P || $19 == P) && $24 ~ /RET|DEF/ { print $2, $26, "winner", $11, "loser", $19, $24 }' "$S/atp_matches_2024.csv"

echo "== 19. Lucas Catarina: newest match (TML 2026, rank 17/27) and newest ranked match (Sackmann, rank 46/48)"
awk -F, -v P="Lucas Catarina" '$12 == P || $22 == P { print $7, $2, $31, "rank=" ($12 == P ? $17 : $27) }' "$T" | sort -r | head -1
for y in $(seq 2015 2025); do
  awk -F, -v P="Lucas Catarina" '($11 == P && $46 != "") || ($19 == P && $48 != "") {
    print $6, $7, $2, $26, "rank=" ($11 == P ? $46 : $48) }' "$S/atp_matches_$y.csv"
done | sort -n | tail -1

echo "== 20. Djokovic 2024 by opponent hand (12 winner_hand, 20 loser_hand; anything but R or L is unknown)"
awk -F, -v P="Novak Djokovic" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  ($11 == P || $19 == P) && index($24, X) == 0 && $2 !~ E {
    hand = ($11 == P ? $20 : $12); if (hand != "R" && hand != "L") { hand = "unknown"; who = ($11 == P ? $19 : $11) }
    if ($11 == P) w[hand]++; else l[hand]++; seen[hand] = 1 }
  END { for (h in seen) printf "%s %d-%d\n", h, w[h], l[h]; print "unknown-hand opponent:", who }' "$S/atp_matches_2024.csv" | sort
