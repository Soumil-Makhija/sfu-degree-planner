"""Explicit prerequisite expressions; unknown academic conditions fail closed."""
import re

GRADES = {g: i for i, g in enumerate(['F', 'D', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+'])}
COURSE = re.compile(r'^[A-Z]{2,5} [0-9]{3}[A-Z]?$')


def grade_at_least(actual, minimum='D'):
    if actual in ('P', 'CR'):
        return minimum in ('P', 'CR', 'D')
    if minimum in ('P', 'CR'):
        minimum = 'D'
    return actual in GRADES and minimum in GRADES and GRADES[actual] >= GRADES[minimum]


def transcript_records(value):
    records = value.get('courses') if isinstance(value, dict) else value
    if not isinstance(records, list) or len(records) > 1000:
        raise ValueError('transcript must be a list (or {courses: [...]}) of at most 1000 courses')
    for record in records:
        if not isinstance(record, dict) or not COURSE.fullmatch(str(record.get('course', ''))):
            raise ValueError('transcript course must use canonical form, e.g. CMPT 120')
        if not isinstance(record.get('grade'), str) or record['grade'] not in {*GRADES, 'P', 'CR', 'W', 'IP', 'N', 'DE', 'F'}:
            raise ValueError(f'unsupported grade for {record["course"]}')
        units = record.get('units', 0)
        if type(units) not in (int, float) or not 0 <= units <= 30:
            raise ValueError('course units must be a number between 0 and 30')
    return records


def evaluate(expression, transcript, confirmations=()):
    """Return satisfied/missing/manual_review and leaf evidence, preserving OR semantics."""
    records = transcript_records(transcript)
    if 'course' in expression:
        course, minimum = expression['course'], expression.get('min_grade', 'D')
        passed = any(r['course'] == course and grade_at_least(r['grade'], minimum) for r in records)
        return {'status': 'satisfied' if passed else 'missing', 'reason': f'{course} >= {minimum}'}
    if 'manual' in expression:
        text = expression['manual']
        return {'status': 'satisfied' if text in confirmations else 'manual_review',
                'reason': text, 'user_confirmed': text in confirmations}
    key = 'all' if 'all' in expression else 'any' if 'any' in expression else None
    if key is None:
        raise ValueError('unknown prerequisite expression')
    children = [evaluate(e, records, confirmations) for e in expression[key]]
    statuses = [c['status'] for c in children]
    if key == 'all':
        status = 'missing' if 'missing' in statuses else 'manual_review' if 'manual_review' in statuses else 'satisfied'
    else:
        status = 'satisfied' if 'satisfied' in statuses else 'manual_review' if 'manual_review' in statuses else 'missing'
    return {'status': status, 'operator': key, 'children': children}


def eligibility(course, transcript, confirmations=()):
    records = transcript_records(transcript)
    result = evaluate(course.get('prerequisite', {'all': []}), records, confirmations)
    reasons = []
    if result['status'] != 'satisfied':
        reasons.append({'kind': 'prerequisite', 'evidence': result})
    completed = [r['course'] for r in records if grade_at_least(r['grade'])]
    for old in completed:
        if old == course['id'] or old in course.get('credit_exclusions', []):
            reasons.append({'kind': 'credit_exclusion', 'reason': old})
        subject, number = old.split()
        for rule in course.get('credit_exclusion_ranges', []):
            if subject == rule['subject'] and rule['min_number'] <= int(number[:3]) <= rule.get('max_number', 999):
                reasons.append({'kind': 'credit_exclusion', 'reason': old})
    for review in course.get('prerequisite_review', []):
        if review not in confirmations:
            reasons.append({'kind': 'manual_review', 'reason': review})
    return {'course': course['id'], 'eligible': not reasons, 'prerequisite': result, 'reasons': reasons,
            'confirmations': sorted(set(confirmations))}


def graph(catalog):
    edges = []
    def walk(target, expr, path):
        if 'course' in expr:
            edges.append({'from': expr['course'], 'to': target, 'min_grade': expr.get('min_grade', 'D'), 'operators': path})
        for key in ('all', 'any'):
            for child in expr.get(key, []):
                walk(target, child, path + [key])
    for course in catalog['courses']:
        walk(course['id'], course['prerequisite'], [])
    return {'nodes': sorted({c['id'] for c in catalog['courses']} | {e['from'] for e in edges}), 'edges': edges,
            'note': 'Edges show dependencies; AND/OR operators and manual predicates remain in course expressions.'}
