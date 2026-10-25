/**
 * The resident's profile photo, in Supabase Storage: one per resident at `<resident_id>/photo.jpg`
 * in the public `resident-photos` bucket. Anyone in the resident's care circle may upload (a storage policy).
 */

import * as ImagePicker from 'expo-image-picker';

import { supabase } from '@/services/supabase/client';

export const PHOTO_BUCKET = 'resident-photos';
const PHOTO_FILE = 'photo.jpg';
/** Small enough to load fast in the sky's photo ring, big enough to stay sharp at 3x. */
const PHOTO_QUALITY = 0.7;

const pathFor = (residentId: string) => `${residentId}/${PHOTO_FILE}`;

/** The photo's public link with its version, or null when there is no photo yet. */
export async function photoUrl(residentId: string): Promise<string | null> {
  const { data, error } = await supabase.storage.from(PHOTO_BUCKET).list(residentId, { search: PHOTO_FILE, limit: 1 });
  const file = data?.find((f) => f.name === PHOTO_FILE);
  if (error || !file) return null;
  const version = Date.parse(file.updated_at ?? file.created_at ?? '') || 0;
  // The version busts caches, so a new photo shows straight away.
  return `${supabase.storage.from(PHOTO_BUCKET).getPublicUrl(pathFor(residentId)).data.publicUrl}?v=${version}`;
}

/**
 * Lets the user pick a photo (cropped square), uploads it in place of the old one and returns its
 * new link. Null if they cancelled. Throws a sentence to show when the upload fails.
 */
export async function pickAndUploadPhoto(residentId: string): Promise<string | null> {
  const picked = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    allowsEditing: true,
    aspect: [1, 1],
    quality: PHOTO_QUALITY,
  });
  if (picked.canceled || !picked.assets[0]) return null;
  const asset = picked.assets[0];
  const body = await (await fetch(asset.uri)).arrayBuffer();
  const { error } = await supabase.storage
    .from(PHOTO_BUCKET)
    .upload(pathFor(residentId), body, { contentType: asset.mimeType ?? 'image/jpeg', upsert: true });
  if (error) {
    throw new Error(
      /row-level security|unauthori[sz]ed|403/i.test(error.message)
        ? "You're not in this pillow's care circle, so you can't change the photo."
        : "Couldn't upload the photo. Try again.",
    );
  }
  return photoUrl(residentId);
}
