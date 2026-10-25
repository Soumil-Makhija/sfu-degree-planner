"""Z3 section selection over complete bundles, with dated weekly conflicts."""
from datetime import date, timedelta
from itertools import combinations

from z3 import Bool, BoolVal, Not, Or, PbEq, Solver, sat, unsat

from .prerequisites import eligibility, transcript_records


def overlap_dates(a, b):
    start = max(date.fromisoformat(a['start_date']), date.fromisoformat(b['start_date']))
    end = min(date.fromisoformat(a['end_date']), date.fromisoformat(b['end_date']))
    return any(start + timedelta(days=(day - start.weekday()) % 7) <= end
               for day in set(a['days']) & set(b['days']))


def meetings_conflict(a, b, travel_minutes=0):
    if not overlap_dates(a, b):
        return False
    gap = travel_minutes if a.get('campus') and b.get('campus') and a['campus'] != b['campus'] else 0
    return a['start'] < b['end'] + gap and b['start'] < a['end'] + gap


def bundles_conflict(a, b, travel_minutes=0):
    return any(meetings_conflict(x, y, travel_minutes) for x in a['meetings'] for y in b['meetings'])


def solve(catalog, courses, transcript, *, busy=(), max_units=18, travel_minutes=60,
          limit=5, confirmations=(), timeout_ms=5000):
    """Require exactly one section for every requested course; enumerate stable schedules."""
    transcript = transcript_records(transcript)
    if not isinstance(courses, list) or not courses or len(courses) > 12 or any(not isinstance(c, str) for c in courses) or len(set(courses)) != len(courses):
        raise ValueError('request 1–12 distinct courses')
    if type(max_units) not in (int, float) or not 0 < max_units <= 40:
        raise ValueError('max_units must be in (0, 40]')
    if type(travel_minutes) is not int or not 0 <= travel_minutes <= 240:
        raise ValueError('travel_minutes must be an integer in [0, 240]')
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('limit must be in [1, 50]')
    if not isinstance(confirmations, (list, tuple)) or any(not isinstance(x, str) for x in confirmations):
        raise ValueError('confirmations must be a list of exact manual-condition strings')
    if not isinstance(busy, (list, tuple)) or len(busy) > 100:
        raise ValueError('busy must contain at most 100 meetings')
    from .catalog import validate_meeting
    for meeting in busy:
        validate_meeting(meeting)
    by_id = {c['id']: c for c in catalog['courses']}
    unknown = sorted(set(courses) - by_id.keys())
    if unknown:
        raise ValueError('courses absent from snapshot: ' + ', '.join(unknown))
    selected = [by_id[c] for c in sorted(courses)]
    checks = [eligibility(c, transcript, confirmations) for c in selected]
    solver = Solver()
    solver.set(timeout=timeout_ms, random_seed=0)
    reasons, variables, options = {}, [], []
    def track(expr, detail):
        label = f'constraint_{len(reasons)}'
        reasons[label] = detail
        solver.assert_and_track(BoolVal(expr) if isinstance(expr, bool) else expr, label)
    for course, check in zip(selected, checks):
        choices = []
        for section in sorted(course['sections'], key=lambda s: s['id']):
            var = Bool(f'choice_{len(variables)}')
            variables.append(var)
            options.append((course, section))
            choices.append(var)
            if not check['eligible']:
                track(Not(var), {'kind': 'eligibility', 'course': course['id'], 'evidence': check})
            meetings = section['meetings']
            if any(meetings_conflict(a, b, travel_minutes) for a, b in combinations(meetings, 2)):
                track(Not(var), {'kind': 'internal_conflict', 'course': course['id'], 'section': section['id']})
            if any(meetings_conflict(a, b, travel_minutes) for a in meetings for b in busy):
                track(Not(var), {'kind': 'busy', 'course': course['id'], 'section': section['id']})
        track(PbEq([(v, 1) for v in choices], 1) if choices else False,
              {'kind': 'required_course', 'course': course['id']})
    track(sum(c['units'] for c in selected) <= max_units, {'kind': 'unit_limit', 'maximum': max_units})
    for i, j in combinations(range(len(variables)), 2):
        ca, a = options[i]
        cb, b = options[j]
        if ca['id'] != cb['id'] and bundles_conflict(a, b, travel_minutes):
            track(Or(Not(variables[i]), Not(variables[j])), {'kind': 'meeting_conflict',
                  'courses': [ca['id'], cb['id']], 'sections': [a['id'], b['id']]})
    schedules = []
    # Stable lexicographic enumeration: SAT decisions never determine output order.
    while len(schedules) < limit:
        status = solver.check()
        if status != sat:
            if not schedules:
                return {'status': 'unsatisfiable' if status == unsat else 'unknown', 'schedules': [],
                        'explanations': [reasons[str(x)] for x in sorted(solver.unsat_core(), key=lambda x: int(str(x).split('_')[-1]))] if status == unsat else [],
                        'reason': None if status == unsat else solver.reason_unknown(),
                        'eligibility': checks, 'term': catalog['term'], 'confirmations': list(confirmations)}
            return _result(catalog, schedules, checks, confirmations, status == unsat, solver.reason_unknown() if status != unsat else None)
        solver.push()
        chosen = []
        for course in selected:
            for i, (candidate, _) in enumerate(options):
                if candidate['id'] != course['id']:
                    continue
                solver.push()
                solver.add(variables[i])
                status = solver.check()
                solver.pop()
                if status == sat:
                    chosen.append(i)
                    solver.add(variables[i])
                    break
                if status != unsat:
                    solver.pop()
                    return _result(catalog, schedules, checks, confirmations, False, solver.reason_unknown())
        solver.pop()
        schedules.append({'units': sum(c['units'] for c in selected), 'sections': [
            {'course': options[i][0]['id'], **options[i][1]} for i in chosen]})
        solver.add(Or([Not(variables[i]) for i in chosen]))
    status = solver.check()
    return _result(catalog, schedules, checks, confirmations, status == unsat,
                   solver.reason_unknown() if status not in (sat, unsat) else None)


def _result(catalog, schedules, checks, confirmations, exhausted, reason):
    return {'status': 'satisfiable' if schedules else 'unknown', 'term': catalog['term'], 'schedules': schedules,
            'eligibility': checks, 'confirmations': list(confirmations), 'exhausted': exhausted, 'reason': reason,
            'note': 'Feasible under supplied facts and confirmations; not a registration or graduation decision.'}
