/**
 * The voice the pillow speaks to her in (Cartesia, through the backend), under
 * `/residents/{residentId}/voice`: the voices to choose from with a ready-made sample of each, a
 * spoken preview of any line, choosing one and how it speaks (owner only), family voices copied
 * from a short recording, accent copies of a voice, and words the pillow says her way (anyone in
 * the care circle).
 */

import { File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';

import { api, ApiError, authedFetch } from '@/services/api';

export type Voice = {
  id: string;
  name: string;
  description: string | null;
  /** 'clone' is a family voice copied from a recording; 'accent' a copy of a voice with another accent. */
  source: 'stock' | 'clone' | 'accent';
  created_by_name: string | null;
  created_at: string | null;
  /** Cartesia's accent id: a clone's own accent, or the accent of a copy. */
  accent?: string | null;
  /** The voice an accent copy was made from. */
  base_voice_id?: string | null;
  /** Where its sample already sits, ready to play; null until it has been made once. */
  sample_url?: string | null;
};

/** How the pillow speaks: Cartesia's speed (0.6 to 1.5), volume (0.5 to 2) and tone. */
export type VoiceStyle = { speed: number; volume: number; emotion: string };

export type VoiceChoice = {
  current: string;
  style: VoiceStyle;
  /** The tones the owner may pick. */
  emotions: string[];
  voices: Voice[];
  /**
   * True when the backend only has the older voice list: choosing works (through the pillow's
   * preferences), hearing a voice first and copying one don't yet.
   */
  legacy: boolean;
};

/** An accent a voice can be copied into ("British"). */
export type Accent = { id: string; name: string; locale: string };

/** A word the pillow says her way. */
export type Pronunciation = {
  id: string;
  word: string;
  sounds_like: string;
  created_by_name: string | null;
  created_at: string;
};

/** A recording to copy a voice from: just made with the mic, or picked from the phone's files. */
export type Clip = { uri: string; name: string; mimeType: string };

/** Longest preview line the backend reads out. */
export const PREVIEW_MAX = 200;
/** Longest name for a family voice. */
export const VOICE_NAME_MAX = 40;
/** How long a recording must be for a good copy, in seconds; longer keeps the accent better. */
export const CLIP_MIN_S = 10;
export const CLIP_MAX_S = 60;
/** Longest word, and longest "sounds like" spelling, the backend keeps. */
export const WORD_MAX = 60;
export const SOUNDS_LIKE_MAX = 120;
/** How the pillow spoke before anyone changed it. */
export const DEFAULT_STYLE: VoiceStyle = { speed: 0.85, volume: 1, emotion: 'calm' };

const base = (residentId: string) => `/residents/${residentId}/voice`;

/**
 * The voices for her, the one in use and how it speaks. Falls back to the older `/voices` list
 * (and the voice saved on her record) while the voice endpoints aren't live yet.
 */
export async function readVoices(residentId: string, savedVoiceId: string | undefined): Promise<VoiceChoice> {
  try {
    const choice = await api<Omit<VoiceChoice, 'legacy'>>(base(residentId));
    return { ...choice, legacy: false };
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 404)) throw e;
    const old = await api<{ id: string; name: string; description: string }[]>('/voices');
    return {
      current: savedVoiceId ?? '',
      style: DEFAULT_STYLE,
      emotions: [],
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

/** Saves how the pillow speaks to her. Owner only (403 for contacts). */
export async function saveStyle(residentId: string, style: VoiceStyle): Promise<VoiceStyle> {
  return api<VoiceStyle>(`${base(residentId)}/style`, { method: 'PUT', body: style });
}

// Sample links already known this session, so Play never has to ask twice.
const samples = new Map<string, string>();

/**
 * Where to play `voice` saying the sample line: the link the voice list gave, or one the backend
 * makes the first time anyone plays it (after that it is stored and instant for everyone).
 */
export async function sampleUri(residentId: string, voice: Voice): Promise<string> {
  const known = voice.sample_url ?? samples.get(voice.id);
  if (known) return known;
  const { url } = await api<{ url: string }>(`${base(residentId)}/samples/${encodeURIComponent(voice.id)}`);
  samples.set(voice.id, url);
  return url;
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
 * The pillow saying a line in `voiceId`, ready to play, with her words said her way. Without
 * `text` the backend uses its own warm line with her name; without `style` it speaks as she hears it.
 */
export async function previewVoice(
  residentId: string,
  voiceId: string,
  text?: string,
  style?: VoiceStyle,
): Promise<string> {
  const words = text?.trim().slice(0, PREVIEW_MAX) || undefined;
  const key = `${residentId}|${voiceId}|${words ?? ''}|${style ? JSON.stringify(style) : ''}`;
  const cached = previews.get(key);
  if (cached) return cached;
  const response = await authedFetch(`${base(residentId)}/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'audio/mpeg, audio/wav' },
    body: JSON.stringify({ voice_id: voiceId, ...(words ? { text: words } : {}), ...(style ? { style } : {}) }),
  });
  const uri = await playableUri(response);
  previews.set(key, uri);
  return uri;
}

/** Forgets fetched previews, so lines are spoken again with a changed dictionary or style. */
export function forgetPreviews() {
  previews.clear();
}

/**
 * Copies a voice from `clip` and returns it. The caller has the speaker's agreement (consent is
 * required). `accent` is the speaker's own accent, when known.
 */
export async function cloneVoice(residentId: string, clip: Clip, name: string, accent?: string): Promise<Voice> {
  const form = new FormData();
  if (Platform.OS === 'web') {
    form.append('clip', await (await fetch(clip.uri)).blob(), clip.name);
  } else {
    // React Native's FormData reads the file from its uri.
    form.append('clip', { uri: clip.uri, name: clip.name, type: clip.mimeType } as unknown as Blob);
  }
  form.append('name', name.trim().slice(0, VOICE_NAME_MAX));
  form.append('consent', 'true');
  if (accent) form.append('accent', accent);
  const response = await authedFetch(`${base(residentId)}/clones`, { method: 'POST', body: form });
  return (await response.json()) as Voice;
}

/** Removes a family voice or an accent copy. Its maker or the owner only. */
export async function deleteClone(residentId: string, voiceId: string): Promise<void> {
  await api(`${base(residentId)}/clones/${encodeURIComponent(voiceId)}`, { method: 'DELETE' });
}

/** The accents a voice can be copied into, for her language. */
export async function readAccents(residentId: string): Promise<Accent[]> {
  return api<Accent[]>(`${base(residentId)}/accents`);
}

/** A copy of `voiceId` speaking with `accent`, with its sample ready; one she has already is returned. */
export async function copyWithAccent(residentId: string, voiceId: string, accent: string): Promise<Voice> {
  return api<Voice>(`${base(residentId)}/accents`, { method: 'POST', body: { voice_id: voiceId, accent } });
}

/** The words the pillow says her way. */
export async function readPronunciations(residentId: string): Promise<Pronunciation[]> {
  return api<Pronunciation[]>(`${base(residentId)}/pronunciations`);
}

/** Teaches the pillow a word. 409 when she already has that word. */
export async function addPronunciation(residentId: string, word: string, soundsLike: string): Promise<Pronunciation> {
  return api<Pronunciation>(`${base(residentId)}/pronunciations`, {
    method: 'POST',
    body: { word: word.trim(), sounds_like: soundsLike.trim() },
  });
}

/** Forgets a word. Whoever added it, or the owner. */
export async function removePronunciation(residentId: string, id: string): Promise<void> {
  await api(`${base(residentId)}/pronunciations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** A recording's file name and type from its uri (.wav on iPhones, .m4a on Android, .webm on the web). */
export function clipFromRecording(uri: string): Clip {
  const ext = uri.split('?')[0].split('.').pop()?.toLowerCase();
  if (Platform.OS === 'web' || !ext || ext.length > 4) return { uri, name: 'recording.webm', mimeType: 'audio/webm' };
  const types: Record<string, string> = { m4a: 'audio/mp4', mp4: 'audio/mp4', wav: 'audio/wav', caf: 'audio/x-caf' };
  return { uri, name: `recording.${ext}`, mimeType: types[ext] ?? `audio/${ext}` };
}
