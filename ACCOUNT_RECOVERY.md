Account signup and recovery
===========================
Username, email and Indian mobile number identify an account. Personal names do not: different people may share a name.

The website and mobile API now share trimmed, case-insensitive username/email checks and canonical mobile-number checks, including existing +91 and formatted numbers. Duplicate requests never overwrite an existing account or send a new verification code. They show sign-in, username-recovery and password-reset options. Integrity conflicts roll back the attempted registration.

Migration accounts.0015 adds unique expression indexes on the built-in auth_user table (normalized username/email) and accounts_userprofile (normalized mobile). These complement Django form validation, protecting simultaneous requests and writes through other entry points. Blank emails/phones remain allowed for existing internal accounts. Existing accounts are not merged or deleted. The migration fails safely if existing duplicate groups require manual review. Run it with deployment before accepting new registrations.

Forgot username is available at /accounts/username/recover/ and /api/v1/auth/username/recover/. It sends a reminder only to an active account's stored email, without returning its username or changing its password. Unknown and disabled accounts receive the same message. Email/IP limits apply across the website and API. Existing password reset remains OTP-based.

Verified: account/API regression suite, duplicate-identifier database backstops, formatted phones, recovery privacy and cooldown, profile-edit conflicts, mobile typechecking and mobile tests.
