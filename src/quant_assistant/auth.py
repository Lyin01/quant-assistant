from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.request
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def _get_github_user(access_token: str) -> dict[str, Any] | None:
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _get_github_email(access_token: str) -> str | None:
    req = urllib.request.Request(
        "https://api.github.com/user/emails",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            emails = json.loads(resp.read().decode("utf-8"))
            for item in emails:
                if item.get("primary") and item.get("verified"):
                    return item.get("email")
            for item in emails:
                if item.get("verified"):
                    return item.get("email")
            return emails[0].get("email") if emails else None
    except Exception:
        return None


def _is_allowed(user_info: dict[str, Any]) -> bool:
    allowed = _oauth_config().get("allowed", [])
    if not allowed:
        return True
    checks = [
        user_info.get("email", ""),
        user_info.get("name", ""),
    ]
    return any(str(c) in allowed for c in checks if c)


def _render_login() -> None:
    st.title("Quant Assistant")
    st.info("请先登录以管理个人持仓数据。")

    has_any = False

    github_cfg = _oauth_config().get("github", {})
    if github_cfg.get("client_id"):
        has_any = True
        try:
            from streamlit_oauth import OAuth2Component
        except ImportError:
            st.error("streamlit-oauth 未安装，无法使用 GitHub 登录。")
            return

        github = OAuth2Component(
            client_id=github_cfg["client_id"],
            client_secret=github_cfg["client_secret"],
            authorize_endpoint="https://github.com/login/oauth/authorize",
            token_endpoint="https://github.com/login/oauth/access_token",
        )
        result = github.authorize_button(
            "使用 GitHub 登录",
            github_cfg.get("redirect_uri", "http://localhost:8501"),
            scope="read:user user:email",
            key="github_login",
        )
        if result and "token" in result:
            access_token = result["token"].get("access_token")
            user = _get_github_user(access_token)
            if user:
                email = user.get("email") or _get_github_email(access_token) or ""
                user_info = {
                    "provider": "github",
                    "id": str(user.get("id", "")),
                    "name": user.get("login", ""),
                    "email": email,
                    "avatar": user.get("avatar_url", ""),
                }
                if _is_allowed(user_info):
                    st.session_state["oauth_user"] = user_info
                    _persist_auth(user_info)
                    st.rerun()
                else:
                    st.error(f"账号 {user_info['name']} ({email}) 未被授权访问此应用。")
            else:
                st.error("无法获取 GitHub 用户信息，请重试。")

    if not has_any:
        st.warning("OAuth 登录未配置。请在 Streamlit Secrets 中设置 client_id。")


def _oauth_config() -> dict[str, Any]:
    try:
        config = st.secrets.get("oauth", {})
    except StreamlitSecretNotFoundError:
        return {}
    return config if hasattr(config, "get") else {}


def render_user_header() -> None:
    user = st.session_state.get("oauth_user")
    if not user:
        return

    cols = st.columns([8, 1])
    with cols[0]:
        name = user.get("name", "用户")
        email = user.get("email", "")
        provider = user.get("provider", "")
        label = f"{name}"
        if email:
            label += f" ({email})"
        label += f" | {provider}"
        st.caption(label)
    with cols[1]:
        if st.button("登出", key="logout_btn"):
            del st.session_state["oauth_user"]
            _clear_persisted_auth()
            st.rerun()


_HMAC_SECRET = None


def _get_hmac_secret() -> str:
    """Get HMAC signing secret from Streamlit secrets or generate a session-level fallback."""
    global _HMAC_SECRET
    if _HMAC_SECRET is not None:
        return _HMAC_SECRET
    try:
        _HMAC_SECRET = st.secrets.get("auth_hmac_secret", "")
    except StreamlitSecretNotFoundError:
        _HMAC_SECRET = ""
    if not _HMAC_SECRET:
        # Session-stable fallback: same secret for the lifetime of this server process
        _HMAC_SECRET = hashlib.sha256(b"quant-assistant-auth-fallback").hexdigest()[:32]
    return _HMAC_SECRET


def _sign(payload: str) -> str:
    """HMAC-SHA256 signature of the payload."""
    return hmac.new(
        _get_hmac_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _encode_auth(user_info: dict[str, Any]) -> str:
    """Encode user info with HMAC signature and timestamp for tamper-proof persistence."""
    envelope = {"user": user_info, "ts": int(time.time())}
    payload = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
    sig = _sign(payload)
    token_data = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(token_data.encode("utf-8")).decode("ascii")


def _decode_auth(token: str) -> dict[str, Any] | None:
    """Decode a signed auth token. Returns None if signature invalid or expired."""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        payload, sig = raw.rsplit("|", 1)
        expected = _sign(payload)
        if not hmac.compare_digest(sig, expected):
            return None
        envelope = json.loads(payload)
        user_info = envelope.get("user", {})
        ts = envelope.get("ts", 0)
        # Token expires after 30 days
        if time.time() - ts > 30 * 86400:
            return None
        return user_info
    except Exception:
        return None


def _persist_auth(user_info: dict[str, Any]) -> None:
    """Store auth token in URL query params so it survives WebSocket reconnects."""
    st.query_params["auth"] = _encode_auth(user_info)


def _clear_persisted_auth() -> None:
    """Remove auth token from query params on explicit logout."""
    if "auth" in st.query_params:
        del st.query_params["auth"]


def require_auth() -> None:
    # 1. Check live session state
    if "oauth_user" in st.session_state:
        render_user_header()
        return

    # 2. Try to restore from query params (survives WebSocket reconnect)
    auth_token = st.query_params.get("auth")
    if auth_token:
        user_info = _decode_auth(auth_token)
        if user_info and _is_allowed(user_info):
            st.session_state["oauth_user"] = user_info
            render_user_header()
            return

    # 3. If OAuth is not configured, auto-login as anonymous local user
    oauth_cfg = _oauth_config()
    has_provider = any(
        provider_cfg.get("client_id")
        for key, provider_cfg in oauth_cfg.items()
        if isinstance(provider_cfg, dict)
    )
    if not has_provider:
        st.session_state["oauth_user"] = {
            "provider": "local",
            "id": "local",
            "name": "本地用户",
            "email": "",
            "avatar": "",
        }
        return

    # 4. OAuth configured but not authenticated — show login
    _render_login()
    st.stop()
