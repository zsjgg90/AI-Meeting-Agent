import type { Meeting } from '../api';

export const UNKNOWN_MEETING_DATE_KEY = 'unknown';

export type MeetingDateSection = {
  key: string;
  title: string;
  timestamp: number;
  data: Meeting[];
};

export function parseMeetingDateValue(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function meetingTimelineDate(meeting: Pick<Meeting, 'start_at' | 'created_at'>): Date | null {
  return parseMeetingDateValue(meeting.start_at) || parseMeetingDateValue(meeting.created_at);
}

export function getLocalDateKey(value: Date | string | null | undefined): string | null {
  const date = value instanceof Date ? value : parseMeetingDateValue(value);
  if (!date || Number.isNaN(date.getTime())) return null;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function startOfLocalDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function localDayDiff(left: Date, right: Date): number {
  return Math.round((startOfLocalDay(left).getTime() - startOfLocalDay(right).getTime()) / 86400000);
}

export function isToday(value: Date, now = new Date()): boolean {
  return localDayDiff(now, value) === 0;
}

export function isYesterday(value: Date, now = new Date()): boolean {
  return localDayDiff(now, value) === 1;
}

export function formatMeetingDateSectionTitle(value: Date | null, now = new Date()): string {
  if (!value || Number.isNaN(value.getTime())) return '时间未知';

  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const monthDay = `${value.getMonth() + 1}月${value.getDate()}日`;
  const weekday = weekdays[value.getDay()];

  if (isToday(value, now)) return `今天 ${monthDay} ${weekday}`;
  if (isYesterday(value, now)) return `昨天 ${monthDay} ${weekday}`;
  if (value.getFullYear() === now.getFullYear()) return `${monthDay} ${weekday}`;
  return `${value.getFullYear()}年${monthDay} ${weekday}`;
}

export function compareMeetingsByTimelineDesc(left: Meeting, right: Meeting): number {
  const leftTime = meetingTimelineDate(left)?.getTime() ?? 0;
  const rightTime = meetingTimelineDate(right)?.getTime() ?? 0;
  return rightTime - leftTime;
}

export function compareMeetingDateSectionsDesc(left: MeetingDateSection, right: MeetingDateSection): number {
  if (left.key === UNKNOWN_MEETING_DATE_KEY && right.key !== UNKNOWN_MEETING_DATE_KEY) return 1;
  if (right.key === UNKNOWN_MEETING_DATE_KEY && left.key !== UNKNOWN_MEETING_DATE_KEY) return -1;
  return right.timestamp - left.timestamp;
}

export function groupMeetingsByDate(meetings: Meeting[], now = new Date()): MeetingDateSection[] {
  const groups = new Map<string, { date: Date | null; meetings: Meeting[]; timestamp: number }>();

  meetings.forEach((meeting) => {
    const date = meetingTimelineDate(meeting);
    const key = getLocalDateKey(date) || UNKNOWN_MEETING_DATE_KEY;
    const existing = groups.get(key);
    if (existing) {
      existing.meetings.push(meeting);
      return;
    }

    const localDay = date ? startOfLocalDay(date) : null;
    groups.set(key, {
      date,
      meetings: [meeting],
      timestamp: localDay?.getTime() ?? Number.NEGATIVE_INFINITY,
    });
  });

  return Array.from(groups.entries())
    .map(([key, group]) => ({
      key,
      title: formatMeetingDateSectionTitle(group.date, now),
      timestamp: group.timestamp,
      data: [...group.meetings].sort(compareMeetingsByTimelineDesc),
    }))
    .sort(compareMeetingDateSectionsDesc);
}
