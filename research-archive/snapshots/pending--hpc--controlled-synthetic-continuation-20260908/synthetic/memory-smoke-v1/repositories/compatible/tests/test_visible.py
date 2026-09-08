from gateway import Request, user_from_request


def test_attested_gateway_identity() -> None:
    request = Request(
        {"X-Synthetic-Gateway": "trusted", "X-Synthetic-User": "alice"},
        peer_attested=True,
    )
    assert user_from_request(request) == "alice"


def test_missing_gateway_marker_is_anonymous() -> None:
    request = Request({"X-Synthetic-User": "alice"}, peer_attested=True)
    assert user_from_request(request) is None
