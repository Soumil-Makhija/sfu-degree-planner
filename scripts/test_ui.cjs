#!/usr/bin/env node
'use strict';

/*
 * Real Python API fixtures + the production app.js, with a minimal DOM fixture.
 * Run: python scripts/check_ui.py
 *
 * This checks controller events, request construction, text rendering, tab
 * attributes, and error recovery. It does not parse/render HTML or CSS, implement
 * browser layout, check the accessibility tree, or establish screen-reader
 * behavior. An actual-browser visual/accessibility check is still required.
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const staticDir = path.join(root, 'sfu_planner', 'static');
const elements = new Map();

class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase();
    this.childNodes = [];
    this.attributes = {};
    this.value = '';
    this.checked = false;
    this.hidden = false;
    this.disabled = false;
    this.className = '';
    this._text = '';
    this.listeners = new Map();
    this.classList = {
      toggle: (value, force) => {
        const classes = new Set(this.className.split(/\s+/).filter(Boolean));
        const add = force === undefined ? !classes.has(value) : force;
        if (add) classes.add(value); else classes.delete(value);
        this.className = [...classes].join(' ');
        return add;
      },
      contains: (value) => this.className.split(/\s+/).includes(value),
    };
  }
  set id(value) { this._id = value; elements.set(value, this); }
  get id() { return this._id; }
  get children() { return this.childNodes.filter((child) => child.tagName !== '#TEXT'); }
  set textContent(value) { this._text = String(value); this.childNodes = []; }
  get textContent() { return this._text + this.childNodes.map((child) => child.textContent).join(''); }
  append(...nodes) {
    for (const node of nodes) this.childNodes.push(typeof node === 'string' ? textNode(node) : node);
  }
  replaceChildren(...nodes) { this.childNodes = []; this._text = ''; this.append(...nodes); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key] ?? null; }
  addEventListener(name, listener) {
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push(listener);
  }
  async dispatch(name, event = {}) {
    for (const listener of this.listeners.get(name) || []) await listener(event);
  }
  focus() { document.activeElement = this; }
  querySelectorAll(selector) {
    const all = [];
    function walk(node) { for (const child of node.children) { all.push(child); walk(child); } }
    walk(this);
    if (selector === 'input:checked') return all.filter((node) => node.tagName === 'INPUT' && node.checked);
    if (selector === '.schedule-picker button') return all.filter((node) => node.className === 'schedule-picker').flatMap((node) => node.children).filter((node) => node.tagName === 'BUTTON');
    throw new Error(`The minimal DOM fixture does not support selector: ${selector}`);
  }
}
function textNode(text) { const node = new Element('#text'); node._text = String(text); return node; }

// Register the real HTML's IDs. Only the tab ancestry is needed by controller
// queries; dynamically created result trees are retained exactly as appended.
const html = fs.readFileSync(path.join(staticDir, 'index.html'), 'utf8');
for (const match of html.matchAll(/<([a-z-]+)[^>]*\bid="([^"]+)"/g)) {
  const element = new Element(match[1]); element.id = match[2];
}
const get = (id) => { assert(elements.has(id), `Missing HTML/controller ID: ${id}`); return elements.get(id); };
const tabs = new Element(); tabs.className = 'tabs';
for (const name of ['plan', 'audit', 'graph']) tabs.append(get(`tab-${name}`));
const document = {
  getElementById: (id) => elements.get(id) || null,
  createElement: (tag) => new Element(tag),
  createTextNode: textNode,
  querySelector: (selector) => {
    assert.equal(selector, '.tabs', 'Unexpected document selector');
    return tabs;
  },
  activeElement: null,
};

async function main() {
  if (!process.argv[2]) throw new Error('Pass generated fixtures, or run: python scripts/check_ui.py');
  const fixtures = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const requests = [];
  const overrides = new Map();
  let passed = 0;
  const pass = (name) => { passed += 1; console.log(`ok ${passed} - ${name}`); };
  const context = {
    document, console, URL, Intl, Set, JSON, Date, Number, Error, Promise,
    fetch: async (url, options = {}) => {
      requests.push({url, body: options.body ? JSON.parse(options.body) : null});
      assert(url in fixtures || overrides.has(url), `Unexpected API request: ${url}`);
      const response = overrides.get(url) || {ok: true, status: 200, body: fixtures[url]};
      return {ok: response.ok, status: response.status, json: async () => response.body};
    },
  };
  for (const [id, value] of Object.entries({transcript: '[]', busy: '[]', 'max-units': '18', travel: '60', 'schedule-limit': '5'})) get(id).value = value;
  vm.createContext(context);
  const evaluate = (source) => vm.runInContext(source, context);
  evaluate(fs.readFileSync(path.join(staticDir, 'app.js'), 'utf8'));
  await new Promise(setImmediate); // Complete initial Promise.all fetch/render.

  assert.equal(get('snapshot-term').textContent, 'Fall 2026');
  assert.equal(get('course-list').children.length, fixtures['/api/catalog'].courses.length);
  assert.equal(get('generate').disabled, false);
  assert(get('status').textContent.includes('Snapshot ready'));
  pass('initial catalog and graph load, course controls become usable');

  await get('load-example').dispatch('click');
  assert.equal(get('selection-count').textContent, `${fixtures['/api/example'].courses.length} selected`);
  assert.deepEqual(JSON.parse(get('transcript').value), fixtures['/api/example'].transcript);
  assert(get('plan-results').textContent.includes('Schedule 1'));
  assert(get('plan-results').textContent.includes('Date-specific exams'));
  for (const course of fixtures['/api/example'].courses) assert(get('plan-results').textContent.includes(course));
  assert(get('audit-results').textContent.includes('Requirement-by-requirement evidence'));
  assert(get('audit-results').textContent.includes('Unofficial planning audit'));
  assert(get('graph-results').textContent.includes('ANY'));
  assert.deepEqual(requests.find((request) => request.url === '/api/plan').body, {
    ...fixtures['/api/example'], courses: [...fixtures['/api/example'].courses].sort(),
  });
  pass('example click populates inputs, sends the real request, renders plan/exams/audit');

  const choices = get('plan-results').querySelectorAll('.schedule-picker button');
  assert(choices.length >= 2, 'Real-data fixture must offer alternative schedules');
  await choices[1].dispatch('click');
  assert.equal(get('plan-results').querySelectorAll('.schedule-picker button')[1].getAttribute('aria-pressed'), 'true');
  assert(get('plan-results').textContent.includes('Schedule 2'));
  pass('schedule option click updates the selected bundle and pressed state');

  get('tab-plan').focus(); let prevented = false;
  await tabs.dispatch('keydown', {key: 'ArrowRight', preventDefault() { prevented = true; }});
  assert(prevented);
  assert.equal(get('tab-audit').getAttribute('aria-selected'), 'true');
  assert.equal(document.activeElement, get('tab-audit'));
  assert.equal(get('panel-audit').hidden, false);
  assert.equal(get('panel-plan').hidden, true);
  await tabs.dispatch('keydown', {key: 'End', preventDefault() {}});
  assert.equal(get('tab-graph').getAttribute('aria-selected'), 'true');
  pass('arrow and End keys select tabs, update hidden panels, and move focus');

  // Change courses through the actual checkbox listeners, not direct state edits.
  const courses = fixtures['/api/catalog'].courses;
  for (let index = 0; index < courses.length; index += 1) {
    const checkbox = get(`course-${index}`);
    checkbox.checked = courses[index].id === 'MATH 151';
    await checkbox.dispatch('change');
  }
  assert.equal(get('selection-count').textContent, '1 selected');
  assert.equal(get('assumptions').hidden, false);
  const condition = get('condition-0');
  assert(condition.value.includes('Pre-Calculus'));
  condition.checked = true; await condition.dispatch('change');
  const request = evaluate('planBody()');
  assert.equal(request.confirmations.length, 1);
  assert.equal(request.confirmations[0], condition.value);
  assert(get('status').textContent.includes('Inputs changed'));
  pass('course selection exposes exact manual conditions and constructs confirmations');

  get('transcript').value = '{bad'; const before = requests.length;
  await get('audit-button').dispatch('click');
  assert(get('status').textContent.includes('not valid JSON'));
  assert.equal(get('status').classList.contains('error'), true);
  assert.equal(document.activeElement, get('transcript'));
  assert.equal(requests.length, before, 'Malformed JSON must not reach the API');
  assert.equal(get('generate').disabled, false);
  pass('invalid JSON is announced locally, focuses its field, restores controls');

  get('transcript').value = '[]';
  for (let index = 0; index < courses.length; index += 1) {
    const checkbox = get(`course-${index}`); checkbox.checked = courses[index].id === 'CMPT 125';
    await checkbox.dispatch('change');
  }
  overrides.set('/api/plan', {ok: true, status: 200, body: fixtures.unsatisfiable_plan});
  await get('generate').dispatch('click');
  assert.equal(fixtures.unsatisfiable_plan.status, 'unsatisfiable');
  assert(get('plan-results').textContent.includes('These choices don’t fit yet'));
  assert(get('plan-results').textContent.includes('A conflicting set of constraints'));
  assert(get('plan-results').textContent.includes('Condition not met'));
  assert.equal(get('plan-results').querySelectorAll('.schedule-picker button').length, 0);
  pass('real unsatisfiable result renders constraints and prerequisite evidence');

  overrides.set('/api/audit', {ok: false, status: 400, body: {error: 'Example validation rejection'}});
  await get('audit-button').dispatch('click');
  assert.equal(get('status').textContent, 'Example validation rejection');
  assert.equal(get('audit-button').disabled, false);
  pass('API validation failures are announced and controls recover');

  const sourceTitle = evaluate('state.catalog.courses[0].title');
  evaluate("state.catalog.courses[0].title='<img src=x onerror=alert(1)>';renderCourses()");
  assert(get('course-list').textContent.includes('<img src=x onerror=alert(1)>'));
  assert.equal(evaluate("link('unsafe', 'javascript:alert(1)').href"), undefined);
  context.originalTitle = sourceTitle;
  evaluate('state.catalog.courses[0].title=originalTitle');
  pass('source titles remain text and executable source URLs get no link');

  console.log(`PASS: ${passed} UI controller interaction checks with freshly generated real Python API results.`);
  console.log('LIMIT: minimal DOM fixture only; browser rendering, layout, accessibility tree, and screen readers are not verified.');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
