export type DefaultMeetingTitleKind = 'recording' | 'import';

function twoDigits(value: number): string {
  return String(value).padStart(2, '0');
}

export function defaultMeetingTitle(kind: DefaultMeetingTitleKind, now = new Date()): string {
  const suffix = kind === 'recording' ? '实时录音' : '文件导入';
  const date = [
    now.getFullYear(),
    twoDigits(now.getMonth() + 1),
    twoDigits(now.getDate()),
  ].join('-');
  const time = `${twoDigits(now.getHours())}:${twoDigits(now.getMinutes())}`;
  return `${date} ${time} ${suffix}`;
}
