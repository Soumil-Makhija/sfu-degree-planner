import itertools
import unittest
from sfu_planner.prerequisites import eligibility, evaluate, grade_at_least, graph, transcript_records
from sfu_planner.solver import solve, meetings_conflict, bundles_conflict


def meeting(start=600, end=660, days=None, start_date='2026-09-09', end_date='2026-12-07', campus='Burnaby'):
    return dict(days=days or [0], start=start, end=end, start_date=start_date, end_date=end_date, campus=campus, kind='LEC')


def course(cid, *sections, prereq=None):
    return dict(id=cid, units=3, title=cid, prerequisite=prereq or {'all': []}, sections=[
        {'id': str(i), 'meetings': m} for i, m in enumerate(sections)])


class Prerequisites(unittest.TestCase):
    def test_grade_and_repeats(self):
        self.assertFalse(grade_at_least('P', 'C-'))
        self.assertTrue(grade_at_least('C-', 'C-'))
        self.assertFalse(grade_at_least('D', 'C-'))
        records = [{'course': 'CMPT 120', 'grade': 'F'}, {'course': 'CMPT 120', 'grade': 'B'}]
        self.assertEqual(evaluate({'course': 'CMPT 120', 'min_grade': 'C-'}, records)['status'], 'satisfied')

    def test_and_or_manual(self):
        expr = {'any': [{'course': 'CMPT 120'}, {'manual': 'placement'}]}
        self.assertEqual(evaluate(expr, [])['status'], 'manual_review')
        self.assertEqual(evaluate(expr, [], ['placement'])['status'], 'satisfied')
        self.assertEqual(evaluate(expr, [{'course': 'CMPT 120', 'grade': 'A'}])['status'], 'satisfied')
        self.assertEqual(evaluate({'all': [expr, {'course': 'MATH 151'}]}, [])['status'], 'missing')

    def test_exclusion_and_graph(self):
        c = course('CMPT 125', [meeting()], prereq={'any': [{'course': 'CMPT 120'}, {'course': 'CMPT 130'}]})
        c['credit_exclusion_ranges'] = [{'subject': 'CMPT', 'min_number': 200}]
        self.assertFalse(eligibility(c, [{'course': 'CMPT 225', 'grade': 'A'}])['eligible'])
        self.assertEqual(len(graph({'courses': [c]})['edges']), 2)
        with self.assertRaises(ValueError):
            transcript_records([{'course': 'cmpt120', 'grade': 'A'}])
        for bad_grade in ([], {}, None):
            with self.assertRaises(ValueError):
                transcript_records([{'course': 'CMPT 120', 'grade': bad_grade}])


class Conflicts(unittest.TestCase):
    def test_time_and_campus_boundaries(self):
        self.assertFalse(meetings_conflict(meeting(), meeting(660, 700)))
        self.assertTrue(meetings_conflict(meeting(), meeting(659, 700)))
        self.assertTrue(meetings_conflict(meeting(), meeting(680, 700, campus='Surrey'), 30))
        self.assertFalse(meetings_conflict(meeting(), meeting(690, 720, campus='Surrey'), 30))

    def test_actual_date_weekday_intersection(self):
        self.assertFalse(meetings_conflict(meeting(days=[0], start_date='2026-09-09', end_date='2026-09-10'), meeting()))
        self.assertFalse(meetings_conflict(meeting(end_date='2026-09-20'), meeting(start_date='2026-09-21')))
        self.assertTrue(meetings_conflict(meeting(days=[5], start_date='2026-12-12', end_date='2026-12-12'),
                                         meeting(days=[5], start_date='2026-12-12', end_date='2026-12-12')))


class SolverTests(unittest.TestCase):
    def test_bundle_selection_busy_and_units(self):
        catalog = {'term': 'fixture', 'courses': [course('CMPT 120', [meeting()], [meeting(800, 860)]),
                   course('MATH 151', [meeting(620, 680)], [meeting(900, 960)])]}
        result = solve(catalog, ['CMPT 120', 'MATH 151'], [], limit=10)
        self.assertEqual(len(result['schedules']), 3)
        self.assertTrue(result['exhausted'])
        self.assertEqual(result, solve(catalog, ['CMPT 120', 'MATH 151'], [], limit=10))
        self.assertEqual(len(solve(catalog, ['CMPT 120', 'MATH 151'], [], busy=[meeting(800, 900)])['schedules']), 1)
        self.assertEqual(solve(catalog, ['CMPT 120', 'MATH 151'], [], max_units=3)['status'], 'unsatisfiable')

    def test_prerequisites_and_internal_bundle_conflict(self):
        c = course('CMPT 125', [meeting()], prereq={'course': 'CMPT 120', 'min_grade': 'C-'})
        result = solve({'term': 'fixture', 'courses': [c]}, ['CMPT 125'], [])
        self.assertEqual(result['status'], 'unsatisfiable')
        self.assertIn('eligibility', [x['kind'] for x in result['explanations']])
        c['prerequisite'] = {'all': []}
        c['sections'][0]['meetings'].append(meeting(630, 690))
        self.assertEqual(solve({'term': 'fixture', 'courses': [c]}, ['CMPT 125'], [])['status'], 'unsatisfiable')

    def test_solver_matches_bruteforce(self):
        # All 64 small timing combinations; independent Cartesian-product oracle.
        for starts in itertools.product([600, 650], repeat=6):
            cs = [course(f'FIX {100+i}', [meeting(starts[i*2], starts[i*2]+40)],
                         [meeting(starts[i*2+1]+100, starts[i*2+1]+140)]) for i in range(3)]
            expected = {tuple(s['id'] for s in picks) for picks in itertools.product(*(c['sections'] for c in cs))
                        if all(not bundles_conflict(a, b) for a, b in itertools.combinations(picks, 2))}
            result = solve({'term': 'fixture', 'courses': cs}, [c['id'] for c in cs], [], limit=50)
            actual = {tuple(s['id'] for s in x['sections']) for x in result['schedules']}
            self.assertEqual(actual, expected)

    def test_request_validation_and_no_sections(self):
        c = course('CMPT 120')
        catalog = {'term': 'fixture', 'courses': [c]}
        self.assertEqual(solve(catalog, ['CMPT 120'], [])['status'], 'unsatisfiable')
        for requested in ([], ['CMPT 120', 'CMPT 120'], ['MATH 151'], [{}], [None], [1], [['CMPT 120']]):
            with self.assertRaises(ValueError):
                solve(catalog, requested, [])
