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



def test_session_builder_sanitizes_malformed_and_non_finite_status(monkeypatch):
    import gui_dev_v3.data.session as session_module

    statuses = {
        "rx": {
            "stage": "Receiving",
            "percent": "nan",
            "size_bytes": "not-a-number",
            "rate_bps": float("inf"),
            "total_chunks": "bad",
            "received_chunks": {},
            "tid": "invalid",
        },
        "signal": {
            "margin_v": "bad",
            "pvo_v": float("nan"),
            "vref_v": [],
            "adc_vref": "inf",
        },
    }
    monkeypatch.setattr(session_module, "read_status", lambda role: statuses.get(role))

    state = session_module.build_session_from_status("rx")

    assert state.progress_percent == 0
    assert state.signal.margin == 0.0
    assert state.signal.pvo == 0.0
    assert state.signal.vref == 0.0
    assert state.signal.adc_vref == 0.0
    assert state.latest_transfer.size_bytes == 0
    assert state.latest_transfer.total_chunks == 0
    assert state.latest_transfer.received_chunks == 0
    assert state.latest_transfer.tid == 0


def test_session_builder_clamps_progress_and_chunk_counts(monkeypatch):
    import gui_dev_v3.data.session as session_module
    statuses = {
        "rx": {
            "stage": "Receiving",
            "percent": 180,
            "total_chunks": 4,
            "received_chunks": 99,
            "size": -10,
            "tid": 700000,
        },
        "signal": {},
    }
    monkeypatch.setattr(session_module, "read_status", lambda role: statuses.get(role))

    state = session_module.build_session_from_status("rx")

    assert state.progress_percent == 100
    assert state.latest_transfer.total_chunks == 4
    assert state.latest_transfer.received_chunks == 4
    assert state.latest_transfer.size_bytes == 0
    assert state.latest_transfer.tid == 999999
