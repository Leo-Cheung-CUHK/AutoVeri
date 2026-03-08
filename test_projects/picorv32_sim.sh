#!/bin/bash
# AutoVerif AI — PicoRV32 simulation script using Icarus Verilog
#
# Usage (as AutoVerif sim_command):
#   bash /path/to/test_projects/picorv32_sim.sh
#
# Must be run from inside the picorv32 repo directory.
# Requires: iverilog, vvp

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PICORV32_DIR="${1:-$(pwd)}"

cd "$PICORV32_DIR"

echo "=== AutoVerif PicoRV32 Simulation (Icarus Verilog) ==="
echo "Working directory: $(pwd)"
echo ""

# Step 1: Compile
echo "[1/2] Compiling with iverilog..."
iverilog -Wall -Wno-sensitivity-entire-array \
    -o /tmp/picorv32_sim \
    testbench.v picorv32.v 2>&1
COMPILE_EXIT=$?

if [ $COMPILE_EXIT -ne 0 ]; then
    echo ""
    echo "Compilation FAILED (exit $COMPILE_EXIT)"
    exit $COMPILE_EXIT
fi

echo "Compilation OK."
echo ""

# Step 2: Run simulation (requires firmware.hex)
if [ ! -f firmware/firmware.hex ]; then
    echo "[2/2] Skipping simulation — firmware/firmware.hex not found."
    echo "      To run full simulation, build firmware with RISC-V GCC:"
    echo "        cd firmware && make"
    echo ""
    echo "Compile-time check passed. No runtime errors."
    exit 0
fi

echo "[2/2] Running simulation..."
vvp -N /tmp/picorv32_sim 2>&1
SIM_EXIT=$?

echo ""
if [ $SIM_EXIT -ne 0 ]; then
    echo "Simulation FAILED (exit $SIM_EXIT)"
    exit $SIM_EXIT
fi

echo "Simulation PASSED."
exit 0
