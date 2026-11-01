#!/usr/bin/env python3
"""Stage 1 solver: plain DPLL + watched literals + trail (v3).

Same search tree as Stage 0 (sat-solver-v2.py): same gen_instance, same
branching (first unassigned variable in clause order, True first), same
unit-propagation closure. Only propagation efficiency changes: watched
literals + assignment trail replace per-assignment clause-list rebuilds
(simplify) and full rescans (unit_propagate).

Node counts must be IDENTICAL to Stage 0 on solved instances. Nodes count
1 for the root state + 1 per branch assignment, which equals v2's dpll()
call count (1 root call + 1 call per branch attempt).

Watched-literal notes:
- Clauses are never modified; watches are two literals per clause.
- Watches are NOT restored on backtrack: a moved watch points at a
  literal that was non-false at move time, and backtracking only makes
  more literals non-false, so the invariant survives unwinding.
- Branching scans clauses in original order, skipping satisfied clauses,
  taking the first unassigned literal. This equals v2's branching on the
  simplified list: satisfied clauses are dropped there, falsified literals
  stripped, so the first literal of the first simplified clause is the
  first non-false literal of the first non-satisfied original clause.

CLI: sat-solver-v3.py solve-one <n> <ratio> <rep> -> one JSON line on stdout.
Exit 0 on SAT/UNSAT/TIMEOUT; nonzero only on crash.
"""
import json
import random
import signal
import sys
import time

TIMEOUT_S = 30


class SolveTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise SolveTimeout()


signal.signal(signal.SIGALRM, _alarm_handler)


def gen_instance(n, ratio, rep):
    # IDENTICAL to v2 (v3 seed scheme).
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

    def propagate(self):
        # Returns True if no conflict, False on conflict.
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
                return False
            watchlists[f + n] = staying
        return True

    def pick_branch(self):
        # First unassigned variable in clause order, skipping satisfied
        # clauses. Returns var, None (SAT: nothing left), or False
        # (conflict state: non-satisfied clause with no unassigned literal;
        # should not happen if propagation is complete).
        assign = self.assign
        for c in self.clauses:
            satisfied = False
            first_unassigned = None
            for l in c:
                v = assign[abs(l)]
                if v == 0:
                    if first_unassigned is None:
                        first_unassigned = abs(l)
                elif (v == 1 and l > 0) or (v == -1 and l < 0):
                    satisfied = True
                    break
            if satisfied:
                continue
            if first_unassigned is None:
                return False
            return first_unassigned
        return None

    def solve(self):
        self.nodes = 1
        # Seed initial unit clauses (generic safety; no-op for 3-SAT, whose
        # clauses all have 3 literals).
        for c in self.clauses:
            if len(c) == 1:
                self.assign_lit(c[0])
        if not self.propagate():
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
                # will catch any node divergence this causes.
                ok = False
            else:
                marks.append(len(self.trail))
                frames.append([var, False])
                self.nodes += 1
                self.assign_lit(var)  # True first
                ok = self.propagate()
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
                        ok = self.propagate()
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
        print("usage: sat-solver-v3.py solve-one <n> <ratio> <rep>",
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
