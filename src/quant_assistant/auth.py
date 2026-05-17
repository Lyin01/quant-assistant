from __future__ import annotations

import json
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
            st.rerun()


def require_auth() -> None:
    if "oauth_user" not in st.session_state:
        _render_login()
        st.stop()
    render_user_header()
