export function stripLeadingListMarker(value: string): string {
  return value.replace(/^\s*\d+\s*[.、]\s*/, '').trim();
}

export function splitNumberedListText(value: string): string[] {
  const text = value.trim();
  if (!text) return [];

  const normalized = text.replace(/\r\n?/g, '\n');
  const hasNumberMarkers = /(?:^|[\n；;]\s*)\d+\s*[.、]\s*/.test(normalized);
  const parts = hasNumberMarkers
    ? normalized.split(/(?:^|[\n；;]\s*)\d+\s*[.、]\s*/g)
    : normalized.split(/[\n；;]+/g);

  return parts.map(stripLeadingListMarker).map((item) => item.trim()).filter(Boolean);
}

export function normalizeNumberedListItems(input: unknown): string[] {
  if (Array.isArray(input)) {
    return input
      .flatMap((item) => splitNumberedListText(String(item ?? '')))
      .map(stripLeadingListMarker)
      .filter(Boolean);
  }

  if (input === null || input === undefined) return [];
  return splitNumberedListText(String(input));
}
