import re

from rest_framework_simplejwt.tokens import RefreshToken


EMAIL_RE = re.compile(r"^loadtest-(?P<role>[a-z]+)-(?P<index>\d{4})@")


def account_role_index(account):
    match = EMAIL_RE.match(account.penduduk.email or "")
    if match:
        return match.group("role"), int(match.group("index"))
    return account.get_peran_display().lower(), 1


def build_account_manifest(accounts):
    rows = []
    tokens = {}
    for account in accounts:
        if not account.is_active:
            continue
        role, index = account_role_index(account)
        refresh = RefreshToken.for_user(account)
        access_token = str(refresh.access_token)
        tokens[account.nik] = access_token
        rows.append(
            {
                "id": account.pk,
                "role": role,
                "index": index,
                "nik": account.nik,
                "email": account.penduduk.email,
                "access": access_token,
                "refresh": str(refresh),
            }
        )

    return {
        "token_type": "Bearer",
        "account_count": len(rows),
        "accounts": rows,
        "tokens": tokens,
    }
