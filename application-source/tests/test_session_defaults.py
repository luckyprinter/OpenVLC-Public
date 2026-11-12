from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend


def test_empty_session_does_not_invent_measurements():
    session = build_empty_session()

    assert session.signal.lux is None
    assert session.signal.adc_vref is None
    assert session.signal.data_rate is None
    assert session.signal.ber is None
    assert session.signal.strict_ber is None
    assert session.signal.crc_status == "Unknown"
    assert session.latest_transfer.quality.strict_ber is None
    assert session.latest_transfer.quality.bit_accuracy is None
    assert session.latest_transfer.quality.bit_errors is None


def test_live_lq_signal_does_not_turn_pvo_into_lux_or_pass_rate_into_crc():
    backend = RXPhysicalBackend()
    snapshot = backend._build_from_lq({
        "SIGNAL": 1.2,
        "VREF": 0.9,
        "MARGIN": 0.365,
        "PASS_RATE": 100.0,
    })

    assert snapshot.session.signal.lux is None
    assert snapshot.session.signal.ber is None
    assert snapshot.session.signal.strict_ber is None
    assert snapshot.session.signal.crc_status == "Unknown"
    assert snapshot.transfer.quality.strict_ber is None
