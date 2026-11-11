from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call

import pytest
from pyvisa.errors import VisaIOError
from pyvisa.resources import MessageBasedResource

from qcodes.instrument_drivers.stanford_research import SIM900, SIM960
from qcodes.parameters import Parameter

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture


@pytest.fixture
def visa_handle(mocker: "MockerFixture") -> MagicMock:
    handle = MagicMock(spec=MessageBasedResource)
    handle.visalib = MagicMock()
    handle.query.return_value = "Stanford Research Systems,SIM900,s/n123,ver3.6"
    mocker.patch.object(SIM900, "_open_resource", return_value=handle)
    return handle


@pytest.fixture
def sim900(visa_handle: MagicMock) -> "Generator[SIM900, None, None]":
    instrument = SIM900("sim900", "GPIB::1::INSTR", query_delay=0)
    try:
        yield instrument
    finally:
        instrument.close()


@pytest.fixture
def sim960(sim900: SIM900) -> SIM960:
    module = SIM960(sim900, "pid", 1)
    sim900.add_submodule("pid", module)
    return module


def test_mainframe_initialization(sim900: SIM900, visa_handle: MagicMock) -> None:
    assert visa_handle.read_termination == "\n"
    assert visa_handle.write_termination == "\n"
    assert visa_handle.timeout == 4000
    visa_handle.write.assert_called_once_with("FLSH")
    assert sim900.IDN()["model"] == "SIM900"


def test_module_initialization(sim960: SIM960, visa_handle: MagicMock) -> None:
    assert visa_handle.write.call_args_list == [
        call("FLSH"),
        call('SNDT 1,"TOKN OFF"'),
        call('SNDT 1,"TERM CRLF"'),
    ]
    assert sim960.root_instrument is sim960.parent
    assert sim960.parent.submodules["pid"] is sim960
    assert "pid" in sim960.parent.snapshot(update="Never")["submodules"]


def test_write_port(sim900: SIM900, visa_handle: MagicMock) -> None:
    sim900.write_port(8, 'ECHO? "test"')
    visa_handle.write.assert_called_with('SNDT 8,"ECHO? ""test"""')


@pytest.mark.parametrize("port", [0, 9, 1.5])
def test_invalid_port(sim900: SIM900, visa_handle: MagicMock, port: int) -> None:
    visa_handle.reset_mock()
    with pytest.raises((ValueError, TypeError)):
        sim900.write_port(port, "*IDN?")
    with pytest.raises((ValueError, TypeError)):
        SIM960(sim900, "invalid", port)
    visa_handle.write.assert_not_called()


@pytest.mark.parametrize("cmd", ["GAIN 1\n*RST", "GAIN 1\r"])
def test_reject_command_terminators(sim900: SIM900, cmd: str) -> None:
    with pytest.raises(ValueError, match="line terminators"):
        sim900.write_port(1, cmd)


def test_read_port(sim900: SIM900, visa_handle: MagicMock) -> None:
    visa_handle.query.return_value = "7"
    visa_handle.read_bytes.return_value = b"1.234\r\n"
    assert sim900.read_port(1) == "1.234\r\n"
    visa_handle.query.assert_called_with("NINP? 1")
    visa_handle.write.assert_called_with("RAWN? 1,7")
    visa_handle.read_bytes.assert_called_once_with(7)


def test_read_port_explicit_count(sim900: SIM900, visa_handle: MagicMock) -> None:
    visa_handle.query.return_value = "7"
    visa_handle.read_bytes.return_value = b"1.234"
    assert sim900.read_port(2, 5) == "1.234"
    visa_handle.write.assert_called_with("RAWN? 2,5")
    visa_handle.read_bytes.assert_called_once_with(5)


@pytest.mark.parametrize("count", [-1, 8])
def test_read_port_invalid_count(
    sim900: SIM900, visa_handle: MagicMock, count: int
) -> None:
    visa_handle.query.return_value = "7"
    visa_handle.reset_mock()
    with pytest.raises(ValueError):
        sim900.read_port(1, count)
    visa_handle.write.assert_not_called()


def test_empty_buffer(sim900: SIM900, visa_handle: MagicMock) -> None:
    visa_handle.query.return_value = "0"
    visa_handle.reset_mock()
    assert sim900.read_port(1) == ""
    visa_handle.write.assert_not_called()
    visa_handle.read_bytes.assert_not_called()


def test_fragmented_response(sim900: SIM900, visa_handle: MagicMock) -> None:
    visa_handle.query.side_effect = ["0", "3", "0", "3", "1"]
    visa_handle.read_bytes.side_effect = [b"1.2", b"34\r", b"\n"]
    visa_handle.reset_mock()
    assert sim900.ask_port(3, "SMON?") == "1.234"
    assert visa_handle.write.call_args_list == [
        call("FLSI 3"),
        call('SNDT 3,"SMON?"'),
        call("RAWN? 3,3"),
        call("RAWN? 3,3"),
        call("RAWN? 3,1"),
    ]


@pytest.mark.parametrize("partial", [b"", b"1.23"])
def test_module_timeout(sim900: SIM900, visa_handle: MagicMock, partial: bytes) -> None:
    sim900.timeout(0)
    visa_handle.query.return_value = str(len(partial))
    visa_handle.read_bytes.return_value = partial
    with pytest.raises(TimeoutError, match="SIM900 port 1"):
        sim900.ask_port(1, "SMON?")


def test_io_error_propagates(sim900: SIM900, visa_handle: MagicMock) -> None:
    visa_handle.query.side_effect = VisaIOError(-1073807339)
    with pytest.raises(VisaIOError):
        sim900.ask_port(1, "SMON?")


def test_scan_ports(sim900: SIM900, visa_handle: MagicMock) -> None:
    identity = b"Stanford Research Systems,SIM960,s/n456,ver2.0\r\n"
    visa_handle.query.side_effect = [str(len(identity)), str(len(identity))] + ["0"] * 7
    visa_handle.read_bytes.return_value = identity
    assert sim900.scan_ports() == [identity.decode().strip()] + [None] * 7
    visa_handle.write.assert_any_call("FLSI 8")
    visa_handle.write.assert_any_call('SNDT 8,"*IDN?"')


def test_flush_all(sim900: SIM900, visa_handle: MagicMock) -> None:
    sim900.flush()
    visa_handle.write.assert_called_with("FLSI")


def test_module_identity_and_monitor(sim960: SIM960, visa_handle: MagicMock) -> None:
    identity = b"Stanford Research Systems,SIM960,s/n456,ver2.0\r\n"
    visa_handle.query.return_value = str(len(identity))
    visa_handle.read_bytes.return_value = identity
    assert sim960.IDN() == identity.decode().strip()
    visa_handle.write.assert_any_call('SNDT 1,"*IDN?"')
    visa_handle.query.return_value = "9"
    visa_handle.read_bytes.return_value = b"+1.2345\r\n"
    assert sim960.setpoint_monitor() == 1.2345
    visa_handle.write.assert_any_call('SNDT 1,"SMON?"')


@pytest.mark.parametrize(
    "name,command,value,formatted",
    [
        ("gain", "GAIN", 2.5, "2.5"),
        ("gain", "GAIN", -2.5, "-2.5"),
        ("integral", "INTG", 0.015, "0.015"),
        ("derivative", "DERV", 0.000015, "1.5e-05"),
        ("offset", "OFST", 1.234, "1.234"),
        ("setpoint", "SETP", -1.234, "-1.234"),
        ("manual_output", "MOUT", 1.234, "1.234"),
        ("ramp_rate", "RATE", 0.0022, "0.0022"),
        ("output_limit_lower", "LLIM", -1.23, "-1.23"),
        ("output_limit_upper", "ULIM", 1.23, "1.23"),
    ],
)
def test_numeric_parameters(
    sim960: SIM960,
    mocker: "MockerFixture",
    name: str,
    command: str,
    value: float,
    formatted: str,
) -> None:
    ask = mocker.patch.object(SIM900, "ask_port", return_value=str(value))
    write = mocker.patch.object(SIM900, "write_port")
    parameter = sim960.parameters[name]
    assert parameter() == value
    ask.assert_called_with(1, f"{command}?")
    ask.return_value = "10" if name == "output_limit_lower" else "-10"
    parameter(value)
    write.assert_called_once_with(1, f"{command} {formatted}")


@pytest.mark.parametrize(
    "name,low,high",
    [
        ("gain", 0.1, 1000),
        ("integral", 0.01, 500000),
        ("derivative", 1e-6, 10),
        ("offset", -10, 10),
        ("setpoint", -10, 10),
        ("manual_output", -10, 10),
        ("ramp_rate", 1e-3, 1e4),
        ("output_limit_lower", -10, 10),
        ("output_limit_upper", -10, 10),
    ],
)
def test_numeric_boundaries(sim960: SIM960, name: str, low: float, high: float) -> None:
    parameter = sim960.parameters[name]
    parameter.validate(low)
    parameter.validate(high)
    with pytest.raises(ValueError):
        parameter(low - 0.01 if low >= 0 else low - 1)
    with pytest.raises(ValueError):
        parameter(high + 1)


@pytest.mark.parametrize("value", [-1001, -0.01, 0, 0.01, 1001])
def test_invalid_gain(sim960: SIM960, value: float) -> None:
    with pytest.raises(ValueError):
        sim960.gain(value)


@pytest.mark.parametrize(
    "name,command,values",
    [
        ("polarity", "APOL", ["negative", "positive"]),
        ("output_mode", "AMAN", ["manual", "pid"]),
        ("setpoint_source", "INPT", ["internal", "external"]),
        ("proportional_enable", "PCTL", [False, True]),
        ("integral_enable", "ICTL", [False, True]),
        ("derivative_enable", "DCTL", [False, True]),
        ("offset_enable", "OCTL", [False, True]),
        ("ramp_enable", "RAMP", [False, True]),
        (
            "display",
            "DISP",
            [
                "gain",
                "integral",
                "derivative",
                "offset",
                "ramp_rate",
                "setpoint",
                "manual_output",
                "output_limit_upper",
                "output_limit_lower",
                "setpoint_monitor",
                "measure_monitor",
                "error_monitor",
                "output_monitor",
            ],
        ),
    ],
)
def test_mapped_parameters(
    sim960: SIM960,
    mocker: "MockerFixture",
    name: str,
    command: str,
    values: list[str] | list[bool],
) -> None:
    ask = mocker.patch.object(SIM900, "ask_port")
    write = mocker.patch.object(SIM900, "write_port")
    parameter = sim960.parameters[name]
    for raw, value in enumerate(values):
        ask.return_value = str(raw)
        assert parameter() == value
        ask.assert_called_with(1, f"{command}?")
        parameter(value)
        write.assert_called_with(1, f"{command} {raw}")
    with pytest.raises(ValueError):
        parameter("invalid")


@pytest.mark.parametrize("state", ["idle", "pending", "ramping", "paused"])
def test_ramp_status(sim960: SIM960, mocker: "MockerFixture", state: str) -> None:
    raw = ["idle", "pending", "ramping", "paused"].index(state)
    ask = mocker.patch.object(SIM900, "ask_port", return_value=str(raw))
    assert sim960.ramp_status() == state
    ask.assert_called_once_with(1, "RMPS?")
    assert not sim960.ramp_status.settable


@pytest.mark.parametrize(
    "name,command",
    [
        ("setpoint_monitor", "SMON?"),
        ("measure_monitor", "MMON?"),
        ("error_monitor", "EMON?"),
        ("output_monitor", "OMON?"),
    ],
)
def test_monitors(
    sim960: SIM960, mocker: "MockerFixture", name: str, command: str
) -> None:
    ask = mocker.patch.object(SIM900, "ask_port", return_value="-0.123456")
    parameter = sim960.parameters[name]
    assert parameter() == -0.123456
    assert isinstance(parameter, Parameter)
    assert parameter.unit == "V"
    assert not parameter.settable
    ask.assert_called_once_with(1, command)


@pytest.mark.parametrize(
    "name,other,value",
    [("output_limit_lower", "ULIM?", 2), ("output_limit_upper", "LLIM?", -2)],
)
def test_output_limit_ordering(
    sim960: SIM960,
    mocker: "MockerFixture",
    name: str,
    other: str,
    value: float,
) -> None:
    ask = mocker.patch.object(SIM900, "ask_port", return_value="0")
    write = mocker.patch.object(SIM900, "write_port")
    with pytest.raises(ValueError, match="output limit"):
        sim960.parameters[name](value)
    ask.assert_called_once_with(1, other)
    write.assert_not_called()
    sim960.parameters[name](0)
    write.assert_called_once()


@pytest.mark.parametrize("enable", [False, True])
def test_start_ramping(sim960: SIM960, visa_handle: MagicMock, enable: bool) -> None:
    sim960.start_ramping(enable)
    visa_handle.write.assert_called_with(f'SNDT 1,"STRT {int(enable)}"')


def test_close_releases_resource(sim900: SIM900, visa_handle: MagicMock) -> None:
    sim900.close()
    visa_handle.close.assert_called_once()
