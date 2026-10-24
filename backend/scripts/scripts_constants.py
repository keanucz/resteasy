"""Constants for the admin scripts."""

# A plain name passed to create_login becomes <name>@<domain>, and that full address is what the
# person types into the app's email field. `.test` is a reserved TLD, so these addresses can never
# receive mail.
USERNAME_EMAIL_DOMAIN = "pillow.test"

# Bytes of randomness in a generated password (token_urlsafe turns 18 bytes into 24 characters)
GENERATED_PASSWORD_BYTES = 18
