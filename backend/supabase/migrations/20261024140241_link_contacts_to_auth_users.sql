-- Link a contact (carer) to the Supabase Auth account they log in to the app with.
-- Nullable: carers who only get texts never need an account. Deleting the account keeps the contact.

alter table contacts
    add column user_id uuid unique references auth.users (id) on delete set null;
