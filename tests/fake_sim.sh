#!/bin/bash
# Fake simulation script — outputs sample errors to simulate a failed Verilator run.
# Point your AutoVerif project's sim_command at this script:
#   sim_command = "bash /path/to/tests/fake_sim.sh"
#
# Exit code 1 tells the runner that simulation failed (as a real tool would).

cat "$(dirname "$0")/sample_sim.log"
exit 1
