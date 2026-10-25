-- The language the family app's voice previews speak in (Settings > Voice). Only the previews
-- follow it; the pillow and the alert calls keep residents.language.
alter table residents
    add column preview_language text not null default 'en'
        check (preview_language in ('en', 'es', 'fr', 'de', 'it', 'pt', 'pl', 'zh', 'ja', 'hi'));
