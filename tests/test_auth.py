from streamlit.errors import StreamlitSecretNotFoundError

from quant_assistant import auth


class MissingSecrets:
    def get(self, *_args, **_kwargs):
        raise StreamlitSecretNotFoundError("missing secrets.toml")


class FakeStreamlit:
    def __init__(self):
        self.secrets = MissingSecrets()
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
