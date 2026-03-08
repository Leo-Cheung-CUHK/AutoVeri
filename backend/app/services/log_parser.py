"""
LogParser: Parses Verilator/ModelSim/VCS simulation logs and extracts structured errors.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedErrorDict:
    error_type: str  # TB_ERROR | RTL_ERROR | FATAL
    file_path: str
    line_number: Optional[int]
    message: str
    sim_time: Optional[str] = None
    test_name: Optional[str] = None


# Patterns for Verilator-style errors
_VERILATOR_ERROR = re.compile(
    r"%Error(?:-[A-Z]+)?:\s+(?P<file>[^\s:]+):(?P<line>\d+):\s+(?P<msg>.+)"
)
_VERILATOR_FATAL = re.compile(
    r"%Fatal(?:-[A-Z]+)?:\s+(?P<file>[^\s:]+):(?P<line>\d+):\s+(?P<msg>.+)"
)

# Patterns for SystemVerilog $fatal / $error calls emitted by simulators
# e.g.: "# ** Fatal: (vsim-3601)  .../tb_top.sv(42): ..."
# or:   "# ** Error: .../tb_top.sv(42): ..."
_SV_FATAL = re.compile(
    r"(?:#\s+\*\*\s+Fatal|Error).*?(?P<file>[^\s(]+)\((?P<line>\d+)\):\s+(?P<msg>.+)"
)

# UVM-style: UVM_ERROR / UVM_FATAL
_UVM_ERROR = re.compile(
    r"UVM_(?P<level>ERROR|FATAL)\s+(?P<file>[^\s(]+)\((?P<line>\d+)\)\s+@\s*(?P<time>[^:]+):\s+(?P<msg>.+)"
)

# Generic $fatal / $error assertion lines
_SV_DOLLAR_FATAL = re.compile(
    r"(?:^|\s)\$fatal\b.*?(?P<file>[^\s(]+)\((?P<line>\d+)\)(?::\s*(?P<msg>.+))?"
)
_SV_DOLLAR_ERROR = re.compile(
    r"(?:^|\s)\$error\b.*?(?P<file>[^\s(]+)\((?P<line>\d+)\)(?::\s*(?P<msg>.+))?"
)

# Icarus Verilog (iverilog) errors:
# filename.v:42: error: Unable to bind wire/reg...
# filename.v:42: warning: ...  (warnings optionally parsed)
_ICARUS_ERROR = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s+error:\s+(?P<msg>.+)"
)
_ICARUS_FATAL = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s+(?:fatal error|internal error):\s+(?P<msg>.+)"
)

# Sim time extraction: "# Time: 1250 ns" or "Time = 1250"
_SIM_TIME = re.compile(
    r"(?:Time\s*[:=]\s*)(?P<time>\d+\s*(?:ns|ps|us|fs)?)", re.IGNORECASE
)

# Test name: ModelSim/QuestaSim prints "# ** Note: $test$plusargs..." but more common:
# "# run -all" or test plusargs. We detect lines like: "# Running test: my_test"
_TEST_NAME = re.compile(
    r"(?:Running test|TEST_NAME|test name)\s*[:=]\s*(?P<name>\S+)", re.IGNORECASE
)


class LogParser:
    """
    Parses simulation log files and returns a list of structured error records.

    Usage:
        parser = LogParser(tb_prefix="tb_", rtl_prefix="rtl_")
        errors = parser.parse(sim_log_text)
    """

    def __init__(self, tb_prefix: str = "tb_", rtl_prefix: str = "rtl_"):
        self.tb_prefix = tb_prefix.lower()
        self.rtl_prefix = rtl_prefix.lower()

    def _classify(self, file_path: str, is_fatal: bool = False) -> str:
        """
        Classify an error as TB_ERROR, RTL_ERROR, or FATAL.

        FATAL takes precedence when the simulator raised a $fatal / %Fatal.
        Otherwise, classify by filename prefix.
        """
        if is_fatal:
            return "FATAL"
        basename = file_path.split("/")[-1].split("\\")[-1].lower()
        if basename.startswith(self.tb_prefix):
            return "TB_ERROR"
        return "RTL_ERROR"

    def parse(self, sim_log: str) -> list[dict]:
        """
        Parse a simulation log string and return a list of ParsedError dicts.
        Each dict maps directly to the ParsedError model fields (excluding id/job_id).
        """
        errors: list[ParsedErrorDict] = []
        seen: set[tuple] = set()  # de-duplicate identical (file, line, msg) triplets

        current_sim_time: Optional[str] = None
        current_test_name: Optional[str] = None

        for raw_line in sim_log.splitlines():
            line = raw_line.strip()

            # Update running sim-time context
            tm = _SIM_TIME.search(line)
            if tm:
                current_sim_time = tm.group("time").strip()

            # Update running test-name context
            tn = _TEST_NAME.search(line)
            if tn:
                current_test_name = tn.group("name").strip()

            error = self._try_parse_line(line, current_sim_time, current_test_name)
            if error:
                dedup_key = (error.file_path, error.line_number, error.message[:120])
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    errors.append(error)

        return [self._to_dict(e) for e in errors]

    def _try_parse_line(
        self,
        line: str,
        sim_time: Optional[str],
        test_name: Optional[str],
    ) -> Optional[ParsedErrorDict]:
        """Try each pattern in priority order; return the first match."""

        # 1. Verilator %Fatal
        m = _VERILATOR_FATAL.search(line)
        if m:
            return ParsedErrorDict(
                error_type="FATAL",
                file_path=m.group("file"),
                line_number=int(m.group("line")),
                message=m.group("msg").strip(),
                sim_time=sim_time,
                test_name=test_name,
            )

        # 2. Verilator %Error
        m = _VERILATOR_ERROR.search(line)
        if m:
            fp = m.group("file")
            return ParsedErrorDict(
                error_type=self._classify(fp),
                file_path=fp,
                line_number=int(m.group("line")),
                message=m.group("msg").strip(),
                sim_time=sim_time,
                test_name=test_name,
            )

        # 3. UVM_ERROR / UVM_FATAL
        m = _UVM_ERROR.search(line)
        if m:
            fp = m.group("file")
            is_fatal = m.group("level") == "FATAL"
            uvm_time = m.group("time").strip() or sim_time
            return ParsedErrorDict(
                error_type=self._classify(fp, is_fatal=is_fatal),
                file_path=fp,
                line_number=int(m.group("line")),
                message=m.group("msg").strip(),
                sim_time=uvm_time,
                test_name=test_name,
            )

        # 4. $fatal (SystemVerilog assertion)
        m = _SV_DOLLAR_FATAL.search(line)
        if m:
            fp = m.group("file") or "unknown"
            ln = m.group("line")
            msg = m.group("msg") or "$fatal assertion triggered"
            return ParsedErrorDict(
                error_type="FATAL",
                file_path=fp,
                line_number=int(ln) if ln else None,
                message=msg.strip(),
                sim_time=sim_time,
                test_name=test_name,
            )

        # 5. $error (SystemVerilog assertion)
        m = _SV_DOLLAR_ERROR.search(line)
        if m:
            fp = m.group("file") or "unknown"
            ln = m.group("line")
            msg = m.group("msg") or "$error assertion triggered"
            return ParsedErrorDict(
                error_type=self._classify(fp),
                file_path=fp,
                line_number=int(ln) if ln else None,
                message=msg.strip(),
                sim_time=sim_time,
                test_name=test_name,
            )

        # 6. Generic simulator Fatal/Error with file(line) format
        m = _SV_FATAL.search(line)
        if m:
            fp = m.group("file") or "unknown"
            is_fatal = "fatal" in line.lower()
            return ParsedErrorDict(
                error_type=self._classify(fp, is_fatal=is_fatal),
                file_path=fp,
                line_number=int(m.group("line")),
                message=m.group("msg").strip(),
                sim_time=sim_time,
                test_name=test_name,
            )

        # 7. Icarus Verilog fatal/internal error
        m = _ICARUS_FATAL.match(line)
        if m:
            fp = m.group("file")
            return ParsedErrorDict(
                error_type="FATAL",
                file_path=fp,
                line_number=int(m.group("line")),
                message=m.group("msg").strip(),
                sim_time=sim_time,
                test_name=test_name,
            )

        # 8. Icarus Verilog error
        m = _ICARUS_ERROR.match(line)
        if m:
            fp = m.group("file")
            return ParsedErrorDict(
                error_type=self._classify(fp),
                file_path=fp,
                line_number=int(m.group("line")),
                message=m.group("msg").strip(),
                sim_time=sim_time,
                test_name=test_name,
            )

        return None

    @staticmethod
    def _to_dict(e: ParsedErrorDict) -> dict:
        return {
            "error_type": e.error_type,
            "file_path": e.file_path,
            "line_number": e.line_number,
            "message": e.message,
            "sim_time": e.sim_time,
            "test_name": e.test_name,
        }
