-- Profile photos of the person the pillow watches, in Supabase Storage. One folder per resident
-- (`<resident_id>/photo.jpg`), so each household's photo stays its own. Anyone may read a photo
-- by its link (the app shows it before any account check); only that resident's owner, signed in,
-- may upload, replace or remove it.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('resident-photos', 'resident-photos', true, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do nothing;

-- True when the signed-in user owns the resident whose folder `object_name` sits in.
create or replace function public.owns_resident_folder(object_name text) returns boolean
language sql stable security definer set search_path = public as $$
    select exists (
        select 1
        from resident_contacts rc
        join contacts c on c.id = rc.contact_id
        where c.user_id = (select auth.uid())
          and rc.role = 'owner'
          and rc.resident_id::text = (storage.foldername(object_name))[1]
    );
$$;

create policy resident_photo_insert on storage.objects for insert to authenticated
    with check (bucket_id = 'resident-photos' and public.owns_resident_folder(name));

create policy resident_photo_update on storage.objects for update to authenticated
    using (bucket_id = 'resident-photos' and public.owns_resident_folder(name))
    with check (bucket_id = 'resident-photos' and public.owns_resident_folder(name));

create policy resident_photo_delete on storage.objects for delete to authenticated
    using (bucket_id = 'resident-photos' and public.owns_resident_folder(name));

-- Listing the folder tells the app when the photo last changed, so it can skip a cached copy.
create policy resident_photo_select on storage.objects for select to anon, authenticated
    using (bucket_id = 'resident-photos');
