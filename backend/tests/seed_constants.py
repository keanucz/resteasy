"""Ids from `supabase/seed.sql` that the live tests rely on."""

# The hypothetical pillow owned by the test user; tests never touch the real `mum` pillow
TEST_PILLOW_ID = "test-pillow"
TEST_RESIDENT_ID = "00000000-0000-0000-0000-000000000011"
TEST_USER_ID = "00000000-0000-0000-0000-000000000012"

# A pillow id that is never registered, for 404 checks
UNKNOWN_PILLOW_ID = "no-such-pillow"
# A contact id with no residents, for empty-list checks
UNKNOWN_CONTACT_ID = "00000000-0000-0000-0000-0000000000ff"
