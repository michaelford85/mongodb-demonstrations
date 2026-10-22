import pytest

from lib import config as c

GOOD = {
    "MONGODB_URI": "mongodb+srv://u:p@cluster0.abc.mongodb.net/?retryWrites=true",
    "VOYAGE_API_KEY": "al-real-looking-secret",
    "COMPETITOR_API_KEY": "sk-another-secret",
    "COMPETITOR_EMBEDDING_PROVIDER": "cohere",
    "COMPETITOR_EMBEDDING_MODEL": "embed-v4.0",
}


def test_ready_config_has_no_problems():
    assert c.validate_live(c.load_settings(GOOD)) == []


def test_empty_env_reports_all_missing():
    problems = c.validate_live(c.load_settings({}))
    text = " ".join(problems)
    assert "VOYAGE_API_KEY" in text and "COMPETITOR_API_KEY" in text and "MONGODB_URI" in text
    assert "model is not set" in text


def test_example_placeholders_are_rejected():
    env = dict(GOOD, VOYAGE_API_KEY="your_voyage_model_api_key_here",
               MONGODB_URI="mongodb+srv://<username>:<password>@<your-cluster>.mongodb.net/")
    problems = " ".join(c.validate_live(c.load_settings(env)))
    assert "VOYAGE_API_KEY" in problems and "MONGODB_URI" in problems


def test_unknown_provider_and_plain_http():
    env = dict(GOOD, COMPETITOR_EMBEDDING_PROVIDER="mystery")
    assert any("unsupported provider" in p for p in c.validate_live(c.load_settings(env)))
    env = dict(GOOD, COMPETITOR_BASE_URL="http://example.com/v1")
    assert any("plain http" in p for p in c.validate_live(c.load_settings(env)))


def test_same_model_rejected():
    env = dict(GOOD, COMPETITOR_EMBEDDING_PROVIDER="voyage", COMPETITOR_EMBEDDING_MODEL="voyage-4")
    # "voyage" is not a competitor provider; also flagged as unsupported or identical
    assert c.validate_live(c.load_settings(env))


def test_bad_numbers():
    with pytest.raises(c.ConfigError):
        c.load_settings(dict(GOOD, VOYAGE_OUTPUT_DIMENSION="big"))
    with pytest.raises(c.ConfigError):
        c.load_settings(dict(GOOD, EVAL_K_VALUES="5,ten"))
    with pytest.raises(c.ConfigError):
        c.load_settings(dict(GOOD, EVAL_SEED="x"))


def test_defaults_and_k_parsing():
    s = c.load_settings(GOOD)
    assert s.defaults.k_values == (5, 10) and s.defaults.depth == 10
    assert s.voyage.base_url == "https://ai.mongodb.com/v1" and s.voyage.model == "voyage-4"
    assert c.load_settings(dict(GOOD, EVAL_K_VALUES="10, 1,5")).defaults.k_values == (1, 5, 10)


def test_run_params_validation():
    assert c.RunParams(k_values=()).validate()
    assert c.RunParams(k_values=(5, 5)).validate()
    assert c.RunParams(dataset="nope").validate()
    assert c.RunParams(num_queries=0).validate()
    assert not c.RunParams().validate()


def test_secrets_never_appear_in_redacted_status_or_repr():
    s = c.load_settings(GOOD)
    blob = repr(s) + str(c.redacted(s, s.defaults)) + str(c.status_rows(s))
    for secret in ("al-real-looking-secret", "sk-another-secret", "u:p@"):
        assert secret not in blob
    assert "cluster0.abc.mongodb.net" in blob  # host only


def test_prefix_env_unescapes_newline_and_is_visible_in_redacted():
    s = c.load_settings(dict(GOOD, COMPETITOR_QUERY_PREFIX="Instruct: x\\nQuery: "))
    assert s.competitor.query_prefix == "Instruct: x\nQuery: " and s.competitor.document_prefix == ""
    assert "Instruct: x" in str(c.redacted(s, s.defaults))


def test_env_example_parses_to_documented_defaults_and_is_not_runnable():
    from pathlib import Path

    from dotenv import dotenv_values

    values = dotenv_values(Path(__file__).resolve().parent.parent / ".env.example")
    s = c.load_settings(values)
    assert s.voyage.model == "voyage-4" and s.voyage.base_url == "https://ai.mongodb.com/v1"
    assert s.competitor.provider == "openai"
    assert s.competitor.model == "intfloat/multilingual-e5-large-instruct"
    assert s.competitor.base_url == "https://api.deepinfra.com/v1/openai"
    assert s.competitor.document_prefix == "" and s.competitor.query_prefix.startswith("Instruct: ")
    assert s.competitor.query_prefix.endswith("\nQuery: ")
    # placeholders must never count as configured credentials
    problems = " ".join(c.validate_live(s))
    assert "VOYAGE_API_KEY" in problems and "COMPETITOR_API_KEY" in problems and "MONGODB_URI" in problems
