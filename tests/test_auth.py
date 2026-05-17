from streamlit.errors import StreamlitSecretNotFoundError

from quant_assistant import auth


class MissingSecrets:
    def get(self, *_args, **_kwargs):
        raise StreamlitSecretNotFoundError("missing secrets.toml")


class DictLikeSecrets:
    def get(self, key, default=None):
        if key == "oauth":
            return DictLikeSection({"github": {"client_id": "client-id"}})
        return default


class DictLikeSection:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeStreamlit:
    def __init__(self, secrets=None):
        self.secrets = secrets or MissingSecrets()
        self.session_state = {}
        self.warnings = []

    def title(self, _text):
        pass

    def info(self, _text):
        pass

    def warning(self, text):
        self.warnings.append(text)


def test_render_login_handles_missing_secrets(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(auth, "st", fake_st)

    auth._render_login()

    assert fake_st.warnings == ["OAuth 登录未配置。请在 Streamlit Secrets 中设置 client_id。"]


def test_is_allowed_allows_user_when_secrets_are_missing(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(auth, "st", fake_st)

    assert auth._is_allowed({"email": "user@example.com", "name": "user"}) is True


def test_oauth_config_keeps_streamlit_dict_like_sections(monkeypatch):
    fake_st = FakeStreamlit(secrets=DictLikeSecrets())
    monkeypatch.setattr(auth, "st", fake_st)

    assert auth._oauth_config().get("github", {}).get("client_id") == "client-id"
