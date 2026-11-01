#!/usr/bin/env python3
"""Stage 3 solver: CDCL (clause learning + non-chronological backjumping).

ONE TECHNIQUE ONLY on the Stage 2b heap solver (sat-solver-v4-heap.py):
conflict-driven clause learning with 1-UIP analysis + backjumping. No
restarts, no learnt-clause deletion (Stage 4), no other search change.
Everything else — gen_instance (v3 seed scheme), watched-literal
propagation core, heap-ordered VSIDS pick, True-first polarity, 30s cap,
CLI — is identical to Stage 2b.

Scheme (stated before running):
- Decision levels: every assignment carries a decision level and a
  reason clause (None for decisions). The trail is cut at level
  boundaries (trail_lim); backjump truncates the trail to the
  asserting level.
- Conflict analysis: 1-UIP, MiniSAT-style trail walk. Start from the
  conflicting clause; repeatedly resolve the latest-assigned seen
  variable at the current level with its reason clause until one
  current-level literal remains (the UIP). Level-0 literals are
  excluded from the learnt clause (sound: their negations are
  implied by the formula alone). Learnt clause = UIP literal first,
  then the other literals in encounter order.
- Learnt clauses are appended to the clause database with watched
  literals on the UIP literal and the highest-level other literal;
  occurrence lists are extended so the heap pick's scan keys cover
  learnt clauses. The learnt database is UNBOUNDED in this stage
  (no deletion until Stage 4) — stated limitation.
- Backjump level = max decision level among the learnt clause's
  non-UIP literals (0 if the learnt clause is unit). After
  backjumping, the UIP literal is assigned at that level with the
  learnt clause as its reason, and propagation resumes. Multiple
  conflicts per decision level are handled by the inner loop.
- VSIDS: bump set changes from the conflicting clause's variables
  (Stage 2) to ALL variables seen during conflict analysis (MiniSAT
  rule: every variable encountered while resolving). Bump arithmetic
  (add var_inc, decay once per conflict, rescale rule) is identical;
  level bookkeeping identical.
- Propagation: the watched-literal core is verbatim Stage 2 except
  unit assignments now record level + reason (required for
  analysis). The per-conflict auto-bump (propagate_checked) is gone:
  conflicts are handled by the solve loop (analyze -> learn ->
  backjump), and bump happens once per analysis.

Node counting (stated): nodes = 1 (root) + 1 per DECISION assignment,
same definition as Stages 0-2b. Learnt-clause operations, backjumps,
and implied (propagated) assignments do NOT count as nodes, and the
chronological "flip" assignments of Stage 2 no longer exist. Node
counts are therefore NOT expected identical to Stage 2b — the search
tree changes by design. The correctness gate is VERDICT agreement
only (390/390, zero flips); node ratios are reported as a
distribution, never as an identity check.

CPU-only, no router, no browser, no GPU.

CLI: sat-solver-v5.py solve-one <n> <ratio> <rep> -> one JSON line.
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
    # IDENTICAL to v2/v3/v4/v4-heap (v3 seed scheme).
    rng = random.Random(1000003 * n + 7919 * int(round(ratio * 10)) + rep)
    m = int(round(ratio * n))
    clauses = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), 3)
        clauses.append(tuple(v if rng.random() < 0.5 else -v for v in vs))
    return clauses


class WatchedSolver:
    def __init__(self, clauses, n):
        self.clauses = list(clauses)
        self.n = n
        self.assign = [0] * (n + 1)  # 0 unassigned, 1 True, -1 False
        self.watchlists = [[] for _ in range(2 * n + 1)]
        self.w1 = [0] * len(clauses)
        self.w2 = [0] * len(clauses)
        for ci, c in enumerate(clauses):
            a = c[0]
            b = c[1] if len(c) > 1 else c[0]
            self.w1[ci] = a
            self.w2[ci] = b
            self.watchlists[a + n].append(ci)
            if len(c) > 1:
                self.watchlists[b + n].append(ci)
        self.trail = []
        self.prop_q = []
        self.qhead = 0
        self.nodes = 0
        # CDCL state: decision level, per-variable level + reason.
        self.dlevel = 0
        self.trail_lim = []  # trail_lim[k] = trail length at start of level k+1
        self.dlevel_of = [0] * (n + 1)
        self.reason = [None] * (n + 1)  # clause index, or None for decisions
        # VSIDS state (identical floats/mechanics to Stage 2).
        self.activity = [0.0] * (n + 1)
        self.var_inc = 1.0
        self.conflict_clause = None
        # Occurrence lists: occ[v] = sorted [(clause_idx, first_pos)].
        # Extended as learnt clauses are added (append preserves order:
        # learnt indices increase monotonically).
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
        self.learnt_count = 0

    def lit_val(self, lit):
        v = self.assign[abs(lit)]
        if v == 0:
            return 0
        return v if lit > 0 else -v

    def assign_lit(self, lit, reason=None):
        var = abs(lit)
        self.assign[var] = 1 if lit > 0 else -1
        self.dlevel_of[var] = self.dlevel
        self.reason[var] = reason
        self.trail.append(var)
        self.prop_q.append(-lit)

    def _level_move(self, v, old, new):
        # Move v from activity level old to level new (Stage 2b verbatim).
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

    def bump_vars(self, var_list):
        # SAME float operations as Stage 2's bump_conflict (add var_inc
        # per variable in the given order, decay once, same rescale
        # rule), applied to the analysis-seen variables instead of the
        # conflicting clause's variables. Level moves added (Stage 2b).
        inc = self.var_inc
        act = self.activity
        for v in var_list:
            old = act[v]
            new = old + inc
            self._level_move(v, old, new)
            act[v] = new
        self.var_inc = inc / VAR_DECAY
        if self.var_inc > RESCALE_AT:
            for v in range(1, self.n + 1):
                act[v] *= 1e-100
            self.var_inc *= 1e-100
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
        # Stage 2 propagate() core VERBATIM, except unit assignments
        # record decision level + reason clause (CDCL requirement).
        # Returns True if no conflict, False on conflict; records the
        # conflicting clause index. Does NOT bump (solve loop owns it).
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
                    # Unit: assign other True, with level + reason.
                    var = abs(other)
                    assign[var] = 1 if other > 0 else -1
                    self.dlevel_of[var] = self.dlevel
                    self.reason[var] = ci
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

    def analyze(self, confl_ci):
        """1-UIP conflict analysis (MiniSAT-style trail walk).

        Returns (learnt_clause_tuple, backjump_level, seen_vars_order).
        learnt[0] is the UIP literal; the rest are in encounter order.
        seen_vars_order is every variable encountered (for VSIDS bump).
        Raises AssertionError if the resolution chain hits a decision
        variable while other current-level variables remain unresolved
        (cannot happen if reasons are correct — fail loudly, never
        learn an unsound clause silently).
        """
        n = self.n
        dlevel = self.dlevel
        dlevel_of = self.dlevel_of
        reason = self.reason
        trail = self.trail
        learnt = []
        seen = bytearray(n + 1)
        order = []
        counter = 0
        p = None  # variable whose reason clause is being processed
        idx = len(trail) - 1
        confl = confl_ci
        while True:
            clause = self.clauses[confl]
            for l in clause:
                v = abs(l)
                if p is not None and v == p:
                    continue  # asserting literal (true) of the reason clause
                if dlevel_of[v] == 0 or seen[v]:
                    continue
                seen[v] = 1
                order.append(v)
                if dlevel_of[v] == dlevel:
                    counter += 1
                else:
                    learnt.append(l)
            # Select the latest-assigned seen variable on the trail.
            while idx < 0 or not seen[trail[idx]]:
                idx -= 1
                assert idx >= 0, "CDCL analysis: no seen variable on trail"
            p = trail[idx]
            idx -= 1
            seen[p] = 0
            counter -= 1
            if counter == 0:
                break
            confl = reason[p]
            assert confl is not None, (
                "CDCL analysis hit decision var %d with %d current-level "
                "literals unresolved" % (p, counter))
        # UIP literal: the literal for p that is FALSE under the assignment.
        uip_lit = -p if self.assign[p] == 1 else p
        learnt.insert(0, uip_lit)
        bt = 0
        for l in learnt[1:]:
            lv = dlevel_of[abs(l)]
            if lv > bt:
                bt = lv
        return tuple(learnt), bt, order

    def add_learnt(self, learnt):
        """Append a learnt clause; return its clause index.

        Watches: learnt[0] (UIP) and the highest-level other literal.
        Occurrence lists extended so the heap pick sees learnt clauses.
        """
        ci = len(self.clauses)
        learnt = list(learnt)
        if len(learnt) > 1:
            # Move the highest-level non-UIP literal to position 1.
            best_i = 1
            best_lv = self.dlevel_of[abs(learnt[1])]
            for i in range(2, len(learnt)):
                lv = self.dlevel_of[abs(learnt[i])]
                if lv > best_lv:
                    best_lv = lv
                    best_i = i
            if best_i != 1:
                learnt[1], learnt[best_i] = learnt[best_i], learnt[1]
        learnt = tuple(learnt)
        self.clauses.append(learnt)
        if len(learnt) == 1:
            self.w1.append(learnt[0])
            self.w2.append(learnt[0])
            self.watchlists[learnt[0] + self.n].append(ci)
        else:
            self.w1.append(learnt[0])
            self.w2.append(learnt[1])
            self.watchlists[learnt[0] + self.n].append(ci)
            self.watchlists[learnt[1] + self.n].append(ci)
        for pos, l in enumerate(learnt):
            self.occ[abs(l)].append((ci, pos))
        self.learnt_count += 1
        return ci

    def backjump(self, level):
        """Truncate the trail to decision level `level`."""
        if level < self.dlevel:
            target = (self.trail_lim[level] if level < len(self.trail_lim)
                      else len(self.trail))
            while len(self.trail) > target:
                v = self.trail.pop()
                self.assign[v] = 0
                self.dlevel_of[v] = 0
                self.reason[v] = None
            del self.trail_lim[level:]
            self.dlevel = level
            self.prop_q.clear()
            self.qhead = 0

    def find_falsified(self):
        """First clause whose literals are all false, or None.

        Only used on the defensive pick_branch()==False path (a
        non-satisfied clause with no unassigned literal exists, so
        some clause is falsified; propagation should normally have
        caught it as a conflict first).
        """
        assign = self.assign
        for ci, c in enumerate(self.clauses):
            falsified = True
            for l in c:
                av = assign[abs(l)]
                if av == 0 or (av == 1 and l > 0) or (av == -1 and l < 0):
                    falsified = False
                    break
            if falsified:
                return ci
        return None

    def _scan_key(self, v):
        # Stage 2b _scan_key VERBATIM (occ lists now also cover learnt
        # clauses, appended in index order, so keys stay consistent
        # with the full clause scan).
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
        # VERBATIM Stage 2 pick_branch (scans self.clauses, which now
        # includes learnt clauses, in index order).
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
        # Stage 2b level-ordered pick VERBATIM.
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

    def drain_conflicts(self):
        """Propagate until clean, learning + backjumping per conflict.

        Returns False iff a conflict occurs at decision level 0
        (UNSAT); True iff propagation is clean.
        """
        while not self.propagate():
            if self.dlevel == 0:
                return False
            learnt, bt, seen = self.analyze(self.conflict_clause)
            self.bump_vars(seen)
            lci = self.add_learnt(learnt)
            self.backjump(bt)
            self.assign_lit(learnt[0], reason=lci)
        return True

    def solve(self):
        self.nodes = 1
        # Seed initial unit clauses (generic safety; no-op for 3-SAT).
        for ci, c in enumerate(self.clauses):
            if len(c) == 1:
                self.assign_lit(c[0], reason=ci)
        if not self.drain_conflicts():
            return "UNSAT"
        while True:
            var = self.pick_branch()
            if var is None:
                return "SAT"
            if var is False:
                # Defensive: propagation missed a conflict. Analyze
                # the falsified clause as a conflict.
                ci = self.find_falsified()
                if ci is None or self.dlevel == 0:
                    return "UNSAT"
                learnt, bt, seen = self.analyze(ci)
                self.bump_vars(seen)
                lci = self.add_learnt(learnt)
                self.backjump(bt)
                self.assign_lit(learnt[0], reason=lci)
                if not self.drain_conflicts():
                    return "UNSAT"
                continue
            # Decision: new level, True first.
            self.dlevel += 1
            self.trail_lim.append(len(self.trail))
            self.nodes += 1
            self.assign_lit(var, reason=None)
            if not self.drain_conflicts():
                return "UNSAT"


def solve_timed(clauses, n):
    solver = WatchedSolver(clauses, n)
    signal.alarm(TIMEOUT_S)
    t0 = time.perf_counter()
    try:
        result = solver.solve()
    except SolveTimeout:
        return ("TIMEOUT", None, None, None)
    finally:
        signal.alarm(0)
    return (result, time.perf_counter() - t0, solver.nodes,
            solver.learnt_count)


def main(argv):
    if len(argv) != 5 or argv[1] != "solve-one":
        print("usage: sat-solver-v5.py solve-one <n> <ratio> <rep>",
              file=sys.stderr)
        return 2
    n, ratio, rep = int(argv[2]), float(argv[3]), int(argv[4])
    clauses = gen_instance(n, ratio, rep)
    status, dt, nodes, learnt = solve_timed(clauses, n)
    print(json.dumps({"n": n, "ratio": ratio, "rep": rep,
                      "status": status, "time_s": dt, "nodes": nodes,
                      "learnt": learnt}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
