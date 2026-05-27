from hyper_demo.services.monitoring import HyperliquidWebsocketMonitor


def test_parse_all_mids_message() -> None:
    message = '{"channel":"allMids","data":{"mids":{"BTC":"106500.5","ETH":"3850"}}}'

    price = HyperliquidWebsocketMonitor.parse_all_mids_message(message, "BTC")

    assert price is not None
    assert price.asset == "BTC"
    assert price.mark_price == 106500.5
    assert price.source == "websocket"


def test_parse_all_mids_ignores_unrelated_messages() -> None:
    assert HyperliquidWebsocketMonitor.parse_all_mids_message('{"channel":"pong"}', "BTC") is None
