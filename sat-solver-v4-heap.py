#!/usr/bin/env python3
"""Stage 2b solver: Stage 2 (VSIDS) + heap-ordered variable pick (v4-heap).

IMPLEMENTATION REFINEMENT ONLY, not a new technique: the branching
decisions are IDENTICAL to Stage 2 (sat-solver-v4.py) — same VSIDS
activities, same candidate set, same tie-breaking — made at lower
per-node cost. Everything else — gen_instance (v3 seed scheme),
watched-literal propagation, trail/backtrack structure, True-first
polarity, node counting (1 root + 1 per branch assignment), 30s cap,
CLI — is identical to Stage 2.

Why the pick can be heap-ordered without changing decisions:
- VSIDS activities change ONLY on conflicts (bump_conflict). Between
  conflicts the activity ordering is fixed.
- Stage 2's pick_branch returns: among unassigned variables occurring
  in non-satisfied clauses, the one with max activity; ties resolve to
  the earliest first-visit in clause-major scan order over
  non-satisfied clauses (strict-greater replacement, clauses scanned
  in index order, literals in clause order, satisfied clauses
  skipped).
- This solver maintains activity LEVELS: dict activity -> set of
  variables, plus the sorted list of distinct activities. The pick
  scans levels from the maximum down and, within the first level
  that holds a candidate, takes the minimum scan key, where
  scan_key(v) = (index, position) of v's first occurrence in a
  currently non-satisfied clause. Min scan key over max-activity
  candidates == first-visited max-activity candidate in the full
  scan. The candidate set (unassigned + occurs in a non-satisfied
  clause) is evaluated from the same assignment state, so the
  winner is identical by construction.
- Exactness guard: if the level scan ever evaluates more than
  PICK_BUDGET candidates (pathological tie mass, e.g. the all-zero
  level before the first conflict), it falls back to a verbatim
  copy of Stage 2's pick_branch. The fallback is always exact, so
  per-pick cost is bounded and decisions are identical in all cases.
- The unreachable-by-invariant defensive case (a non-satisfied
  clause with no unassigned literal -> False) is preserved: when
  the level scan finds no candidate at all, the fallback scan runs
  and returns None (SAT) or False exactly as Stage 2 would.

Float-identity discipline (required for identical decisions):
- bump_conflict performs the SAME float additions, in the SAME
  clause-literal order, as Stage 2; only level bookkeeping is added.
- Rescale performs the SAME divisions in the SAME order as Stage 2,
  then rebuilds the level structures from the rescaled activities
  (ordering preserved by rescale, so the rebuild is exact).
- Level membership is keyed by the exact float activity values; no
  rounding, no epsilon comparisons anywhere in the decision path.

Node counts MUST be identical to Stage 2 on every instance: any
node-count difference means a decision differed, which fails the
Stage 2b gate. CPU-only, no router, no browser, no GPU.

CLI: sat-solver-v4-heap.py solve-one <n> <ratio> <rep> -> one JSON line.
Exit 0 on SAT/UNSAT/TIMEOUT; nonzero only on crash.
"""
import bisect
import json
import random
import signal
import sys
import time

TIMEOUT_S = 30
VAR_DECAY = 0.95
RESCALE_AT = 1e100
PICK_BUDGET = 64


class SolveTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise SolveTimeout()


signal.signal(signal.SIGALRM, _alarm_handler)


def gen_instance(n, ratio, rep):
    # IDENTICAL to v2/v3/v4 (v3 seed scheme).
    rng = random.Random(1000003 * n + 7919 * int(round(ratio * 10)) + rep)
    m = int(round(ratio * n))
    clauses = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), 3)
        clauses.append(tuple(v if rng.random() < 0.5 else -v for v in vs))
    return clauses


class WatchedSolver:
    def __init__(self, clauses, n):
        self.clauses = clauses
        self.n = n
        self.assign = [0] * (n + 1)  # 0 unassigned, 1 True, -1 False
        self.watchlists = [[] for _ in range(2 * n + 1)]
        self.w1 = [0] * len(clauses)
        self.w2 = [0] * len(clauses)
        for ci, c in enumerate(clauses):
            a, b = c[0], c[1]
            self.w1[ci] = a
            self.w2[ci] = b
            self.watchlists[a + n].append(ci)
            self.watchlists[b + n].append(ci)
        self.trail = []
        self.prop_q = []
        self.qhead = 0
        self.nodes = 0
        # VSIDS state (identical floats to Stage 2).
        self.activity = [0.0] * (n + 1)
        self.var_inc = 1.0
        self.conflict_clause = None
        # Occurrence lists: occ[v] = sorted [(clause_idx, first_pos)].
        # Static; built once. Used for candidate checks + scan keys.
        occ = [dict() for _ in range(n + 1)]
        for ci, c in enumerate(clauses):
            for pos, l in enumerate(c):
                v = abs(l)
                if ci not in occ[v]:
                    occ[v][ci] = pos
        self.occ = [sorted(d.items()) for d in occ]
        # Activity levels: activity value -> set of variables at it;
        # sorted_acts = sorted distinct activity values (ascending).
        self.levels = {0.0: set(range(1, n + 1))}
        self.sorted_acts = [0.0]

    def lit_val(self, lit):
        v = self.assign[abs(lit)]
        if v == 0:
            return 0
        return v if lit > 0 else -v

    def assign_lit(self, lit):
        var = abs(lit)
        self.assign[var] = 1 if lit > 0 else -1
        self.trail.append(var)
        self.prop_q.append(-lit)

    def _level_move(self, v, old, new):
        # Move v from activity level old to level new. old != new here
        # (bumps add a positive inc); the guard keeps rescale/rebuild
        # paths safe if ever called with equal values.
        if old == new:
            return
        s = self.levels[old]
        s.discard(v)
        if not s:
            del self.levels[old]
            i = bisect.bisect_left(self.sorted_acts, old)
            if i < len(self.sorted_acts) and self.sorted_acts[i] == old:
                del self.sorted_acts[i]
        s2 = self.levels.get(new)
        if s2 is None:
            self.levels[new] = {v}
            bisect.insort(self.sorted_acts, new)
        else:
            s2.add(v)

    def bump_conflict(self):
        # SAME float operations, SAME order as Stage 2; level moves
        # added. No-op if no conflict clause was recorded.
        ci = self.conflict_clause
        if ci is None:
            return
        inc = self.var_inc
        act = self.activity
        for l in self.clauses[ci]:
            v = abs(l)
            old = act[v]
            new = old + inc
            self._level_move(v, old, new)
            act[v] = new
        self.var_inc = inc / VAR_DECAY
        if self.var_inc > RESCALE_AT:
            for v in range(1, self.n + 1):
                act[v] *= 1e-100
            self.var_inc *= 1e-100
            # Rebuild levels from the rescaled activities (exact:
            # same divisions, same order as Stage 2).
            levels = {}
            for v in range(1, self.n + 1):
                a = act[v]
                s = levels.get(a)
                if s is None:
                    levels[a] = {v}
                else:
                    s.add(v)
            self.levels = levels
            self.sorted_acts = sorted(levels)

    def propagate(self):
        # VERBATIM Stage 2 propagate(). Returns True if no conflict,
        # False on conflict; records the conflicting clause index.
        self.conflict_clause = None
        assign = self.assign
        clauses = self.clauses
        w1 = self.w1
        w2 = self.w2
        watchlists = self.watchlists
        n = self.n
        q = self.prop_q
        while self.qhead < len(q):
            f = q[self.qhead]
            self.qhead += 1
            wl = watchlists[f + n]
            staying = []
            i = 0
            conflict = False
            while i < len(wl):
                ci = wl[i]
                a = w1[ci]
                b = w2[ci]
                other = b if a == f else a
                ov_raw = assign[abs(other)]
                if ov_raw == 0:
                    ov = 0
                else:
                    ov = ov_raw if other > 0 else -ov_raw
                if ov == 1:
                    staying.append(ci)
                    i += 1
                    continue
                # Search for a non-false literal distinct from the watches.
                new_watch = None
                for l in clauses[ci]:
                    if l == a or l == b:
                        continue
                    lv_raw = assign[abs(l)]
                    if lv_raw == 0:
                        new_watch = l
                        break
                    if (lv_raw if l > 0 else -lv_raw) != -1:
                        new_watch = l
                        break
                if new_watch is not None:
                    if a == f:
                        w1[ci] = new_watch
                    else:
                        w2[ci] = new_watch
                    watchlists[new_watch + n].append(ci)
                    i += 1
                    continue
                if ov == 0:
                    # Unit: assign other True.
                    var = abs(other)
                    assign[var] = 1 if other > 0 else -1
                    self.trail.append(var)
                    q.append(-other)
                    staying.append(ci)
                    i += 1
                    continue
                # Conflict: other is false, no replacement.
                conflict = True
                break
            if conflict:
                # Commit partial progress: staying + unprocessed remainder
                # (including the conflicting clause itself, which keeps
                # watching f). Moved clauses are already in their new lists.
                watchlists[f + n] = staying + wl[i:]
                self.conflict_clause = ci
                return False
            watchlists[f + n] = staying
        return True

    def propagate_checked(self):
        # propagate() + exactly one VSIDS bump per conflict.
        ok = self.propagate()
        if not ok:
            self.bump_conflict()
        return ok

    def _scan_key(self, v):
        # (clause_idx, pos) of v's first occurrence in a currently
        # non-satisfied clause, or None if v occurs in no non-satisfied
        # clause (not a candidate). Clause order dominates position,
        # matching the full scan's traversal order.
        assign = self.assign
        clauses = self.clauses
        for ci, pos in self.occ[v]:
            c = clauses[ci]
            satisfied = False
            for l in c:
                av = assign[abs(l)]
                if av != 0 and ((av == 1 and l > 0) or (av == -1 and l < 0)):
                    satisfied = True
                    break
            if not satisfied:
                return (ci, pos)
        return None

    def _pick_branch_scan(self):
        # VERBATIM Stage 2 pick_branch. Always exact; used as the
        # fallback when the level scan exceeds its budget, and when
        # no candidate exists (returns None or False exactly).
        assign = self.assign
        act = self.activity
        best_var = None
        best_act = -1.0
        for c in self.clauses:
            satisfied = False
            for l in c:
                v = assign[abs(l)]
                if v == 0:
                    continue
                if (v == 1 and l > 0) or (v == -1 and l < 0):
                    satisfied = True
                    break
            if satisfied:
                continue
            unassigned = False
            for l in c:
                if assign[abs(l)] == 0:
                    unassigned = True
                    av = abs(l)
                    a = act[av]
                    if a > best_act:
                        best_act = a
                        best_var = av
            if not unassigned:
                return False
        return best_var

    def pick_branch(self):
        # Level-ordered pick: identical decisions to _pick_branch_scan
        # (same candidate set, same max activity, same tie-break), at
        # O(levels + ties) instead of O(clauses) per decision.
        assign = self.assign
        checks = 0
        for act_val in reversed(self.sorted_acts):
            best = None
            best_key = None
            for v in self.levels[act_val]:
                if assign[v] != 0:
                    continue
                key = self._scan_key(v)
                checks += 1
                if key is None:
                    continue
                if best_key is None or key < best_key:
                    best_key = key
                    best = v
                if checks > PICK_BUDGET:
                    return self._pick_branch_scan()
            if best is not None:
                return best
        return self._pick_branch_scan()

    def solve(self):
        # VERBATIM Stage 2 solve().
        self.nodes = 1
        # Seed initial unit clauses (generic safety; no-op for 3-SAT, whose
        # clauses all have 3 literals).
        for c in self.clauses:
            if len(c) == 1:
                self.assign_lit(c[0])
        if not self.propagate_checked():
            return "UNSAT"
        frames = []  # [var, flipped]; flipped True means False already tried
        marks = []   # trail length before the frame's decision literal
        while True:
            var = self.pick_branch()
            if var is None:
                return "SAT"
            if var is False:
                # Defensive: propagation missed a conflict. Treat as a
                # conflict at the current level and backtrack; validation
                # will catch any verdict divergence this causes.
                ok = False
            else:
                marks.append(len(self.trail))
                frames.append([var, False])
                self.nodes += 1
                self.assign_lit(var)  # True first
                ok = self.propagate_checked()
            while not ok:
                flipped = False
                while frames:
                    v, fl = frames.pop()
                    m = marks.pop()
                    while len(self.trail) > m:
                        self.assign[self.trail.pop()] = 0
                    self.prop_q.clear()
                    self.qhead = 0
                    if not fl:
                        marks.append(m)
                        frames.append([v, True])
                        self.nodes += 1
                        self.assign_lit(-v)
                        ok = self.propagate_checked()
                        flipped = True
                        break
                if not flipped:
                    return "UNSAT"


def solve_timed(clauses, n):
    solver = WatchedSolver(clauses, n)
    signal.alarm(TIMEOUT_S)
    t0 = time.perf_counter()
    try:
        result = solver.solve()
    except SolveTimeout:
        return ("TIMEOUT", None, None)
    finally:
        signal.alarm(0)
    return (result, time.perf_counter() - t0, solver.nodes)


def main(argv):
    if len(argv) != 5 or argv[1] != "solve-one":
        print("usage: sat-solver-v4-heap.py solve-one <n> <ratio> <rep>",
              file=sys.stderr)
        return 2
    n, ratio, rep = int(argv[2]), float(argv[3]), int(argv[4])
    clauses = gen_instance(n, ratio, rep)
    status, dt, nodes = solve_timed(clauses, n)
    print(json.dumps({"n": n, "ratio": ratio, "rep": rep,
                      "status": status, "time_s": dt, "nodes": nodes}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
