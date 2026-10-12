import socket

import pytest

from matchlab.ports import PortInUseError, PortSet, ensure_free, is_bound, port_set, wait_until_bound


def test_slots_do_not_overlap():
    assert port_set(0) == PortSet(16000, 16001, 16002)
    assert port_set(3) == PortSet(16030, 16031, 16032)


def test_port_in_use_is_reported():
    ports = port_set(40)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", ports.coach))
        with pytest.raises(PortInUseError, match=str(ports.coach)):
            ensure_free(ports)
    ensure_free(ports)


def test_bound_port_is_seen_without_binding_it():
    port = port_set(41).player
    assert not is_bound(port)
    with pytest.raises(RuntimeError, match="did not open port"):
        wait_until_bound(port, timeout_s=0.2)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", port))
        assert is_bound(port)
        wait_until_bound(port, timeout_s=1.0)


def test_is_bound_closes_its_files(recwarn):
    import gc

    for _ in range(3):
        is_bound(port_set(42).player)
    gc.collect()
    assert not [w for w in recwarn if issubclass(w.category, ResourceWarning)]


def test_is_bound_ignores_unreadable_tables(monkeypatch):
    import builtins

    def refuse(*args, **kwargs):
        raise PermissionError("no")

    monkeypatch.setattr(builtins, "open", refuse)
    assert is_bound(port_set(43).player) is False
