#!/usr/bin/env python3
"""Stage 0 solver: clean reimplementation of plain DPLL (v3 semantics).

Same algorithm as sat-scaling-v3.py, no search change: unit propagation
(scan order, restart scan after each assignment), first-unassigned-variable
branching in clause order, True branch first, 30s cap via SIGALRM.
CLI: sat-solver-v2.py solve-one <n> <ratio> <rep> -> one JSON line on stdout.
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
    rng = random.Random(1000003 * n + 7919 * int(round(ratio * 10)) + rep)
    m = int(round(ratio * n))
    clauses = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), 3)
        clauses.append(tuple(v if rng.random() < 0.5 else -v for v in vs))
    return clauses


def simplify(clauses, var, value):
    sat_lit = var if value else -var
    false_lit = -var if value else var
    out = []
    for c in clauses:
        if sat_lit in c:
            continue
        nc = tuple(l for l in c if l != false_lit)
        if not nc:
            return None
        out.append(nc)
    return out


def unit_propagate(clauses, assignment):
    changed = True
    while changed:
        changed = False
        for c in clauses:
            unassigned = [l for l in c if abs(l) not in assignment]
            if not unassigned:
                return None, None
            if len(unassigned) == 1:
                l = unassigned[0]
                assignment[abs(l)] = (l > 0)
                clauses = simplify(clauses, abs(l), l > 0)
                if clauses is None:
                    return None, None
                changed = True
                break
    return clauses, assignment


def dpll(clauses, assignment, nodes):
    nodes[0] += 1
    clauses, assignment = unit_propagate(clauses, dict(assignment))
    if clauses is None:
        return None
    if not clauses:
        return assignment
    var = None
    for c in clauses:
        for l in c:
            if abs(l) not in assignment:
                var = abs(l)
                break
        if var:
            break
    for val in (True, False):
        nc = simplify(clauses, var, val)
        if nc is None:
            continue
        r = dpll(nc, {**assignment, var: val}, nodes)
        if r is not None:
            return r
    return None


def solve_timed(clauses):
    nodes = [0]
    signal.alarm(TIMEOUT_S)
    t0 = time.perf_counter()
    try:
        result = dpll(clauses, {}, nodes)
    except SolveTimeout:
        return ("TIMEOUT", None, None)
    finally:
        signal.alarm(0)
    return ("SAT" if result is not None else "UNSAT",
            time.perf_counter() - t0, nodes[0])


def main(argv):
    if len(argv) != 5 or argv[1] != "solve-one":
        print("usage: sat-solver-v2.py solve-one <n> <ratio> <rep>",
              file=sys.stderr)
        return 2
    n, ratio, rep = int(argv[2]), float(argv[3]), int(argv[4])
    clauses = gen_instance(n, ratio, rep)
    status, dt, nodes = solve_timed(clauses)
    print(json.dumps({"n": n, "ratio": ratio, "rep": rep,
                      "status": status, "time_s": dt, "nodes": nodes}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
