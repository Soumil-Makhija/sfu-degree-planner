'use strict';

const $ = (id) => document.getElementById(id);
const state = {catalog: null, graph: null, selected: new Set(), confirmations: new Set(), plan: null, audit: null, schedule: 0, working: false};
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function clear(id) { const node = typeof id === 'string' ? $(id) : id; node.replaceChildren(); return node; }
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
function link(text, url) {
  const node = el('a', text);
  // Source links must never turn untrusted catalog text into an executable URL.
  try { const parsed = new URL(url); if (['https:', 'http:'].includes(parsed.protocol)) node.href = parsed.href; } catch (_) { /* Render invalid links as text. */ }
  if (node.href) { node.target = '_blank'; node.rel = 'noopener noreferrer'; }
  return node;
}
function badge(text, tone = 'neutral') { return el('span', text, `badge ${tone}`); }
function niceKey(key) { return key.replaceAll('_', ' '); }
function human(value) {
  if (Array.isArray(value)) return value.length ? value.map(human).join(' · ') : 'None';
  if (value && typeof value === 'object') return Object.entries(value).map(([key, val]) => `${niceKey(key)}: ${human(val)}`).join('; ');
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return value == null ? 'None' : String(value);
}
function clock(minutes) { return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`; }
function shortDate(value) {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en-CA', {month: 'short', day: 'numeric'}).format(date);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  let payload;
  try { payload = await response.json(); } catch (_) { throw new Error(`The local server returned an unreadable response (${response.status}).`); }
  if (!response.ok) throw new Error(typeof payload.error === 'string' ? payload.error : payload.message || `Request failed (${response.status}).`);
  return payload;
}
function jsonArray(id, label) {
  let value;
  try { value = JSON.parse($(id).value); } catch (error) { $(id).focus(); throw new Error(`${label} is not valid JSON: ${error.message}`); }
  if (!Array.isArray(value)) { $(id).focus(); throw new Error(`${label} must be a JSON array of records.`); }
  return value;
}
function manualConditions(expression, result = new Set()) {
  if (!expression) return result;
  if (typeof expression.manual === 'string') result.add(expression.manual);
  for (const op of ['all', 'any']) for (const child of expression[op] || []) manualConditions(child, result);
  return result;
}
function currentConfirmations() {
  return [...$('confirmation-list').querySelectorAll('input:checked')].map((input) => input.value);
}
function renderConfirmations() {
  const container = clear('confirmation-list');
  const conditions = new Set();
  for (const course of state.catalog.courses) if (state.selected.has(course.id)) {
    manualConditions(course.prerequisite, conditions);
    for (const review of course.prerequisite_review || []) conditions.add(review);
  }
  $('assumptions').hidden = conditions.size === 0;
  [...conditions].sort().forEach((condition, i) => {
    const label = el('label', null, 'confirmation');
    const input = document.createElement('input');
    input.type = 'checkbox'; input.value = condition; input.id = `condition-${i}`; input.checked = state.confirmations.has(condition);
    input.addEventListener('change', () => { if (input.checked) state.confirmations.add(condition); else state.confirmations.delete(condition); markStale(); });
    label.append(input, el('span', condition)); container.append(label);
  });
}
function markStale() {
  if (state.plan || state.audit) status('Inputs changed. Generate a new timetable or rerun the audit to update your results.');
}
function renderCourses() {
  const list = clear('course-list');
  state.catalog.courses.forEach((course, i) => {
    const item = el('div', null, 'course-item');
    const top = el('div', null, 'course-top');
    const input = document.createElement('input'); input.type = 'checkbox'; input.id = `course-${i}`; input.value = course.id; input.checked = state.selected.has(course.id);
    const label = el('label', null, 'course-label'); label.htmlFor = input.id;
    const title = el('span', course.id, 'course-title'); title.append(el('span', `${course.units} units`));
    label.append(title, el('span', course.title, 'course-name')); top.append(input, label);
    const details = el('details', null, 'course-detail'); details.append(el('summary', 'Prerequisites & source'));
    details.append(el('p', course.prerequisite_text || 'No course prerequisite listed.'));
    if (course.restriction_text) details.append(el('p', course.restriction_text));
    details.append(el('p', `${course.sections.length} complete section bundles in snapshot.`));
    if (course.calendar_url) { const a = link('SFU course calendar ↗', course.calendar_url); a.className = 'source-link'; details.append(a); }
    item.append(top, details); list.append(item);
    input.addEventListener('change', () => { if (input.checked) state.selected.add(course.id); else state.selected.delete(course.id); $('selection-count').textContent = `${state.selected.size} selected`; renderConfirmations(); markStale(); });
  });
  $('selection-count').textContent = `${state.selected.size} selected`;
  renderConfirmations();
}
function setTab(name, focus = false) {
  for (const tab of ['plan', 'audit', 'graph']) {
    const selected = name === tab;
    $(`tab-${tab}`).setAttribute('aria-selected', String(selected));
    $(`tab-${tab}`).tabIndex = selected ? 0 : -1;
    $(`panel-${tab}`).hidden = !selected;
  }
  if (focus) $(`tab-${name}`).focus();
}
function busyWorking(value) {
  state.working = value;
  for (const id of ['generate', 'audit-button', 'load-example', 'audit-empty']) {
    const button = $(id); if (button) button.disabled = value || !state.catalog;
  }
  $('generate').setAttribute('aria-busy', String(value));
}
function planBody() {
  const courses = [...state.selected].sort();
  if (!courses.length) throw new Error('Select at least one course to generate a timetable.');
  return {courses, transcript: jsonArray('transcript', 'Transcript records'), busy: jsonArray('busy', 'Busy meetings'), max_units: Number($('max-units').value), travel_minutes: Number($('travel').value), limit: Number($('schedule-limit').value), confirmations: currentConfirmations()};
}
function evidence(parent, value, title = 'Inspect structured evidence') {
  const details = el('details', null, 'evidence'); details.append(el('summary', title), el('pre', JSON.stringify(value, null, 2))); parent.append(details);
}
function reasonText(reason) {
  if (reason.reason) return reason.reason;
  if (reason.kind === 'prerequisite') return `Prerequisite status: ${niceKey(reason.evidence.status)}. Expand the evidence for AND / OR conditions.`;
  return human(reason);
}
function renderEligibility(container, checks) {
  if (!checks || !checks.length) return;
  const panel = el('div', null, 'panel eligibility-panel'); panel.append(el('h3', 'Prerequisite & credit checks'));
  for (const check of checks) {
    const row = el('div', null, 'eligibility-row'); const top = el('div', null, 'eligibility-top');
    top.append(el('strong', check.course), badge(check.eligible ? 'Eligible under supplied facts' : 'Condition not met', check.eligible ? 'success' : 'warning')); row.append(top);
    if (check.reasons && check.reasons.length) { const list = el('ul'); for (const reason of check.reasons) list.append(el('li', reasonText(reason))); row.append(list); }
    evidence(row, check.prerequisite, 'Inspect prerequisite expression evidence'); panel.append(row);
  }
  container.append(panel);
}
function renderSchedule(container, schedule, index) {
  const panel = el('div', null, 'schedule-panel');
  const heading = el('div', null, 'schedule-header'); heading.append(el('h3', `Schedule ${index + 1}`), el('span', `${schedule.units} units · ${schedule.sections.length} courses`)); panel.append(heading);
  const regular = [], exams = [];
  schedule.sections.forEach((section, courseIndex) => { for (const meeting of section.meetings) (meeting.kind === 'EXAM' ? exams : regular).push({...meeting, course: section.course, section: section.id, tone: courseIndex % 4}); });
  const activeDays = [0, 1, 2, 3, 4]; if (regular.some((m) => m.days.includes(5))) activeDays.push(5); if (regular.some((m) => m.days.includes(6))) activeDays.push(6);
  const scroll = el('div', null, 'table-scroll');
  const table = el('table', null, 'timetable'); table.setAttribute('aria-label', `Weekly meetings for schedule ${index + 1}; dates listed in each meeting`);
  const head = el('thead'); const headRow = el('tr'); for (const day of activeDays) { const th = el('th', days[day]); th.scope = 'col'; headRow.append(th); } head.append(headRow); table.append(head);
  const tbody = el('tbody'); const row = el('tr');
  for (const day of activeDays) {
    const cell = el('td');
    const meetings = regular.filter((meeting) => meeting.days.includes(day)).sort((a, b) => a.start - b.start || a.course.localeCompare(b.course));
    for (const meeting of meetings) {
      const card = el('div', null, `meeting-card tone-${meeting.tone}`);
      card.append(el('strong', meeting.course), el('time', `${clock(meeting.start)}–${clock(meeting.end)}`), el('span', `${meeting.kind} · ${meeting.component || meeting.section}`), el('br'), el('span', meeting.campus), el('small', `${shortDate(meeting.start_date)}–${shortDate(meeting.end_date)}`)); cell.append(card);
    }
    if (!meetings.length) cell.append(el('span', 'No classes', 'free-day'));
    row.append(cell);
  }
  tbody.append(row); table.append(tbody); scroll.append(table); panel.append(scroll);
  const examPanel = el('section', null, 'exams'); examPanel.append(el('h3', 'Date-specific exams'));
  if (!exams.length) examPanel.append(el('p', 'No exams in the selected snapshot bundles.', 'help'));
  else {
    const list = el('ul', null, 'exam-list');
    exams.sort((a, b) => a.start_date.localeCompare(b.start_date) || a.start - b.start).forEach((meeting) => {
      const item = el('li'); const detail = el('div'); detail.append(el('strong', `${meeting.course} · ${clock(meeting.start)}–${clock(meeting.end)}`), el('small', `${meeting.campus} · ${meeting.component || meeting.section}`));
      item.append(el('span', shortDate(meeting.start_date), 'exam-date'), detail); list.append(item);
    }); examPanel.append(list);
  }
  panel.append(examPanel);
  const bundles = el('details', null, 'bundle-list'); bundles.append(el('summary', 'Selected enrollment bundles & original outlines'));
  const bundleList = el('ul');
  for (const section of schedule.sections) { const item = el('li'); item.append(el('span', `${section.course} · ${section.id}`)); const links = el('span'); (section.source_urls || []).forEach((url, i) => { if (i) links.append(document.createTextNode(' · ')); links.append(link(`Outline ${i + 1} ↗`, url)); }); item.append(links); bundleList.append(item); }
  bundles.append(bundleList); panel.append(bundles); container.append(panel);
}
function renderPlan() {
  const result = state.plan; const container = clear('plan-results');
  const heading = el('div', null, 'result-heading'); const title = el('div'); title.append(el('p', 'Your next term, taking shape', 'eyebrow'));
  const schedules = result.schedules || [];
  title.append(el('h2', schedules.length ? 'Room for a good term.' : result.status === 'unsatisfiable' ? 'These choices don’t fit yet.' : 'The search needs another look.'), el('p', schedules.length ? `${schedules.length} feasible ${schedules.length === 1 ? 'schedule' : 'schedules'} found${result.exhausted ? ' · all possibilities enumerated' : ' · more may exist'}.` : 'Review prerequisites, busy times, campus travel, and unit limits below.'));
  heading.append(title, badge(schedules.length ? 'Feasible under supplied facts' : niceKey(result.status), schedules.length ? 'success' : 'warning')); container.append(heading);
  if (result.confirmations && result.confirmations.length) {
    const assumptions = el('div', null, 'result-note warning'); assumptions.append(el('strong', 'User-supplied assumptions in this result: '), document.createTextNode(result.confirmations.join(' · '))); container.append(assumptions);
  }
  if (schedules.length) {
    const picker = el('div', null, 'schedule-picker'); picker.setAttribute('aria-label', 'Choose a feasible schedule');
    schedules.forEach((_, i) => { const button = el('button', `Option ${i + 1}`); button.type = 'button'; button.setAttribute('aria-pressed', String(i === state.schedule)); button.addEventListener('click', () => { state.schedule = i; renderPlan(); const current = $('plan-results').querySelectorAll('.schedule-picker button')[i]; if (current) current.focus(); }); picker.append(button); }); container.append(picker);
    renderSchedule(container, schedules[state.schedule], state.schedule);
    container.append(el('p', 'Weekly view shows the recurring pattern; each card’s date range governs attendance. Exams are separate. Times are local to America/Vancouver. Holidays are not modeled.', 'result-note'));
  } else if (result.explanations && result.explanations.length) {
    const panel = el('div', null, 'panel'); panel.append(el('h3', 'A conflicting set of constraints'));
    const list = el('ul', null, 'help'); const seen = new Set();
    for (const reason of result.explanations) {
      let text = `${niceKey(reason.kind)}: ${reason.course || (reason.courses || []).join(' + ') || ''}`;
      if (reason.kind === 'unit_limit') text = `The selected courses exceed the ${reason.maximum}-unit limit.`;
      if (reason.section) text += ` · ${reason.section}`;
      if (!seen.has(text)) { seen.add(text); list.append(el('li', text)); }
    }
    panel.append(list, el('p', 'This is one conflicting set, not an exhaustive diagnosis. Other constraints may need changes after this set is resolved.', 'help')); evidence(panel, result.explanations); container.append(panel);
  }
  if (result.reason) container.append(el('p', `Solver detail: ${result.reason}. Results may be partial.`, 'result-note warning'));
  renderEligibility(container, result.eligibility);
  container.append(el('p', result.note || 'Feasible means compatible with this snapshot and the supplied facts. It does not reserve a seat or approve registration.', 'help audit-provenance'));
}
function checkBadge(statusValue) { return statusValue === 'satisfied' ? badge('Model match', 'success') : statusValue === 'manual_review' ? badge('Manual review', 'warning') : badge('Missing', 'neutral'); }
function renderAudit() {
  const result = state.audit; const container = clear('audit-results');
  const checks = result.checks || []; const matches = checks.filter((check) => check.status === 'satisfied').length;
  const heading = el('div', null, 'result-heading'); const text = el('div'); text.append(el('p', `${result.academic_year} · Computing Science BSc`, 'eyebrow'), el('h2', 'Progress you can trace.'), el('p', `${matches} of ${checks.length} modeled checks match your supplied completed records.`)); heading.append(text, badge('Unofficial planning audit', 'warning')); container.append(heading);
  container.append(el('p', result.disclaimer, 'result-note'));
  const metrics = el('div', null, 'audit-metrics');
  for (const id of ['total_units', 'upper_units', 'upper_cmpt_units', 'depth_units']) {
    const check = checks.find((candidate) => candidate.id === id); if (!check) continue;
    const metric = el('div', null, 'metric'); const strong = el('strong', check.earned_units); strong.append(el('small', ` / ${check.required_units}`));
    const progress = document.createElement('progress'); progress.max = check.required_units; progress.value = check.earned_units; progress.setAttribute('aria-label', `${check.label}: ${check.earned_units} of ${check.required_units} units`);
    metric.append(el('span', check.label, 'metric-label'), strong, progress, el('p', `${check.remaining_units} units remaining${check.provisional_units > check.earned_units ? ` · ${check.provisional_units} including provisional units` : ''}`)); metrics.append(metric);
  }
  container.append(metrics);
  const summary = el('div', null, 'audit-summary'); summary.append(badge(`${matches} model matches`, 'success'), badge(`${(result.missing_checks || []).length} missing checks`), badge(`${(result.manual_review_checks || []).length} need review`, 'warning')); container.append(summary);
  const panel = el('div', null, 'schedule-panel'); const panelHeading = el('div', null, 'schedule-header'); panelHeading.append(el('h3', 'Requirement-by-requirement evidence')); panel.append(panelHeading);
  const list = el('div', null, 'check-list');
  for (const check of checks) {
    const details = el('details', null, 'check-row'); const label = el('summary'); label.append(el('span', check.label, 'check-label'), checkBadge(check.status)); details.append(label);
    const body = el('div', null, 'check-details'); const dl = el('dl');
    for (const [key, value] of Object.entries(check)) { if (['id', 'label', 'status'].includes(key)) continue; dl.append(el('dt', niceKey(key)), el('dd', human(value))); }
    if (!dl.children.length) body.append(el('p', 'This condition requires official records, academic interpretation, or institutional approval.')); else body.append(dl);
    details.append(body); list.append(details);
  }
  panel.append(list); container.append(panel);
  if ((result.issues || []).length || (result.ignored_attempts || []).length) { const panel = el('div', null, 'panel eligibility-panel'); panel.append(el('h3', 'Transcript interpretation')); const list = el('ul', null, 'help'); for (const issue of result.issues || []) list.append(el('li', issue)); for (const ignored of result.ignored_attempts || []) list.append(el('li', `${ignored.course}: ${ignored.reason}`)); panel.append(list); container.append(panel); }
  const provenance = el('div', null, 'audit-provenance'); provenance.append(el('p', result.program), el('p', `Requirements reviewed ${result.requirements_reviewed_on}. Only completed records are audited; the proposed timetable is not counted.`));
  const links = el('div', null, 'source-links'); for (const [key, url] of Object.entries(result.sources || {})) links.append(link(`${niceKey(key)} ↗`, url)); provenance.append(links); container.append(provenance);
}
function expressionText(expression) {
  if (expression.course) return `${expression.course} ≥ ${expression.min_grade || 'D'}`;
  if (expression.manual) return `Verify: ${expression.manual}`;
  if (expression.all) return expression.all.length ? `ALL (${expression.all.map(expressionText).join('; ')})` : 'No course prerequisite';
  if (expression.any) return `ANY (${expression.any.map(expressionText).join('; ')})`;
  return 'Unmodeled condition; review required';
}
function renderGraph() {
  const container = clear('graph-results');
  for (const course of state.catalog.courses) {
    const details = el('details', null, 'dependency-group'); const edges = state.graph.edges.filter((edge) => edge.to === course.id);
    const summary = el('summary'); summary.append(el('span', course.id), el('small', `${edges.length} course ${edges.length === 1 ? 'dependency' : 'dependencies'}`)); details.append(summary, el('p', course.prerequisite_text || 'No course prerequisite listed.', 'help'));
    if (edges.length) {
      const scroll = el('div', null, 'table-scroll'); const table = el('table', null, 'dependency-table'); table.setAttribute('aria-label', `Dependency edges for ${course.id}`);
      const head = el('thead'); const row = el('tr'); for (const text of ['From course', 'Minimum grade', 'Expression path']) { const th = el('th', text); th.scope = 'col'; row.append(th); } head.append(row); table.append(head);
      const body = el('tbody'); for (const edge of edges) { const row = el('tr'); row.append(el('td', `${edge.from} → ${edge.to}`), el('td', edge.min_grade), el('td', (edge.operators || []).map((op) => op.toUpperCase()).join(' → ') || 'Direct dependency')); body.append(row); } table.append(body); scroll.append(table); details.append(scroll);
    }
    const conditions = [...manualConditions(course.prerequisite), ...(course.prerequisite_review || [])]; if (conditions.length) details.append(el('p', `Manual conditions: ${conditions.join(' · ')}`, 'dependency-manual'));
    const expression = el('details', null, 'evidence'); expression.append(el('summary', 'Full AND / OR expression'), el('pre', expressionText(course.prerequisite))); details.append(expression); container.append(details);
  }
}
async function generatePlan({switchView = true} = {}) {
  const body = planBody(); status('Searching complete section bundles and checking dated conflicts…');
  const result = await api('/api/plan', body); state.plan = result; state.schedule = 0; renderPlan(); if (switchView) setTab('plan');
  status(result.schedules && result.schedules.length ? `Found ${result.schedules.length} feasible schedules. Dates, exams, and prerequisite evidence are ready to review.` : 'No feasible schedule returned. Inspect the constraint and prerequisite explanations.');
}
async function runAudit({switchView = true} = {}) {
  const transcript = jsonArray('transcript', 'Transcript records'); status('Auditing completed records against the reviewed Fall 2026 rules…');
  state.audit = await api('/api/audit', {transcript}); renderAudit(); if (switchView) setTab('audit');
  status(`Audit complete: ${state.audit.missing_checks.length} missing checks and ${state.audit.manual_review_checks.length} checks requiring review.`);
}
async function perform(work) {
  if (state.working) return;
  busyWorking(true);
  try { await work(); } catch (error) { status(error.message || String(error), true); } finally { busyWorking(false); }
}
async function loadExample() {
  const example = await api('/api/example');
  $('transcript').value = JSON.stringify(example.transcript || [], null, 2); $('busy').value = JSON.stringify(example.busy || [], null, 2);
  $('max-units').value = example.max_units || 18; $('travel').value = example.travel_minutes ?? 60; $('schedule-limit').value = String(example.limit || 5);
  state.selected = new Set(example.courses || []); state.confirmations = new Set(example.confirmations || []); renderCourses();
  await generatePlan(); await runAudit({switchView: false}); setTab('plan'); status('Example ready. Inspect timetable options, open the degree audit, or edit the records to explore your own plan.');
}
async function init() {
  for (const name of ['plan', 'audit', 'graph']) $(`tab-${name}`).addEventListener('click', () => setTab(name));
  document.querySelector('.tabs').addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const tabs = ['plan', 'audit', 'graph']; const current = tabs.findIndex((name) => $(`tab-${name}`) === document.activeElement); if (current < 0) return;
    event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (current + (event.key === 'ArrowRight' ? 1 : 2)) % 3; setTab(tabs[next], true);
  });
  $('generate').addEventListener('click', () => perform(generatePlan)); $('audit-button').addEventListener('click', () => perform(runAudit)); $('audit-empty').addEventListener('click', () => perform(runAudit)); $('load-example').addEventListener('click', () => perform(loadExample));
  for (const id of ['transcript', 'busy', 'max-units', 'travel', 'schedule-limit']) $(id).addEventListener('input', markStale);
  try {
    [state.catalog, state.graph] = await Promise.all([api('/api/catalog'), api('/api/graph')]);
    const term = state.catalog.term.split('-'); $('snapshot-term').textContent = `${term[1][0].toUpperCase()}${term[1].slice(1)} ${term[0]}`; $('snapshot-count').textContent = `${state.catalog.courses.length} courses · offline snapshot`;
    $('source-summary').textContent = `${state.catalog.source.name}. Snapshot fetched ${state.catalog.source.fetched_at.slice(0, 10)}. All meeting times use ${state.catalog.timezone}.`;
    const notes = clear('catalog-notes'); for (const note of state.catalog.notes || []) notes.append(el('li', note));
    const item = el('li'); item.append(link('Original SFU course outlines API ↗', state.catalog.source.base_url)); notes.append(item);
    renderCourses(); renderGraph(); busyWorking(false); status('Snapshot ready. Load the example or select courses to start your plan.');
  } catch (error) { status(`Cannot load planning data: ${error.message}. Check that the local server is running and reload this page.`, true); }
}
init();
