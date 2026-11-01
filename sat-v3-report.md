# 3-SAT scaling v3: wall hunt — COMPLETE (2026-10-29)

Pre-registered design (sat-scaling-v3.py): n = 100, 110, 120, 130,
150 at ratio 4.26, 20 reps, 30s cap, plain DPLL, seed-fixed
instances, per-instance data saved. Interrupted once by a runtime
restart (killed during n=130's print -- its write had already
landed); resumed detached (nohup) for n=150 only, no cells redone.

## Measured cells (20 reps each)

| n | SAT | UNSAT | TIMEOUT | timeout frac | solved median | censored median |
|---|-----|-------|---------|--------------|---------------|-----------------|
| 100 | 13 | 7 | 0 | 0.00 | 4.41s | 4.41s |
| 110 | 10 | 4 | 6 | 0.30 | 9.54s | 16.93s |
| 120 | 9 | 0 | 11 | 0.55 | 3.07s | 30.0s (cap) |
| 130 | 5 | 0 | 15 | 0.75 | 14.37s | 30.0s (cap) |
| 150 | 1 | 0 | 19 | 0.95 | 0.97s | 30.0s (cap) |

Solved median = median over solved instances only (v3's design).
Censored median = median over all 20 with TIMEOUT counted as 30s.

## Measured wall: bracket (110, 120]

Two independent definitions agree at n=120:
- First n with timeout majority (>50%): 120 (0.55).
- First n with censored median at the cap (30s): 120.
The wall is bracketed, not point-located: it falls between the
last mostly-solving cell (110, 30% timeouts) and the first
mostly-timing-out cell (120, 55%).

## v3's pre-registered fit: FAILED (returns None)

log_fit over solved medians (all cells) gives a NEGATIVE slope,
so no projected wall exists. Cause, stated plainly: solved
medians are survivor-biased at/after the wall. Hard instances
time out OUT of the median, so it falls as the wall is crossed
(120: 3.07s after 110: 9.54s) and collapses at 150, where a
single easy instance (0.97s) is the whole "median". The design's
projection step does not survive contact with the wall -- the
fit must exclude post-wall cells, or use censored medians, to
project at all. This failure is a finding, not a bug to hide.

## Pre-wall censored fit: projects 114.25 (6 vars EARLY)

Fit over pre-wall censored medians only (100: 4.41, 110: 16.93):
base 1.144, projected cap-crossing at n = 114.25. Measured wall
is 120, so the projection lands ~6 vars early. Why early: the
censored median at 110 sits at the solved distribution's ~65th
percentile (timeouts push the median's rank up the solved tail),
inflating the slope (censored jump 3.8x vs solved jump 2.2x
over the same 10 vars). And it uses only 2 points -- a line
through 2 points has no residual check, so its uncertainty is
unquantified. The gap is reported, not closed by re-fitting.

## The wall is UNSAT-driven

Past n=110, NO UNSAT instance solves within 30s (120: 0, 130: 0,
150: 0 UNSAT solved; every decided instance past 110 is SAT).
UNSAT proofs (full search trees) are what blow up; SAT witnesses
are still found. Consistent with v1/v2: naive DPLL pays full
UNSAT-proof cost past the transition.

## Growth rate: unchanged near the wall

Pre-wall censored base 1.144 vs v2's solved-median base ~1.13
over n=10..100: same ballpark. The wall is a cap-crossing (times
hitting 30s), not a change in the exponential base. Base remains
solver-specific and empirical, not a hardware property.

## Remaining gap (open, not launched)

The projection method needs a third pre-wall point (e.g. n=105)
or a rank-stable statistic to project accurately. Options:
(a) run n=105 (20 reps, ~2-4 min CPU) and refit over 3 pre-wall
censored points; (b) leave the wall as the measured bracket
(110, 120], which is already a complete finding. Either way the
bracket stands; the refinement only sharpens the projection.

## Refinement: n=105 (RUN 2026-10-29, perg's tap)

n=105: SAT=12, UNSAT=7, TIMEOUT=1 (5%), solved median 9.91s,
mean 11.76s, max 29.83s (one instance a hair under the cap).
Timeout progression now: 0 (100) -> 1 (105) -> 6 (110) -> 11
(120). The approach is flat, then steepens sharply between
105 and 110 -- not gradual.

3-point pre-wall fits (100, 105, 110):
- Censored: base 1.1441, projected wall 113.52, residuals
  (log10) 100: -0.0426, 105: +0.0851, 110: -0.0426. Gap vs
  measured 120: -6.48 vars (early, same as the 2-point fit's
  -5.75 -- the third point CONFIRMED the early bias, it did
  not close it).
- Solved: base 1.0803, projected wall 123.01, residuals
  100: -0.0615, 105: +0.1229, 110: -0.0615. Gap vs measured
  120: +3.01 vars (late -- the solved median stalls 105->110
  (9.91 -> 9.54) as the 6 hardest instances leave the solved
  set, so its slope is too shallow).
The two biased estimators STRADDLE the truth: 113.5 < 120 <
123.0. Censored is biased early (rank shift as timeouts grow);
solved is biased late (survivor removal). Neither alone
projects the wall.

CORRECTION to the v3 report above: the "two definitions
agreeing" at 120 are one fact, not two. Censored median = 30s
holds exactly when timeouts are the majority (for n=20, the
median of 20 with timeouts counted as 30 is 30 iff at least
11 are censored). Majority-timeout and censored-median-at-cap
are the same crossing stated twice. The bracket (110, 120]
stands on that one fact, plus the timeout counts themselves.

DEEPER LESSON (trajectory): the wall is a threshold (S-curve),
not an exponential. Timeout fractions 0 -> 0.05 -> 0.30 -> 0.55
-> 0.75 -> 0.95 rise, peak in per-step increment around
105-120, then decelerate -- an S-curve whose inflection sits
AT the wall. Pre-wall trends cannot see the inflection, so
every extrapolation from pre-wall data misses (early for
censored, late for solved). Exponential rates (base ~1.08-1.14)
DO extrapolate (they are pre-wall properties); threshold
crossings do not -- they must be BRACKETED, not extrapolated.
A Kaplan-Meier median would not change this: with all
censoring at the cap, it reduces to the same order statistic
as the censored median.

OPEN (bisection, not extrapolation): n=115 would narrow the
bracket (110, 120] to a 5-var half. That sharpens the location;
it is not another projection attempt.

## Bisection: n=115 (RUN 2026-10-29, perg's tap)

n=115: SAT=12, UNSAT=2, TIMEOUT=6 (30%), solved median 9.40s,
censored median 20.25s. Timeout fraction 0.30 <= 0.5, so the
bracket narrows to (115, 120] (5 vars).

Timeout progression now: 0 (100) -> 1 (105) -> 6 (110) -> 6
(115) -> 11 (120). The 110->115 plateau is at this resolution
only: 20 reps means 5% steps and a count SD near 2, so 6 vs 6
is consistent with noise on a smooth rise -- not evidence of
a real flat spot.

UNSAT refinement: 115 carries 2 solved UNSAT instances, the
only UNSAT solves in the wall region (110: 0, 120/130/150: 0).
The v3 claim softens from "zero UNSAT past 110" to "UNSAT
proofs become rare past 110 (4 -> 2 -> 0 across 110/115/120)
and vanish by 120; the wall's upper half is SAT-only."
Composition 110 -> 115 -> 120: SAT 10 -> 12 -> 9, UNSAT 4 ->
2 -> 0, TIMEOUT 6 -> 6 -> 11. 115 is the last cell where SAT
witnesses dominate (12/20).

Solved medians are FLAT across 105-115 (9.91, 9.54, 9.40)
while timeouts go 1 -> 6 -> 6: the solved set is the easy
tail, whose median cannot see the wall. (Confirms the
solved-fit lesson from n=105.)

NOISE FLOOR: (115, 120] is about as tight as 20-rep cells
support. Adjacent cells differ by ~5% in timeout fraction
(30% -> 55% over 5 vars) while one cell's count noise is
~10% (SD ~2 counts). Further bisection would be
noise-chasing; a tighter bracket needs more reps per cell,
not more cells.

## Second bisection: n=118 (RUN 2026-10-29, perg's tap)

n=118: SAT=9, UNSAT=1, TIMEOUT=10 (exactly 50%), solved
median 11.31s, censored median 29.85s. Exactly half is NOT a
majority, so under the majority definition the crossing is
still ahead: bracket narrows to (118, 120] (2 vars). Only one
integer remains inside it: 119.

Timeout progression now: 0 (100) -> 1 (105) -> 6 (110) -> 6
(115) -> 10 (118) -> 11 (120). UNSAT fade is the smoothest
signal in the region: 4 (110) -> 2 (115) -> 1 (118) -> 0
(120), monotone, no noise reversals -- UNSAT proofs thin out
steadily and are gone by 120. SAT falls from the 115 bulge
(12) to 9 at both 118 and 120.

Solved median finally moves: 9.91, 9.54, 9.40 across
105-115 (flat), then 11.31 at 118. The easy tail itself is
slowing now -- the whole distribution shifts right, not just
its hard tail (small-n caveat: 10 solved at 118).

Censored median 29.85s implies the largest solved instance
at 118 is 29.70s: solved and timeout instances sit 0.30s
apart at the cap. The cap slices a continuous distribution;
there is no natural break at 30s.

CAP RELATIVITY (derived, rough): this wall is cap-dependent,
not a universal constant. The phase transition (ratio ~4.26)
is cap-independent; the solve-time wall is the n where the
median solve time crosses the cap, so doubling the cap to
60s shifts the wall by about log(2)/log(1.13) ~= 5.7 vars,
to roughly 124-126. The bracket (118, 120] is the wall AT a
30s cap.

## Final bisection: n=119 (RUN 2026-10-29, perg's tap) -- CLOSED

n=119: SAT=5, UNSAT=2, TIMEOUT=13 (65%), solved median
10.59s, censored median 30.0s (cap). 65% is a majority, so
the bracket closes to (118, 119] -- 1 var wide, no integer
left to bisect. First majority cell = 119.

Timeout curve, complete: 0 (100) -> 1 (105) -> 6 (110) -> 6
(115) -> 10 (118) -> 13 (119) -> 11 (120) -> 15 (130) -> 19
(150). Note the reversal: 119 (13) exceeds 120 (11). That
is noise, not a peak -- a 2-count gap against a difference
SD near 2.8, and the trend past the wall rises steadily
(120: 55%, 130: 75%, 150: 95%).

UNSAT fade, complete: 4 (110) -> 2 (115) -> 1 (118) -> 2
(119) -> 0 (120). One 1-count blip at 119, within noise;
the fade holds overall.

Solved medians past the wall are noise: 10.59 (119, 7
solved) -> 3.07 (120, 9 solved) -> 14.37 (130, 5 solved) ->
0.97 (150, 1 solved). Tiny easy-tail sets; only the
timeout fraction is meaningful past the wall.

REPLICATION CAVEAT on the closure: 119's majority (13/20)
is the definitional answer, but with 20 reps its 95%
interval includes 50%, so a rerun of 119 could come back
10-11 and flip the bracket to (119, 120]. The series is
closed (no integer left), but the answer carries +-1 var
of replication noise. A higher-rep rerun at 119/120 would
firm it up; it is not launched.

FINAL WALL STATEMENT (plain DPLL, ratio 4.26, 30s cap,
20 reps/cell): first majority-timeout cell n=119, bracket
(118, 119]. Arc lessons: thresholds bracket, they do not
extrapolate; censored and solved fits straddle the truth;
the wall is cap-dependent while the phase transition is
not; the UNSAT fade is the smoothest wall-region signal;
solved medians past the wall are noise.

Files (mrfloppy): ~/sat-scaling/results-v3.json (cells +
log_fit), ~/sat-scaling/results-v3-analysis.json (censored
medians, bracket, pre-wall fit). Scripts: ~/workspace/
sat-scaling-v3.py, sat-scaling-v3-resume.py.

## Higher-rep rerun: 119 + 120 at 100 fresh reps (RUN
2026-10-29, perg's tap) -- COMPLETE

Scope: 100 FRESH reps per cell (rep indices 20..119 under
v3's seed scheme -- new instances, never repeats), same
DPLL, same 30s cap, CPU-only. Pooled n=120 per cell.

v1 HUNG (diagnosed, killed, nothing lost -- no cell had
finished): single-process design, one dpll call ran 20+
min at 99.8% CPU with zero log output (first progress
print due ~8-10 min; 20 reps x 30s hard cap => a print
MUST have existed by ~10.5 min). py-spy: simplify <-
unit_propagate <- dpll (x~20 recursion) <- solve_timed <-
fresh_cell. SigBlk 0, SigCgt 0x2000 (SIGALRM handler
installed), SigPnd 0 -- NOT a blocked signal or a
missing handler. Mechanism for the alarm never
terminating that one dpll call is UNKNOWN (stated, not
invented). Hang predates the LFM3 temp server; stack is
pure CPU dpll -- parallel work did NOT cause it.

v2 (subprocess per rep; parent SIGKILLs the child after
35s; a kill counts as TIMEOUT; per-rep checkpointing;
per-rep heartbeat prints; startup banner): COMPLETE, 0
ERRORS across all 200 fresh reps. The subprocess design
eliminates the v1 hang class. Mid-run the waiter died in
a runtime restart; the rerun survived (nohup), was
verified alive via checkpoints (119 done, 120 at
64/100), and the waiter was relaunched -- no work lost.

Results (fresh / pooled, Wilson 95%):
- 119: fresh SAT 43, UNSAT 5, TIMEOUT 52 (52%),
  (0.42, 0.62) | pooled 65/120 = 54.2%, (0.45, 0.63),
  majority_firm = NO.
- 120: fresh SAT 30, UNSAT 4, TIMEOUT 66 (66%),
  (0.56, 0.75) | pooled 77/120 = 64.2%, (0.55, 0.72),
  majority_firm = YES.

What the rerun did and did not do:
- CONFIRMED the count-bracket (118, 119]: 118 = 10/20 =
  50% (not >50%); 119 pooled = 65/120 = 54.2% (>50%).
  First count-majority cell = 119, unchanged. The
  rerun did NOT overturn the closure.
- Did NOT firm 119's majority at 95%: pooled interval
  (0.45, 0.63) still includes 50%. The true fraction at
  119 (~54%) is too close to 50% for 120 reps to exclude
  it (firming 54% at 95% needs ~600 reps). Pre-stated
  limit, borne out.
- First FIRMLY-majority cell = 120 (pooled 64.2%,
  interval (0.55, 0.72) excludes 50%). So: count-bracket
  (118, 119], firm-bracket (118, 120]. Both true; the
  distinction is the honest statement.
- Ordering RESTORED to monotone: fresh 119 (52%) <
  fresh 120 (66%), 14 points apart. The original 20-rep
  reversal (119: 65% > 120: 55%) was noise, as
  suspected. Pooled ordering 54.2% < 64.2%.
- UNSAT correction: fresh 120 has 4 UNSAT solves, not
  0. Pooled UNSAT rates: 119: 7/120 = 5.8%; 120: 4/120
  = 3.3%. The fade is real (35% at 100 -> ~3-6% at the
  wall) but it fades to ~4%, not to zero -- the 20-rep
  "0 at 120" was a small-sample artifact (4% expects
  0.8 in 20 reps). Language corrected: "fades to ~4%",
  not "vanishes".

FINAL WALL STATEMENT, revised (plain DPLL, ratio 4.26,
30s cap, pooled 120 reps at the wall cells): first
count-majority cell n=119, bracket (118, 119]; first
95%-firm majority cell n=120, firm-bracket (118, 120].

Files (mrfloppy): ~/sat-scaling/results-rerun-119.json,
results-rerun-120.json, rerun-summary.txt,
rerun-119-120-v2.log (v2 heartbeats),
rerun-119-120.log (v1, 0 bytes -- the hang's
signature). Scripts: ~/workspace/sat-rerun-119-120.py
(v1 -- hung design, do not reuse),
sat-rerun-119-120-v2.py + sat-solve-one.py (v2),
sat-rerun-launch.sh, sat-rerun-waiter.sh,
rerun-kill-restart.sh.

## Tail-noise bootstrap: is the past-wall bounce sampling
noise, or structural? (RUN 2026-10-29, perg's tap --
tail first, then the batch runner)

Question: past-wall 20-rep solved medians bounce 10.59
(119), 3.07 (120), 14.37 (130), 0.97 (150). The report
called them noise. This test measures whether that label
is earned, on SAVED per-instance data only (no new runs).

Method (pre-registered): reference pools from pre-wall
cells n = 100, 105, 110, 115 (solved sets mostly intact).
Two pools: flat regime 105-115 (cell medians 9.91, 9.54,
9.40 -- stable, nearest the wall) and all pre-wall
100-115 (sensitivity; 100's median 4.41 pulls it lower).
Each pool in two variants: all solved, SAT-only
(past-wall solved sets are SAT-dominated, so SAT-only
is the primary reference for a SAT-only set, and the
"all" pool is the right reference for a mixed set).
Bootstrap: for each past-wall k (20-rep 7/9/5/1, rerun
fresh 48/34, pooled 55/43), draw k with replacement,
take the median, 10,000 times (seed 12345). Verdict:
observed within the 95% interval -> consistent with
sampling; outside -> structural flag. Strength gradient:
k=1 nearly uninformative, k=55/43 decisive.

Results (all four 20-rep medians verified against the
files: MATCH):
- 20-rep 119 (k=7, 10.59): WITHIN all four references
  (intervals wide at k=7, e.g. [3.4, 22.1]).
- 20-rep 120 (k=9, 3.07): OUTSIDE three references
  (frac<=obs 0.003-0.021 -- an unusually FAST easy tail),
  WITHIN only the lowest (100-115 SAT-only, frac 0.090).
  This is the one small-k fluke.
- 20-rep 130 (k=5, 14.37): WITHIN all four.
- 20-rep 150 (k=1, 0.97): WITHIN all four, but the
  k=1 interval IS the full distribution ([0.04, 29.8]),
  so this is nearly uninformative -- a fast draw
  (6-17th percentile), not evidence either way.
- Rerun fresh 119 (k=48, 11.21): WITHIN both "all"
  references; OUTSIDE both SAT-only (frac 1.000).
- Rerun fresh 120 (k=34, 9.99): WITHIN both "all";
  OUTSIDE both SAT-only (frac 0.979-0.998).
- Pooled 119 (k=55, 11.13): WITHIN both "all";
  OUTSIDE both SAT-only (frac 1.000).
- Pooled 120 (k=43, 7.37): WITHIN ALL FOUR (SAT-only
  frac 0.496 -- dead center).

Reading (the subtlety matters): the SAT-only
"OUTSIDE" results for fresh/pooled 119 and fresh 120
are COMPOSITION artifacts, not structure. Those solved
sets are MIXED (119 fresh: 43 SAT + 5 UNSAT; pooled
119: 48 SAT + 7 UNSAT), and UNSAT proofs are slower
than SAT witnesses (reference medians: all 9.57 vs
SAT-only 7.08), so the slow UNSAT instances pull the
mixed median above the SAT-only distribution. The
correct reference for a mixed set is the "all" pool,
which passes in EVERY case. Comparing a mixed set to
a SAT-only reference manufactures false structure --
reference pools must match the solved set's
composition. Pooled 120, the cleanest large-k case,
passes even SAT-only.

VERDICT: the tail noise is EXPLAINED, not just
labeled. Mechanism: (a) the solved-time distribution
is extremely WIDE (pre-wall range 0.04-29.8s, ~750x),
so small-sample medians (k=1-9) bounce enormously --
at k=7-9 the 95% interval spans ~[3, 22]s, so a bounce
from 3 to 14 to 10 is EXPECTED; (b) composition
(SAT/UNSAT mix) shifts the median, and mismatched
references fake structure; (c) one small-k fluke
(20-rep 120) that does NOT replicate at large k
(fresh 9.99, pooled 7.37, both consistent). No
systematic wall effect on the easy tail survives the
large-k test: pooled medians (11.13, 7.37) straddle
the flat pre-wall regime (~9.5), both within noise.
The "noise" label stands, now measured.

Design input to the batch runner (from this test):
record per-call times with k attached (a tail median
from k=5 is not comparable to one from k=50 -- show
the interval, not just the point); separate by
category (like SAT/UNSAT) so composition doesn't
masquerade as structure; bootstrap the interval for
small-k tails (seed fixed).

Script: ~/workspace/tail-bootstrap.py (mrfloppy copy
run 2026-10-29; seed 12345, 10,000 draws).

## Gap analyses: node scaling, S-curve fit, distribution shape (2026-10-29)

Saved-data analysis only — no solver runs, no fleet contact beyond a read-only
copy, no router calls. Full findings: ~/workspace/sat-gap-analyses.md;
script: ~/workspace/sat-gap-analyses.py; numbers: ~/workspace/sat-gap-results.json.
Per-instance data exist only for n >= 100; below that the record is cell
medians, so pre-wall node analysis rests on medians.

**Node scaling — tracks within a cell, diverges across n.** Clean pre-wall
fit (v1+v2 cell medians, n = 10–100, no timeouts, no survivor bias):
nodes 1.087/var (log slope 0.0837 ± 0.0035, R² 0.983, 12 cells), time
1.127/var (log slope 0.1199 ± 0.0061, R² 0.975) — time grows ~3.7%/var
faster than nodes. Per-instance, log(nodes) vs log(time) r = 0.993 (k = 99
solved), per-cell r ≥ 0.990 everywhere: within a cell time is almost
perfectly determined by nodes, but the constant rises — median µs/node
15.2 (n = 10) → 448.2 (n = 100) → 811 (n = 119), ~66% across the wall
region alone. Mechanism unknown (clause-scanning alone predicts only
linear-in-n growth, slower than observed). UNSAT costs more only because
it visits ~2.5× more nodes (median 27,009 [24,977, 33,501], k = 23, vs SAT
10,609 [8,185, 13,737], k = 76; KS p = 1.6e-8) at the same µs/node (ratio of
medians 626 vs 614, within 2%). Post-wall medians are survivor-selected
(120: 4,432 nodes; 150: 1,031, k = 1) and are not trend points. Determinism
check: v2 and v3 n = 100 share identical median nodes (9,831.5); median
time differs 0.5% (timing jitter).

**S-curve fit — inflection ~118, consistent with both brackets.** Binomial
MLE logistic on timeout counts: pooled fit a = −17.63 ± 2.88,
b = 0.1497 ± 0.0243, inflection 117.79 ± 0.76 (SE), 95% CI (116.30, 119.28);
20-rep-only fit 119.21 ± 1.39 (dragged right by the 119 > 120 reversal).
All 9 pooled points fall inside their Wilson intervals of the fitted
curve; fitted 25% → 75% width 14.7 vars. The fit confirms the wall's
location and S-curve character but adjudicates NEITHER bracket — verdict
0, not a refutation: the 1-var count-vs-firm distinction is smaller than
the fit's SE. This is the inflection of the 30 s-cap curve (cap-dependent).

**Distribution shape — unimodal, left-skewed, fast tail.** Pre-wall solved
(n = 100–115, k = 67): median 8.58 s [5.71, 11.67], range 0.0065–29.83 s
(4,586×; the 750× figure was the 105–115 reference). Log10 skew −1.94,
KS vs normal p = 0.0195 (lognormal −1, weakly; normalized cut agrees,
p = 0.016). Histogram rises monotonically toward the cap — no valley, no
second peak — so two-moded is −1 on histogram evidence, even though a
2-component mixture fits better by BIC (broad low-weight component
absorbing the fast tail, not a second population). Power-law tail: 0
(untestable — upper tail cap-censored, lower tail only 9–15 instances).
SAT spans the full range (median 6.52 s); UNSAT lives only in a slow narrow
band (median 16.90 s, range 8.7×, fastest ~3.4 s; KS vs SAT p = 2.9e-6) —
proofs have a floor, witnesses do not. Composition, mechanism attached:
mixed median exceeds SAT-only in every cell with UNSAT solves (pooled
119/120: 9.86 vs 7.37 s, +34%, k = 98 vs 87, CIs overlapping), because
UNSAT proofs are slower and node-heavier at the same cost per node; as
UNSAT solves vanish past the wall, the mixed median converges to SAT-only.



---

# Addendum to sat-v3-report.md — MERGED 2026-10-30 (perg's word)

Status: merged 2026-10-30 on perg's word. Appended only; no existing section was rewritten (unmodified-data rule).

Sources (numbers copied verbatim; no recomputation in this draft):
- `~/workspace/sat-600rep-119-summary.md` (run completed 2026-10-29 ~17:53 EDT)
- `~/workspace/sat-60s-cap-summary.md` (run 2026-10-29, 14:56–16:13 EDT)

---

## Addendum A: n=119 firming — 600 pooled reps (30s cap, plain DPLL)

This resolves the exact open distinction the v3 report maintains:
count-bracket (118, 119] but firm-bracket (118, 120], because the
pooled 119 majority (54.2%) was not 95%-firm.

480 fresh reps (rep indices 120..599), v2 subprocess design, 0 errors.
Existing results files untouched (baselines verified unchanged).

| Set | SAT | UNSAT | TIMEOUT | n | Timeout frac | Wilson 95% |
|---|---|---|---|---|---|---|
| Fresh (reps 120..599) | 179 | 36 | 265 | 480 | 0.5521 | (0.51, 0.60) |
| Baseline pooled (orig 5/2/13 + rerun 43/5/52) | 48 | 7 | 65 | 120 | 0.5417 | (0.45, 0.63) |
| **Pooled (600)** | **227** | **43** | **330** | **600** | **0.5500** | **(0.51, 0.59)** |

**majority_firm = YES.** Pooled Wilson lower bound 0.510 > 0.50 (exact
interval (0.510, 0.589)). **Firm bracket = (118, 119].** Count and firm
brackets now AGREE at (118, 119].

Caveats (travel with the verdict):
- Firm but thin: lower bound 0.510 sits only ~1pp above 0.50. Firm by
  the pre-set rule (lower bound > 0.50), not a landslide.
- Fresh fraction (0.5521) is consistent with baseline (0.5417); no drift.
- UNSAT persists: pooled 119 UNSAT 43/600 = 7.2% (fresh 36/480 = 7.5%);
  at n=120 pooled UNSAT is 4/120 = 3.3%. The fade lands at a few
  percent, not zero.
- 120-extension condition NOT triggered, 120 NOT run: extension required
  pooled 119 ≥ 0.602 (within ~1 Wilson half-width of 120's 0.642);
  actual 0.550 is 9.2pp below. Ordering 119 < 120 holds on point
  estimates; 120 was already firm (77/120 = 64.2%, Wilson (0.55, 0.72)).

Files: mrfloppy `~/sat-scaling/results-600rep-119.json` (480 instances,
reps 120..599, all unique), `600rep-119-summary.txt`, `600rep-119-done`.

---

## Addendum B: 60s-cap wall-shift test (plain DPLL, ratio 4.26)

Prediction tested (derived pre-run in the v3 report): doubling the cap
30s → 60s shifts the wall by +5.7 vars (log(2)/log(1.13)) from
(118, 119] to ~124–126. Prediction: n=120 below majority timeouts,
n=124–126 around the crossing, n=130 majority.

Method: same plain DPLL, same seed scheme, cap change ONLY via
`v2.TIMEOUT_S = 60`; subprocess per rep, parent SIGKILL after 65s;
fresh rep ranges per cell (different instances from the 30s cells —
comparisons are population estimates, NOT paired outcomes). 0 errors
across 100 reps. CPU-only on mrfloppy, residents untouched.

| n | SAT | UNSAT | TIMEOUT | frac | Wilson 95% | solved median (s) | censored median (s) |
|---|-----|-------|---------|------|------------|-------------------|---------------------|
| 120 | 7 | 3 | 10 | 0.50 | (0.30, 0.70) | 16.59 | 59.42 |
| 124 | 6 | 5 | 9 | 0.45 | (0.26, 0.66) | 21.79 | 50.52 |
| 125 | 11 | 1 | 8 | 0.40 | (0.22, 0.61) | 23.49 | 46.26 |
| 126 | 7 | 0 | 13 | 0.65 | (0.43, 0.82) | 26.14 | 60.00 |
| 130 | 3 | 0 | 17 | 0.85 | (0.64, 0.95) | 30.49 | 60.00 |

Censored median = median over all 20 reps with TIMEOUT counted as 60.0.

Verdict — **prediction MATCHES, with two nuances:**
- Count-bracket (first cell > 50%): **(125, 126]**. 120 (0.50, not
  > 50%), 124 (0.45), 125 (0.40) are not majorities; 126 (0.65) is
  the first majority. The crossing lands inside the predicted 124–126.
- Firm-bracket over measured cells: **(126, 130]**. Only 130 is
  95%-firm (lower 0.64); 126's majority is NOT firm (0.43–0.82).
  127, 128, 129 are unmeasured, so a firm cell could sit inside
  (126, 130]; this is a statement about measured cells.
- Nuance 1: 120 is EXACTLY at 0.50 (10/20), not below it — "below
  majority" holds only in the strict "not a majority" sense.
- Nuance 2: the sequence is non-monotone (0.50 → 0.45 → 0.40 → 0.65
  → 0.85). The dip is within noise (intervals overlap heavily,
  Δ0.10 against per-cell SD ~0.11). Do not read structure into it
  at n=20 per cell.
- The point estimate behind the range (+5.7 → ~124.7) sits ~1 var
  below the observed first majority (126) — inside the predicted
  range, consistent given n=20 cells and unmeasured neighbours.

Secondary findings: solved medians rise monotonically with n
(16.59 → 30.49s) even while timeout fractions dip; UNSAT fade moves
right with the cap (UNSAT solves at 120, 124, 125, then zero at 126
and 130 — small numbers, noisy).

Limitations: n=20 per cell (wide intervals; only 130 firm); unmeasured
integers 121–123 and 127–129; the 60s wall is cap-dependent like the
30s wall — never present 126 as "the" wall without the cap attached.
Sharpened prediction already pinned (not launched): 120s cap → n≈133,
240s → n≈140.

Files: mrfloppy `~/sat-scaling/results-60s-cap-{120,124,125,126,130}.json`,
run dir `~/sat-60s-cap/`; local `sat-60s-cap-verify.py` (independent
recompute, ALL OK) and `sat-60s-cap-data/` (copies of the 5 cell JSONs).
No existing results files were modified.

---

## Updated wall statement (for the report's final section, on merge)

Plain DPLL, ratio 4.26: 30s-cap wall firm bracket **(118, 119]** (600
pooled reps at n=119, Wilson lower 0.510); 60s-cap wall count-bracket
**(125, 126]**, firm-bracket (126, 130] over measured cells. The wall is
a cap-dependent quantile (P(T ≤ cap) crossing 0.5), not a ceiling and
not cap-independent; the phase transition at ratio ~4.26 is the
cap-independent structure. UNSAT proofs fade to a few percent at the
wall, not to zero, at both caps.
