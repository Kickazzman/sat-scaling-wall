# sat-scaling-wall

3-SAT solver scaling wall: plain DPLL, watched literals, VSIDS, heap-ordered
pick, and clause learning with backjumping, at ratio 4.26 with a 30-second cap
on mrfloppy CPU. Brackets are quantiles under the cap, not ceilings.

## Results (as measured, 2026-10-29)

- Plain DPLL: firm bracket (118, 119].
- Watched literals: (173, 174].
- VSIDS: (200, 201] — does NOT hold under the heap pick.
- Heap-ordered pick: wall above 201 (390/390 identical verdicts and node
  counts vs VSIDS, ~4x lower cost per node). (200, 201] must not be quoted
  as the heap solver's wall.
- Clause learning + backjumping (CDCL): count bracket (235, 236]; firming
  at n=236 failed (47/100), bar as written not met. Stage 4 not launched.

## Contents

- `sat-solver-v2.py` … `sat-solver-v5.py` (including `sat-solver-v4-heap.py`,
  the heap-ordered pick) — solvers as run.
- `sat-v3-report.md` — v3 report.
- `results-v3.json` — per-instance data (source: `~/sat-scaling/results-v3.json`
  on mrfloppy).

## Credit

Research by Joshua McClain (Kickazzman).
Research partner: cobrajet (GitHub: cobrajet302gt).
License: MIT — see LICENSE. Free use for anyone, with the copyright and
permission notice kept. Provenance: see RECORD.md and REDACTION-LOG.md.
