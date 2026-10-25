# Academic model and its boundaries

This is an unofficial planning audit for a **first Computing Science BSc, single major, under the Fall 2026 SFU calendar**. It reports evidence for individual modeled requirements. It never certifies graduation. `incomplete` means at least one modeled check lacks enough counted evidence; `manual_review` means no modeled check is missing, with official checks still outstanding. A `satisfied` check means the supplied completion records match that particular rule. It does not authenticate a transcript or confer credit.

## Reviewed official sources

Reviewed on October 25, 2026:

- [Computing Science major, Fall 2026](https://www.sfu.ca/students/calendar/2026/fall/programs/computing-science/major/bachelor-of-science-or-bachelor-of-arts.html): lower and upper requirements, Tables I–III, depth, breadth, BSc credential and prerequisite/continuation grades.
- [Credential definitions, Fall 2026](https://www.sfu.ca/students/calendar/2026/fall/fees-and-regulations/credentials-offered/definitions.html): first-degree 120-unit minimum and graduation GPA/residency rules.
- [WQB, Fall 2026](https://www.sfu.ca/students/calendar/2026/fall/fees-and-regulations/enrolment/WQB.html): designation grades, separate breadth allocations, transfer treatment and exceptions.
- [Faculty of Applied Sciences, Fall 2026](https://www.sfu.ca/students/calendar/2026/fall/faculties-research/faculty-applied-sciences.html): faculty residency requirements, including school-specific upper division residency.
- [Undergraduate grading, Fall 2026](https://www.sfu.ca/students/calendar/2026/fall/fees-and-regulations/grading-policy/grading-systems-and-policies.html): D earns course credit; letter-grade values, temporary grades and administrative notations.

`data/requirements.json` contains the reviewed rules and **94 course metadata entries**. Every entry includes a direct Fall 2026 calendar course URL. The program page supplies its listed courses; eight additional economics, philosophy, archaeology, humanities, biology and physics entries provide a small real-data WQB example set. This is a curated subset of the university calendar, not an exhaustive course catalog. Outline sections used for timetable planning are a separate dataset and do not define degree requirements.

## Rules calculated

| Area | Calculation |
| --- | --- |
| Lower core | CMPT 105W, 120, 125, 201, 210, 225, 276, 295; MACM 101; STAT 271 |
| Mathematics | MATH 150 or 151; MATH 152; MATH 232 or 240. Listed life/social-science calculus substitutes need B+ and school permission and remain manual review. |
| Upper core | CMPT 307 and 376W |
| Degree units | At least 120 total; at least 45 upper division; at least 30 upper division CMPT |
| CS breadth | Four distinct courses assigned to four distinct Table I areas, including CMPT 307. An augmenting-path matching prevents a cross-listed area membership from reusing a course. |
| CS depth | At least 12 CMPT units at the 400 level; 415, 416 and 498 excluded pending special permission |
| BSc credential | MACM 316 plus two distinct Table I/II/III courses, reserving at least 30 other upper division CMPT units. MACM 316 cannot fill its own separate extra-course slot. Table II currently contains no courses. |
| Writing | A lower division W and an upper division CMPT W, at least 3 units each; the latter requires an explicit SFU institution field. Two upper W courses without a lower W remain manual review because exceptions can depend on admission/transfer circumstances. |
| Quantitative | At least two Q courses totaling at least 6 units |
| Designated breadth | Two courses and at least 6 units in each of B-Hum, B-Soc and B-Sci, all outside CMPT |
| Additional breadth | Two further courses and at least 6 units outside CMPT; these courses cannot also occupy a designated breadth slot |

Fall 2026 changed the breadth requirement to **four of six areas**. Older five-area checklists are not used. CMPT 201, CMPT 210 and STAT 271 belong to this calendar's lower core; an older MACM 201 checklist is not substituted. Optional named concentrations, honours, BA, second degrees, joint/double majors, dual degrees and BEd combinations are outside the supported program.

WQB credit requires C- or better. A D can earn general course credit while failing a WQB designation check. Computing Science prerequisite entry also requires C- in prerequisite courses; that is evaluated by the separate prerequisite planner rather than imposing C- as an invented blanket graduation course grade. Unknown grades, including P/CR and administrative grades outside the explicit credit model, are excluded with review notes. Failed, withdrawn and in-progress attempts earn no completion credit.

Each course can contribute to multiple compatible checks, such as total units, depth, program breadth and Q. Units are only counted once in a given unit total. W/Q and B can overlap where the calendar allows. A course can occupy only one of the four B buckets. Breadth allocation searches for a maximum number of fully satisfied buckets and returns the actual courses chosen. The reviewed metadata contains courses of at least three units, so allocation uses two courses per bucket; a future metadata extension with smaller-unit courses requires extending that allocation rule before claiming coverage.

## Transcript schema and trust

Supply a JSON array, or an object with a `courses` array:

```json
[
  {"course": "CMPT 120", "grade": "A", "units": 3},
  {"course": "CMPT 376W", "grade": "B+", "institution": "SFU"}
]
```

`course` and completed `grade` determine membership. `units` is optional for a reviewed course; the curated calendar units take precedence, and disagreement is reported. For a course outside the snapshot, supplied units appear as `provisional_units`; they cannot satisfy the verified `earned_units` target. Supplied `designations`, `level`, `verified` or similar claims cannot override the reviewed metadata. Unknown course designations are not guessed from a title, department, course number or a caller's verification flag. Numbered 300–499 courses are modeled as upper division; graduate courses require review.

`institution: "SFU"` supplies the residency evidence needed by the upper W check. Missing institution is not inferred as SFU. `transfer: true` or an institution other than SFU marks a transfer record. An assigned course-equivalent identifier may be used for content and provisional degree planning, with a transfer review issue, but WQB credit is withheld until actual articulation is reviewed. This avoids treating an SFU W counterpart as evidence that transferred W credit was awarded. Historical credit amounts and designations may differ from the Fall 2026 snapshot and require review.

Repeats of the same course count once, using the highest supplied passing letter grade. A few explicit duplicate-credit sets are also collapsed: cross-listed CMPT/MACM 476, Calculus I alternatives, Calculus II alternatives and linear-algebra alternatives. These are conservative planning choices. The audit does not interpret chronological credit restrictions or determine which attempt SFU would officially award. Duplicate alternatives raise a review issue. Repeatable special topics are counted only once by identifier until their separate approved topics can be verified.

## Always requiring official review

The output retains explicit manual-review checks for:

- Official transcript authenticity, awarded credit, transfer articulations, substitutions, historical course exclusions, repeatable topics and permissions.
- Overall, upper division, program and program upper division graduation GPAs, including the 2.00 minima, and Computing Science's separate 2.40 continuation CGPA rule. The course-selection model does not know the official GPA populations, failures, exclusions and approved program allocation, so it does not certify these averages.
- SFU residency: half of total units, two thirds of upper division units, and two thirds of school upper division units. The correct program population and institutional record must be reviewed.
- Applicable calendar/cohort, admission and continuation standing, other credentials, WQB exemptions or transfer exceptions, and final credential approval.

Generic unit totals alone are insufficient evidence that a student may graduate. Contact SFU advising to determine applicability and resolve manual-review items. No SFU affiliation or institutional approval is claimed.

## Validation

`python -m unittest discover -s tests -p test_audit.py -v` exercises real calendar requirements with synthetic completion records. It covers the Fall 2026 changes, failed/repeated attempts, untrusted units/designations, unknown credits, cross-listed exclusions, permission alternatives, distinct CS breadth matching, depth exclusions, non-overlapping BSc extra slots, SFU upper W evidence, separate WQB breadth buckets and a complete modeled example that still refuses graduation certification.
