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
# The last tournament start in the TML snapshot of 2026-11-07. Checks on 2026 count only
# tournaments that started by then, so accepting a newer snapshot doesn't move them (D-034).
# TML dates each match; a tournament's start is its earliest match date, as in the loaded data
# (D-010). Those checks read the file twice: once for the starts, then for the matches.
CUTOFF=20261026

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

echo "== 5. Sinner vs Alcaraz, every season (Sackmann 2015-2025 + TML 2026 up to the cutoff)"
for y in $(seq 2015 2025); do
  f="$S/atp_matches_$y.csv"
  awk -F, -v X="$EXCLUDE" -v E="$EXHIBITION" '
    (($11 == "Jannik Sinner" && $19 == "Carlos Alcaraz") || ($11 == "Carlos Alcaraz" && $19 == "Jannik Sinner")) &&
    index($24, X) == 0 && $2 !~ E { print $6, $3, ($11 == "Jannik Sinner" ? "W" : "L"), $2, $26 }' "$f"
done
awk -F, -v X="$EXCLUDE" -v E="$EXHIBITION" -v C="$CUTOFF" '
  NR == FNR { if (FNR > 1 && (!($1 in s) || $7 < s[$1])) s[$1] = $7; next }
  FNR > 1 && s[$1] <= C &&
  (($12 == "Jannik Sinner" && $22 == "Carlos Alcaraz") || ($12 == "Carlos Alcaraz" && $22 == "Jannik Sinner")) &&
  index($29, X) == 0 && $2 !~ E { print $7, $3, ($12 == "Jannik Sinner" ? "W" : "L"), $2, $31 }' "$T" "$T"

echo "== 6. Sinner's last 5 matches in TML 2026 up to the cutoff (columns: 7 match date, 12 winner, 22 loser, 31 round, 17/27 ranks)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" -v C="$CUTOFF" '
  NR == FNR { if (FNR > 1 && (!($1 in s) || $7 < s[$1])) s[$1] = $7; next }
  FNR > 1 && s[$1] <= C && ($12 == P || $22 == P) && index($29, X) == 0 {
    print $7, $2, $31, ($12 == P ? "W" : "L"), ($12 == P ? $22 : $12), "rank=" ($12 == P ? $17 : $27) }' "$T" "$T" | sort -r | head -5

echo "== 7. Alcaraz 2026 (TML) up to the cutoff, win-loss"
awk -F, -v P="Carlos Alcaraz" -v X="$EXCLUDE" -v E="$EXHIBITION" -v C="$CUTOFF" '
  NR == FNR { if (FNR > 1 && (!($1 in s) || $7 < s[$1])) s[$1] = $7; next }
  FNR > 1 && s[$1] <= C && ($12 == P || $22 == P) && index($29, X) == 0 && $2 !~ E { if ($12 == P) w++; else l++ }
  END { printf "%d-%d\n", w, l }' "$T" "$T"

echo "== 8. Alexander Zverev 2024: exhibition matches, other counted matches"
awk -F, -v P="Alexander Zverev" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  ($11 == P || $19 == P) && index($24, X) == 0 { if ($2 ~ E) ex++; else n++ }
  END { printf "exhibitions %d, other matches %d\n", ex, n }' "$S/atp_matches_2024.csv"

echo "== 9. Player IDs (atp_players.csv: id, first, last)"
grep -E "^(206173|100644|104999|207352|200000|207989|104925|106421|104755|133975|200031|209950|207518|126203)," "$S/atp_players.csv" | cut -d, -f1-3

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

# ---------- Milestones 8 and 9 (D-029, D-030). Columns are looked up by header name. ----------

echo "== 21. Sinner 2024 set patterns, completed matches only (D-029)"
awk -F, -v P="Jannik Sinner" -v E="$EXHIBITION" '
  NR == 1 { for (i = 1; i <= NF; i++) c[$i] = i; next }
  ($c["winner_name"] == P || $c["loser_name"] == P) && $c["tourney_name"] !~ E {
    s = toupper($c["score"]); if (s ~ /RET|DEF/) { early++; next }; if (s ~ /W\/O|WALKOVER|ABD/ || s == "") next
    n = split($c["score"], t, " "); me = ($c["winner_name"] == P); ws = 0; ls = 0
    for (k = 1; k <= n; k++) if (t[k] !~ /^(\[[0-9]+-[0-9]+\]|[0-9]+-[0-9]+(\([0-9]+\))?)$/) next
    for (k = 1; k <= n; k++) {
      x = t[k]; gsub(/[][]/, "", x); sub(/\(.*/, "", x); split(x, g, "-"); a = g[1] + 0; b = g[2] + 0
      if (a > b) ws++; else ls++
      mine[k] = me ? a : b; theirs[k] = me ? b : a
      tb[k] = (t[k] ~ /\(/ || (a == 7 && b == 6) || (a == 6 && b == 7)) }
    if (ws <= ls) next  # a score that contradicts the winner is an unknown result (D-007)
    for (k = 1; k <= n; k++) if (tb[k]) { tbp++; if (mine[k] > theirs[k]) tbw++ }
    if (n == $c["best_of"]) { dp++; if (me) dw++ }  # all sets played: the last one decided it
    if (mine[1] > theirs[1]) { w1p++; if (me) w1w++ } else { l1p++; if (me) l1w++ }
    done++ }
  END { printf "completed %d, ended early %d; tiebreaks %d/%d; deciding sets %d/%d; after winning set 1 %d/%d; after losing set 1 %d/%d\n",
               done, early, tbw, tbp, dw, dp, w1w, w1p, l1w, l1p }' "$S/atp_matches_2024.csv"

echo "== 22. Djokovic 2024 against opponents ranked 10 or better at the time, and opponents with no ranking"
awk -F, -v P="Novak Djokovic" -v X="$EXCLUDE" -v E="$EXHIBITION" '
  NR == 1 { for (i = 1; i <= NF; i++) c[$i] = i; next }
  ($c["winner_name"] == P || $c["loser_name"] == P) && index($c["score"], X) == 0 && $c["tourney_name"] !~ E {
    r = ($c["winner_name"] == P ? $c["loser_rank"] : $c["winner_rank"])
    if (r == "") { unknown++; who = ($c["winner_name"] == P ? $c["loser_name"] : $c["winner_name"]); next }
    if (r + 0 <= 10) { if ($c["winner_name"] == P) w++; else l++ } }
  END { printf "top 10: %d-%d; unranked opponents: %d (%s)\n", w, l, unknown, who }' "$S/atp_matches_2024.csv"

echo "== 23. Sinner's last 10 counted matches in TML 2026 up to the cutoff: minutes (tourney_date is the match date in TML)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" -v E="$EXHIBITION" -v C="$CUTOFF" '
  FNR == 1 { for (i = 1; i <= NF; i++) c[$i] = i; next }
  NR == FNR { t = $c["tourney_id"]; d = $c["tourney_date"]; if (!(t in s) || d < s[t]) s[t] = d; next }
  s[$c["tourney_id"]] <= C && ($c["winner_name"] == P || $c["loser_name"] == P) && index($c["score"], X) == 0 && $c["tourney_name"] !~ E {
    print $c["tourney_date"], ($c["minutes"] == "" ? "none" : $c["minutes"]) }' "$T" "$T" | sort -r | head -10 |
  awk '{ if ($2 == "none") missing++; else { n++; total += $2; if ($2 > longest) longest = $2 } }
       END { printf "with minutes %d, missing %d, total %d, longest %d\n", n, missing, total, longest }'

echo "== 24. Grass 2023, service points won by player, players with 10+ matches with stats (no 2023 stats were removed by D-008)"
awk -F, -v X="$EXCLUDE" -v E="$EXHIBITION" '
  NR == 1 { for (i = 1; i <= NF; i++) c[$i] = i; next }
  $c["surface"] == "Grass" && index($c["score"], X) == 0 && $c["tourney_name"] !~ E && $c["w_svpt"] != "" && $c["l_svpt"] != "" {
    s = toupper($c["score"]); if (s ~ /ABD/ || s == "") next
    w = $c["winner_name"]; l = $c["loser_name"]
    n[w]++; won[w] += $c["w_1stWon"] + $c["w_2ndWon"]; pts[w] += $c["w_svpt"]
    n[l]++; won[l] += $c["l_1stWon"] + $c["l_2ndWon"]; pts[l] += $c["l_svpt"] }
  END { for (p in n) if (n[p] >= 10) printf "%.6f %d/%d %d %s\n", won[p] / pts[p], won[p], pts[p], n[p], p }' "$S/atp_matches_2023.csv" |
  sort -rn | awk '{ print NR ". " $0 }'

C=data/raw/charting
echo "== 26. Sinner's charted Roland Garros 2024 matches: serve direction, rally length, net points (D-030)"
awk -F, -v P="Jannik Sinner" '
  FILENAME ~ /matches/ { if ($1 ~ /^2024[0-9]*-M-Roland_Garros-/ && ($2 == P || $3 == P)) { id[$1] = 1; first[$1] = ($2 == P) } ; next }
  FILENAME ~ /ServeDirection/ && ($1 in id) && $2 == P && ($3 == "1" || $3 == "2") {
    for (k = 4; k <= 9; k++) d[$3, k] += $k }
  FILENAME ~ /Rally/ && ($1 in id) && $4 ~ /^(1-3|4-6|7-9|10|Total)$/ {
    played[$4] += $5; won[$4] += (first[$1] ? $6 : $10) }
  FILENAME ~ /NetPoints/ && ($1 in id) && $2 == P && $3 == "NetPoints" { net += $4; netwon += $5 }
  END {
    printf "charted matches %d\n", length(id)
    printf "first serves in  deuce wide %d body %d T %d; ad wide %d body %d T %d\n", d[1,4], d[1,5], d[1,6], d[1,7], d[1,8], d[1,9]
    printf "second serves    deuce wide %d body %d T %d; ad wide %d body %d T %d\n", d[2,4], d[2,5], d[2,6], d[2,7], d[2,8], d[2,9]
    printf "rally points won 1-3 %d/%d, 4-6 %d/%d, 7-9 %d/%d, 10+ %d/%d, all %d/%d\n", won["1-3"], played["1-3"], won["4-6"], played["4-6"],
           won["7-9"], played["7-9"], won["10"], played["10"], won["Total"], played["Total"]
    printf "net points won %d/%d\n", netwon, net }' "$C/charting-m-matches.csv" "$C/charting-m-stats-ServeDirection.csv" \
  "$C/charting-m-stats-Rally.csv" "$C/charting-m-stats-NetPoints.csv"

echo "== 25. Sinner's 2023 Davis Cup matches: minutes (the match files have none for these)"
awk -F, -v P="Jannik Sinner" -v X="$EXCLUDE" '
  NR == 1 { for (i = 1; i <= NF; i++) c[$i] = i; next }
  ($c["winner_name"] == P || $c["loser_name"] == P) && index($c["score"], X) == 0 && $c["tourney_level"] == "D" {
    n++; if ($c["minutes"] == "") missing++; else { timed++; total += $c["minutes"] } }
  END { printf "matches %d, with minutes %d, missing %d, total %d\n", n, timed, missing, total }' "$S/atp_matches_2023.csv"

echo "== 27. The 2025 Roland Garros final as the file writes it (winner first), to read from Sinner's side by hand"
awk -F, 'NR == 1 { for (i = 1; i <= NF; i++) c[$i] = i; next }
  $c["tourney_name"] == "Roland Garros" && $c["round"] == "F" { print $c["winner_name"], "d.", $c["loser_name"], $c["score"] }' "$S/atp_matches_2025.csv"

echo "== 28. Laaksonen 2015 tiebreaks: his Davis Cup match against Bemelmans has a bare 6-7 set (no tiebreak score)"
awk -F, -v P="Henri Laaksonen" -v E="$EXHIBITION" '
  NR == 1 { for (i = 1; i <= NF; i++) c[$i] = i; next }
  ($c["winner_name"] == P || $c["loser_name"] == P) && $c["tourney_name"] !~ E {
    s = toupper($c["score"]); if (s ~ /RET|DEF|W\/O|WALKOVER|ABD/ || s == "") next
    n = split($c["score"], t, " "); me = ($c["winner_name"] == P)
    for (k = 1; k <= n; k++) {
      x = t[k]; gsub(/[][]/, "", x); sub(/\(.*/, "", x); split(x, g, "-"); a = g[1] + 0; b = g[2] + 0
      if (t[k] ~ /\(/ || (a == 7 && b == 6) || (a == 6 && b == 7)) { played++; if ((me ? a : b) > (me ? b : a)) won++
        if (t[k] !~ /\(/) print "bare:", $c["tourney_name"], $c["score"] } } }
  END { printf "tiebreaks %d/%d\n", won, played }' "$S/atp_matches_2015.csv"

echo "== 29. Return points won against first and second serves (D-033): Sinner 2024 (Sackmann), Alcaraz 2026 (TML) up to the cutoff"
# The opponent's serve, read from the other side: points they didn't win are the returner's.
# Second-serve points are serve points minus first serves in, so double faults are included.
for args in "Jannik Sinner|$S/atp_matches_2024.csv" "Carlos Alcaraz|$T"; do
  awk -F, -v P="${args%%|*}" -v X="$EXCLUDE" -v E="$EXHIBITION" -v C="$CUTOFF" '
    FNR == 1 { for (i = 1; i <= NF; i++) c[$i] = i; next }
    NR == FNR { t = $c["tourney_id"]; d = $c["tourney_date"]; if (!(t in s) || d < s[t]) s[t] = d; next }
    s[$c["tourney_id"]] <= C && ($c["winner_name"] == P || $c["loser_name"] == P) && index($c["score"], X) == 0 && $c["tourney_name"] !~ E &&
    $c["w_svpt"] != "" && $c["l_svpt"] != "" {
      o = ($c["winner_name"] == P) ? "l_" : "w_"
      fin += $c[o "1stIn"]; fwon += $c[o "1stWon"]; sp += $c[o "svpt"]; swon += $c[o "2ndWon"] }
    END { printf "%s: against first serves %d/%d, against second serves %d/%d\n", P, fin - fwon, fin, sp - fin - swon, sp - fin }' "${args#*|}" "${args#*|}"
done

echo "== 30. Season paths (D-035): each tournament's start, name, counted win-loss, walkovers, and its last round with the result"
# The last round is the highest in the draw's order (R128 R64 R32 R16 RR QF SF BR F), then the
# highest match number. Walkovers are listed (wo=) but not counted; exhibitions are left out.
path() {
  awk -F, -v P="$1" -v X="$EXCLUDE" -v E="$EXHIBITION" '
    BEGIN { split("R128 R64 R32 R16 RR QF SF BR F", r, " "); for (i in r) ord[r[i]] = i }
    ($11 == P || $19 == P) && $2 !~ E {
      t = $1; if (!(t in start)) { start[t] = $6; name[t] = $2; n++; order[n] = t }
      won = ($11 == P); wo = index($24, X) > 0
      if (wo) walk[t]++; else if (won) w[t]++; else l[t]++
      k = ord[$26] * 1000 + $7
      if (!(t in best) || k > best[t]) { best[t] = k; last[t] = $26 " " (won ? "W" : "L") (wo ? " W/O" : "") }
    }
    END { for (i = 1; i <= n; i++) { t = order[i]; printf "%s %s %d-%d wo=%d last=%s\n", start[t], name[t], w[t], l[t], walk[t], last[t] } }' "$2" | sort
}
path "Jannik Sinner" "$S/atp_matches_2025.csv"
path "Arthur Fils" "$S/atp_matches_2025.csv" | grep "Roland Garros"
path "Lorenzo Musetti" "$S/atp_matches_2024.csv" | grep -E "Olympics|ITA vs ARG"
path "Felix Auger Aliassime" "$S/atp_matches_2024.csv" | grep "Olympics"
path "Alexander Zverev" "$S/atp_matches_2025.csv" | grep -E "Tour Finals|United Cup"
path "Taylor Fritz" "$S/atp_matches_2025.csv" | grep -E "Tour Finals|United Cup"
