const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const sourcePath = path.join(root, 'src', 'utils', 'meetingDateSections.ts');
const source = fs.readFileSync(sourcePath, 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
});

const moduleShim = { exports: {} };
Function('exports', 'require', 'module', '__filename', '__dirname', output.outputText)(
  moduleShim.exports,
  require,
  moduleShim,
  sourcePath,
  path.dirname(sourcePath),
);

const {
  UNKNOWN_MEETING_DATE_KEY,
  getLocalDateKey,
  isToday,
  isYesterday,
  formatMeetingDateSectionTitle,
  groupMeetingsByDate,
} = moduleShim.exports;

function localIso(year, month, day, hour = 0, minute = 0) {
  return new Date(year, month - 1, day, hour, minute, 0).toISOString();
}

function meeting(id, startAt, createdAt = startAt) {
  return {
    id,
    title: id,
    status: 'completed',
    start_at: startAt,
    end_at: null,
    location: null,
    created_at: createdAt,
    updated_at: createdAt || new Date().toISOString(),
  };
}

const now = new Date(2026, 6, 30, 10, 0, 0);
const sections = groupMeetingsByDate(
  [
    meeting('old', localIso(2025, 12, 31, 15, 0)),
    meeting('today-early', localIso(2026, 7, 30, 9, 0)),
    meeting('invalid', 'not-a-date', 'also-invalid'),
    meeting('yesterday', localIso(2026, 7, 29, 18, 0)),
    meeting('earlier', localIso(2026, 7, 28, 11, 0)),
    meeting('today-late', localIso(2026, 7, 30, 11, 0)),
    meeting('created-fallback', null, localIso(2026, 7, 29, 20, 0)),
  ],
  now,
);

assert.equal(getLocalDateKey(new Date(2026, 6, 30, 9, 15)), '2026-07-30');
assert.equal(isToday(new Date(2026, 6, 30, 0, 1), now), true);
assert.equal(isYesterday(new Date(2026, 6, 29, 23, 59), now), true);

assert.equal(sections.length, 5, 'same-day meetings should share one section and invalid dates should share unknown');
assert.deepEqual(
  sections.map((section) => section.key),
  ['2026-07-30', '2026-07-29', '2026-07-28', '2025-12-31', UNKNOWN_MEETING_DATE_KEY],
  'date sections should sort descending with unknown last',
);
assert.deepEqual(sections[0].data.map((item) => item.id), ['today-late', 'today-early'], 'meetings inside a date should sort descending');
assert.deepEqual(sections[1].data.map((item) => item.id), ['created-fallback', 'yesterday'], 'created_at should be used when start_at is missing');

assert.equal(formatMeetingDateSectionTitle(new Date(2026, 6, 30), now), '今天 7月30日 周四');
assert.equal(formatMeetingDateSectionTitle(new Date(2026, 6, 29), now), '昨天 7月29日 周三');
assert.equal(formatMeetingDateSectionTitle(new Date(2026, 6, 28), now), '7月28日 周二');
assert.equal(formatMeetingDateSectionTitle(new Date(2025, 11, 31), now), '2025年12月31日 周三');
assert.equal(formatMeetingDateSectionTitle(null, now), '时间未知');

const utcPreviousDayIso = new Date(2026, 6, 30, 0, 30, 0).toISOString();
assert.equal(
  getLocalDateKey(utcPreviousDayIso),
  getLocalDateKey(new Date(2026, 6, 30, 0, 30, 0)),
  'local key should use local date fields after parsing instead of truncating UTC text',
);

const beforeMidnight = new Date(2026, 6, 30, 23, 59, 0);
const afterMidnight = new Date(2026, 6, 31, 0, 0, 1);
assert.equal(formatMeetingDateSectionTitle(new Date(2026, 6, 30, 12, 0), beforeMidnight), '今天 7月30日 周四');
assert.equal(formatMeetingDateSectionTitle(new Date(2026, 6, 30, 12, 0), afterMidnight), '昨天 7月30日 周四');

assert.deepEqual(groupMeetingsByDate([], now), [], 'empty meeting list should produce no sections');

console.log('meeting date section tests passed');
