/**
 * The voice the pillow speaks to her in (Cartesia, through the backend), under
 * `/residents/{residentId}/voice`: the voices to choose from, a spoken preview of any of them,
 * choosing one (owner only), and family voices copied from a short recording (anyone in the care circle).
 */

import { File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';

import { api, ApiError, authedFetch } from '@/services/api';

export type Voice = {
  id: string;
  name: string;
  description: string | null;
  /** 'clone' is a family voice copied from a recording. */
  source: 'stock' | 'clone';
  created_by_name: string | null;
  created_at: string | null;
};

export type VoiceChoice = {
  current: string;
  voices: Voice[];
  /**
   * True when the backend only has the older voice list: choosing works (through the pillow's
   * preferences), hearing a voice first and copying one don't yet.
   */
  legacy: boolean;
};

/** A recording to copy a voice from: just made with the mic, or picked from the phone's files. */
export type Clip = { uri: string; name: string; mimeType: string };

/** Longest preview line the backend reads out. */
export const PREVIEW_MAX = 200;
/** Longest name for a family voice. */
export const VOICE_NAME_MAX = 40;
/** How long a recording must be for a good copy, in seconds. */
export const CLIP_MIN_S = 10;
export const CLIP_MAX_S = 30;

const base = (residentId: string) => `/residents/${residentId}/voice`;

/**
 * The voices for her and the one in use. Falls back to the older `/voices` list (and the voice
 * saved on her record) while the voice endpoints aren't live yet.
 */
export async function readVoices(residentId: string, savedVoiceId: string | undefined): Promise<VoiceChoice> {
  try {
    const choice = await api<{ current: string; voices: Voice[] }>(base(residentId));
    return { ...choice, legacy: false };
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 404)) throw e;
    const old = await api<{ id: string; name: string; description: string }[]>('/voices');
    return {
      current: savedVoiceId ?? '',
      voices: old.map((v) => ({ ...v, source: 'stock', created_by_name: null, created_at: null })),
      legacy: true,
    };
  }
}

/** Makes `voiceId` the voice she hears. Owner only (403 for contacts). */
export async function chooseVoice(residentId: string, voiceId: string, legacyPillowId?: string): Promise<string> {
  if (legacyPillowId) {
    await api(`/pillows/${legacyPillowId}/preferences`, { method: 'PATCH', body: { voice_id: voiceId } });
    return voiceId;
  }
  const { current } = await api<{ current: string }>(base(residentId), { method: 'PUT', body: { voice_id: voiceId } });
  return current;
}

// Previews already fetched this session, so playing one again doesn't ask Cartesia twice.
const previews = new Map<string, string>();
let previewCount = 0;

/** Something the audio player can open: a blob link on the web, a file in the cache on a phone. */
async function playableUri(response: Response): Promise<string> {
  if (Platform.OS === 'web') return URL.createObjectURL(await response.blob());
  const wav = (response.headers.get('content-type') ?? '').includes('wav');
  const file = new File(Paths.cache, `voice-preview-${++previewCount}.${wav ? 'wav' : 'mp3'}`);
  await file.write(new Uint8Array(await response.arrayBuffer()));
  return file.uri;
}

/**
 * The pillow saying a line in `voiceId`, ready to play. Without `text` the backend uses its own
 * warm line with her name.
 */
export async function previewVoice(residentId: string, voiceId: string, text?: string): Promise<string> {
  const words = text?.trim().slice(0, PREVIEW_MAX) || undefined;
  const key = `${residentId}|${voiceId}|${words ?? ''}`;
  const cached = previews.get(key);
  if (cached) return cached;
  const response = await authedFetch(`${base(residentId)}/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'audio/mpeg, audio/wav' },
    body: JSON.stringify({ voice_id: voiceId, ...(words ? { text: words } : {}) }),
  });
  const uri = await playableUri(response);
  previews.set(key, uri);
  return uri;
}

/** Copies a voice from `clip` and returns it. The caller has the speaker's agreement (consent is required). */
export async function cloneVoice(residentId: string, clip: Clip, name: string): Promise<Voice> {
  const form = new FormData();
  if (Platform.OS === 'web') {
    form.append('clip', await (await fetch(clip.uri)).blob(), clip.name);
  } else {
    // React Native's FormData reads the file from its uri.
    form.append('clip', { uri: clip.uri, name: clip.name, type: clip.mimeType } as unknown as Blob);
  }
  form.append('name', name.trim().slice(0, VOICE_NAME_MAX));
  form.append('consent', 'true');
  const response = await authedFetch(`${base(residentId)}/clones`, { method: 'POST', body: form });
  return (await response.json()) as Voice;
}

/** Removes a family voice. Its maker or the owner only. */
export async function deleteClone(residentId: string, voiceId: string): Promise<void> {
  await api(`${base(residentId)}/clones/${encodeURIComponent(voiceId)}`, { method: 'DELETE' });
}

/** A recording's file name and type from its uri (.wav on iPhones, .m4a on Android, .webm on the web). */
export function clipFromRecording(uri: string): Clip {
  const ext = uri.split('?')[0].split('.').pop()?.toLowerCase();
  if (Platform.OS === 'web' || !ext || ext.length > 4) return { uri, name: 'recording.webm', mimeType: 'audio/webm' };
  const types: Record<string, string> = { m4a: 'audio/mp4', mp4: 'audio/mp4', wav: 'audio/wav', caf: 'audio/x-caf' };
  return { uri, name: `recording.${ext}`, mimeType: types[ext] ?? `audio/${ext}` };
}
