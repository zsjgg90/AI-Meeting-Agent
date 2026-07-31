import Svg, { Circle, Line, Path, Polyline, Rect } from 'react-native-svg';

export type LucideIconName =
  | 'book-open'
  | 'bell'
  | 'calendar-days'
  | 'camera'
  | 'chevron-down'
  | 'chevron-left'
  | 'chevron-right'
  | 'circle-check-big'
  | 'circle-help'
  | 'clock-3'
  | 'file-text'
  | 'filter'
  | 'flag'
  | 'git-branch'
  | 'house'
  | 'image-plus'
  | 'info'
  | 'log-out'
  | 'mail'
  | 'message-square'
  | 'mic'
  | 'more-horizontal'
  | 'pause'
  | 'pencil-line'
  | 'phone'
  | 'play'
  | 'plus'
  | 'rotate-ccw'
  | 'search'
  | 'send'
  | 'settings'
  | 'share-2'
  | 'sparkles'
  | 'square'
  | 'square-check-big'
  | 'triangle-alert'
  | 'user'
  | 'user-round'
  | 'video'
  | 'x';

type Props = {
  name: LucideIconName;
  color?: string;
  size?: number;
  strokeWidth?: number;
};

export function LucideIcon({ name, color = '#111827', size = 24, strokeWidth = 2 }: Props) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      {renderIcon(name, color, strokeWidth)}
    </Svg>
  );
}

function renderIcon(name: LucideIconName, color: string, strokeWidth: number) {
  const common = {
    stroke: color,
    strokeWidth,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };

  switch (name) {
    case 'bell':
      return (
        <>
          <Path {...common} d="M10.3 21a2 2 0 0 0 3.4 0" />
          <Path {...common} d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
        </>
      );
    case 'book-open':
      return (
        <>
          <Path {...common} d="M12 7v14" />
          <Path {...common} d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
        </>
      );
    case 'calendar-days':
      return (
        <>
          <Path {...common} d="M8 2v4" />
          <Path {...common} d="M16 2v4" />
          <Rect {...common} x="3" y="4" width="18" height="18" rx="2" />
          <Path {...common} d="M3 10h18" />
          <Path {...common} d="M8 14h.01" />
          <Path {...common} d="M12 14h.01" />
          <Path {...common} d="M16 14h.01" />
          <Path {...common} d="M8 18h.01" />
          <Path {...common} d="M12 18h.01" />
          <Path {...common} d="M16 18h.01" />
        </>
      );
    case 'camera':
      return (
        <>
          <Path {...common} d="M14.5 4h-5L8 6H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3z" />
          <Circle {...common} cx="12" cy="13" r="3" />
        </>
      );
    case 'chevron-left':
      return <Polyline {...common} points="15 18 9 12 15 6" />;
    case 'chevron-down':
      return <Polyline {...common} points="6 9 12 15 18 9" />;
    case 'chevron-right':
      return <Polyline {...common} points="9 18 15 12 9 6" />;
    case 'circle-check-big':
      return (
        <>
          <Circle {...common} cx="12" cy="12" r="10" />
          <Path {...common} d="m9 12 2 2 4-4" />
        </>
      );
    case 'circle-help':
      return (
        <>
          <Circle {...common} cx="12" cy="12" r="10" />
          <Path {...common} d="M9.1 9a3 3 0 1 1 5.8 1c-.4.8-1.2 1.2-1.8 1.7-.7.5-1.1 1-1.1 2" />
          <Path {...common} d="M12 17h.01" />
        </>
      );
    case 'clock-3':
      return (
        <>
          <Circle {...common} cx="12" cy="12" r="10" />
          <Path {...common} d="M12 6v6h4" />
        </>
      );
    case 'file-text':
      return (
        <>
          <Path {...common} d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <Path {...common} d="M14 2v6h6" />
          <Path {...common} d="M16 13H8" />
          <Path {...common} d="M16 17H8" />
          <Path {...common} d="M10 9H8" />
        </>
      );
    case 'filter':
      return (
        <>
          <Path {...common} d="M22 3H2l8 9.5V20l4 2v-9.5z" />
          <Path {...common} d="M18 14h-4" />
          <Path {...common} d="M18 18h-7" />
        </>
      );
    case 'flag':
      return (
        <>
          <Path {...common} d="M4 22V4" />
          <Path {...common} d="M4 4h11l-1 4 1 4H4" />
        </>
      );
    case 'git-branch':
      return (
        <>
          <Line {...common} x1="6" y1="3" x2="6" y2="15" />
          <Circle {...common} cx="18" cy="6" r="3" />
          <Circle {...common} cx="6" cy="18" r="3" />
          <Path {...common} d="M18 9a9 9 0 0 1-9 9" />
        </>
      );
    case 'house':
      return (
        <>
          <Path {...common} d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" />
          <Path {...common} d="M3 10a2 2 0 0 1 .7-1.5l7-6a2 2 0 0 1 2.6 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </>
      );
    case 'image-plus':
      return (
        <>
          <Rect {...common} x="3" y="3" width="18" height="18" rx="2" />
          <Path {...common} d="M8 11.5 11 9l4 5 2-2 2 3" />
          <Path {...common} d="M14 6h4" />
          <Path {...common} d="M16 4v4" />
          <Circle {...common} cx="8" cy="8" r="1" />
        </>
      );
    case 'info':
      return (
        <>
          <Circle {...common} cx="12" cy="12" r="10" />
          <Path {...common} d="M12 16v-4" />
          <Path {...common} d="M12 8h.01" />
        </>
      );
    case 'log-out':
      return (
        <>
          <Path {...common} d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <Path {...common} d="M16 17l5-5-5-5" />
          <Path {...common} d="M21 12H9" />
        </>
      );
    case 'mail':
      return (
        <>
          <Rect {...common} x="3" y="5" width="18" height="14" rx="2" />
          <Path {...common} d="m3 7 9 6 9-6" />
        </>
      );
    case 'message-square':
      return (
        <>
          <Path {...common} d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          <Path {...common} d="M8 9h8" />
          <Path {...common} d="M8 13h5" />
        </>
      );
    case 'mic':
      return (
        <>
          <Path {...common} d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
          <Path {...common} d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <Line {...common} x1="12" y1="19" x2="12" y2="22" />
        </>
      );
    case 'more-horizontal':
      return (
        <>
          <Circle {...common} cx="12" cy="12" r="1" />
          <Circle {...common} cx="19" cy="12" r="1" />
          <Circle {...common} cx="5" cy="12" r="1" />
        </>
      );
    case 'pause':
      return (
        <>
          <Path {...common} d="M8 5v14" />
          <Path {...common} d="M16 5v14" />
        </>
      );
    case 'pencil-line':
      return (
        <>
          <Path {...common} d="M12 20h9" />
          <Path {...common} d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
        </>
      );
    case 'phone':
      return (
        <>
          <Path {...common} d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.7.6 2.5a2 2 0 0 1-.5 2.1L8 9.5a16 16 0 0 0 6.5 6.5l1.2-1.2a2 2 0 0 1 2.1-.5c.8.3 1.6.5 2.5.6a2 2 0 0 1 1.7 2z" />
        </>
      );
    case 'play':
      return <Path {...common} d="M6 3l15 9-15 9z" />;
    case 'plus':
      return (
        <>
          <Path {...common} d="M5 12h14" />
          <Path {...common} d="M12 5v14" />
        </>
      );
    case 'rotate-ccw':
      return (
        <>
          <Path {...common} d="M3 12a9 9 0 1 0 3-6.7L3 8" />
          <Path {...common} d="M3 3v5h5" />
        </>
      );
    case 'search':
      return (
        <>
          <Circle {...common} cx="11" cy="11" r="8" />
          <Path {...common} d="m21 21-4.3-4.3" />
        </>
      );
    case 'send':
      return (
        <>
          <Path {...common} d="m22 2-7 20-4-9-9-4z" />
          <Path {...common} d="M22 2 11 13" />
        </>
      );
    case 'settings':
      return (
        <>
          <Path {...common} d="M12.2 2h-.4a2 2 0 0 0-2 1.7l-.2 1.1a7.6 7.6 0 0 0-1.2.7l-1-.4a2 2 0 0 0-2.4.8l-.2.4a2 2 0 0 0 .3 2.5l.8.7a7.5 7.5 0 0 0 0 1.4l-.8.7a2 2 0 0 0-.3 2.5l.2.4a2 2 0 0 0 2.4.8l1-.4a7.6 7.6 0 0 0 1.2.7l.2 1.1a2 2 0 0 0 2 1.7h.4a2 2 0 0 0 2-1.7l.2-1.1a7.6 7.6 0 0 0 1.2-.7l1 .4a2 2 0 0 0 2.4-.8l.2-.4a2 2 0 0 0-.3-2.5l-.8-.7a7.5 7.5 0 0 0 0-1.4l.8-.7a2 2 0 0 0 .3-2.5l-.2-.4a2 2 0 0 0-2.4-.8l-1 .4a7.6 7.6 0 0 0-1.2-.7l-.2-1.1a2 2 0 0 0-2-1.7Z" />
          <Circle {...common} cx="12" cy="12" r="3" />
        </>
      );
    case 'share-2':
      return (
        <>
          <Circle {...common} cx="18" cy="5" r="3" />
          <Circle {...common} cx="6" cy="12" r="3" />
          <Circle {...common} cx="18" cy="19" r="3" />
          <Path {...common} d="m8.6 13.5 6.8 4" />
          <Path {...common} d="m15.4 6.5-6.8 4" />
        </>
      );
    case 'sparkles':
      return (
        <>
          <Path {...common} d="M12 3 9.7 9.7 3 12l6.7 2.3L12 21l2.3-6.7L21 12l-6.7-2.3z" />
          <Path {...common} d="M5 3v4" />
          <Path {...common} d="M3 5h4" />
          <Path {...common} d="M19 17v4" />
          <Path {...common} d="M17 19h4" />
        </>
      );
    case 'square':
      return <Rect {...common} x="5" y="5" width="14" height="14" rx="2" />;
    case 'square-check-big':
      return (
        <>
          <Rect {...common} x="3" y="3" width="18" height="18" rx="2" />
          <Path {...common} d="m9 12 2 2 4-5" />
        </>
      );
    case 'triangle-alert':
      return (
        <>
          <Path {...common} d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z" />
          <Path {...common} d="M12 9v4" />
          <Path {...common} d="M12 17h.01" />
        </>
      );
    case 'user':
      return (
        <>
          <Path {...common} d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
          <Circle {...common} cx="12" cy="7" r="4" />
        </>
      );
    case 'user-round':
      return (
        <>
          <Circle {...common} cx="12" cy="8" r="5" />
          <Path {...common} d="M20 21a8 8 0 0 0-16 0" />
        </>
      );
    case 'video':
      return (
        <>
          <Rect {...common} x="3" y="6" width="12" height="12" rx="2" />
          <Path {...common} d="m15 10 5-3v10l-5-3z" />
        </>
      );
    case 'x':
      return (
        <>
          <Path {...common} d="M18 6 6 18" />
          <Path {...common} d="m6 6 12 12" />
        </>
      );
    default:
      return null;
  }
}
