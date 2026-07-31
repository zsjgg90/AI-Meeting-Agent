import { AudioFile } from '../api';

const playableAudioExtensions = ['.aac', '.m4a', '.mp3', '.mp4', '.mpeg', '.mpga', '.wav', '.webm', '.ogg'];

function audioUploadedAtMillis(audioFile: AudioFile): number {
  const value = new Date(audioFile.uploaded_at).getTime();
  return Number.isNaN(value) ? 0 : value;
}

export function hasPlayableAudioShape(audioFile: AudioFile): boolean {
  const filename = audioFile.filename.toLowerCase();
  const hasAudioMime = Boolean(audioFile.content_type?.toLowerCase().startsWith('audio/'));
  const hasAudioExtension = playableAudioExtensions.some((extension) => filename.endsWith(extension));
  return Boolean(audioFile.id && audioFile.path && audioFile.file_size_bytes > 0 && (hasAudioMime || hasAudioExtension));
}

export function chooseMeetingAudioFile(audioFiles: AudioFile[]): AudioFile | null {
  if (!audioFiles.length) return null;
  const sorted = [...audioFiles].sort((left, right) => audioUploadedAtMillis(right) - audioUploadedAtMillis(left));
  return sorted.find(hasPlayableAudioShape) || sorted.find((audioFile) => Boolean(audioFile.id && audioFile.path)) || null;
}
