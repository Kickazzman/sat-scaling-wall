#!/usr/bin/env python3
"""Stage 2 solver: Stage 1 (watched literals + trail) + VSIDS branching (v4).

ONE change only, on top of Stage 1 (sat-solver-v3.py): the branching
variable selection. Everything else — gen_instance (v3 seed scheme),
watched-literal propagation, trail/backtrack structure, True-first
polarity, node counting (1 root + 1 per branch assignment), 30s cap,
CLI — is identical to Stage 1.

VSIDS (variable-state independent decaying sum), MiniSAT-style:
- activity[v] starts at 0.0 for every variable.
- On each conflict, the variables of the conflicting clause are bumped
  by var_inc, and var_inc is then multiplied by 1/VAR_DECAY. This is
  exactly equivalent to decaying all activities by VAR_DECAY per
  conflict and bumping by 1.0, but O(clause length) per conflict
  instead of O(n); the activity ORDERING is identical.
- VAR_DECAY = 0.95 (classic value), BUMP base 1.0.
- Rescale (activities and var_inc divided by 1e100) if var_inc exceeds
  1e100, so floats never overflow; ordering is preserved.
- Branching picks the unassigned variable with highest activity among
  variables occurring in non-satisfied clauses (same candidate set as
  Stage 1's clause-order scan); ties resolve to the earliest-seen in
  clause order (strict-greater replacement). Before the first conflict
  all activities are 0, so early decisions match Stage 1's order.
- The conflicting clause is the clause propagate() reports as
  conflicting (all literals false, no replacement watch). Bumping uses
  exactly that clause's variables, once per conflict.

Node counts are EXPECTED to differ from Stage 1 (search order changes);
verdicts must not. No clause learning, no restarts — those are later
stages. CPU-only, no router, no browser, no GPU.

CLI: sat-solver-v4.py solve-one <n> <ratio> <rep> -> one JSON line on stdout.
Exit 0 on SAT/UNSAT/TIMEOUT; nonzero only on crash.
"""
import json
import random
import signal
import sys
import time

TIMEOUT_S = 30
VAR_DECAY = 0.95
RESCALE_AT = 1e100


class SolveTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise SolveTimeout()


signal.signal(signal.SIGALRM, _alarm_handler)


def gen_instance(n, ratio, rep):
    # IDENTICAL to v2/v3 (v3 seed scheme).
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
        # VSIDS state (the ONLY Stage 2 addition to solver state).
        self.activity = [0.0] * (n + 1)
        self.var_inc = 1.0
        self.conflict_clause = None

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

    def bump_conflict(self):
        # Bump the conflicting clause's variables; grow var_inc (decay
        # equivalent). No-op if no conflict clause was recorded.
        ci = self.conflict_clause
        if ci is None:
            return
        inc = self.var_inc
        act = self.activity
        for l in self.clauses[ci]:
            act[abs(l)] += inc
        self.var_inc = inc / VAR_DECAY
        if self.var_inc > RESCALE_AT:
            for v in range(1, self.n + 1):
                act[v] *= 1e-100
            self.var_inc *= 1e-100

    def propagate(self):
        # Returns True if no conflict, False on conflict. On conflict,
        # records the conflicting clause index for VSIDS bumping.
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

    def pick_branch(self):
        # Highest-activity unassigned variable among variables in
        # non-satisfied clauses; ties -> earliest in clause order.
        # Returns var, None (SAT: nothing left), or False (conflict
        # state: non-satisfied clause with no unassigned literal;
        # should not happen if propagation is complete).
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

    def solve(self):
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
        print("usage: sat-solver-v4.py solve-one <n> <ratio> <rep>",
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
