# -*- coding: utf-8 -*-

# Copyright 2017, IBM.
#
# This source code is licensed under the Apache License, Version 2.0 found in
# the LICENSE.txt file in the root directory of this source tree.

# pylint: disable=invalid-name

"""
Interface to C++ quantum circuit simulator with realistic noise.
"""

import logging
import uuid
from math import log2
from numpy import array
from qiskit._util import local_hardware_info
from qiskit.backends.models import BackendConfiguration
from qiskit.qobj import QobjInstruction
from .qasm_simulator import QasmSimulator
from ._simulatorerror import SimulatorError
from .aerjob import AerJob

logger = logging.getLogger(__name__)


class StatevectorSimulator(QasmSimulator):
    """C++ statevector simulator"""

    DEFAULT_CONFIGURATION = {
        'backend_name': 'statevector_simulator',
        'backend_version': '1.0.0',
        'n_qubits': int(log2(local_hardware_info()['memory'] * (1024**3)/16)),
        'url': 'https://github.com/Qiskit/qiskit-terra/src/qasm-simulator-cpp',
        'simulator': True,
        'local': True,
        'conditional': False,
        'open_pulse': False,
        'memory': False,
        'max_shots': 65536,
        'description': 'A single-shot C++ statevector simulator for the |0> state evolution',
        'basis_gates': ['u1', 'u2', 'u3', 'cx', 'cz', 'id', 'x', 'y', 'z', 'h',
                        's', 'sdg', 't', 'tdg', 'rzz', 'load', 'save',
                        'snapshot'],
        'gates': [{'name': 'TODO', 'parameters': [], 'qasm_def': 'TODO'}]
    }

    def __init__(self, configuration=None, provider=None):
        super().__init__(configuration=(configuration or
                                        BackendConfiguration.from_dict(self.DEFAULT_CONFIGURATION)),
                         provider=provider)

    def run(self, qobj):
        """Run a qobj on the backend."""
        job_id = str(uuid.uuid4())
        aer_job = AerJob(self, job_id, self._run_job, qobj)
        aer_job.submit()
        return aer_job

    def _run_job(self, job_id, qobj):
        """Run a Qobj on the backend."""
        self._validate(qobj)
        final_state_key = 32767  # Internal key for final state snapshot
        # Add final snapshots to circuits
        for experiment in qobj.experiments:
            experiment.instructions.append(
                QobjInstruction(name='snapshot', params=[final_state_key],
                                label='MISSING', type='MISSING')
            )
        result = super()._run_job(job_id, qobj)
        # Remove added snapshot from qobj
        for experiment in qobj.experiments:
            del experiment.instructions[-1]
        # Extract final state snapshot and move to 'statevector' data field
        for experiment_result in result.results:
            snapshots = experiment_result.data.snapshots.to_dict()
            if str(final_state_key) in snapshots['statevector']:
                final_state_key = str(final_state_key)
            # Pop off final snapshot added above
            final_state = snapshots['statevector'].pop(final_state_key)[0]
            final_state = array([v[0] + 1j * v[1] for v in final_state], dtype=complex)
            # Add final state to results data
            experiment_result.data.statevector = final_state
            # Remove snapshot dict if empty
            if snapshots == {}:
                delattr(experiment_result.data, 'snapshots')
        return result

    def _validate(self, qobj):
        """Semantic validations of the qobj which cannot be done via schemas.
        Some of these may later move to backend schemas.

        1. No shots
        2. No measurements in the middle
        """
        if qobj.config.shots != 1:
            logger.info("statevector simulator only supports 1 shot. "
                        "Setting shots=1.")
            qobj.config.shots = 1
        for experiment in qobj.experiments:
            if getattr(experiment.config, 'shots', 1) != 1:
                logger.info("statevector simulator only supports 1 shot. "
                            "Setting shots=1 for circuit %s.", experiment.name)
                experiment.config.shots = 1
            for op in experiment.instructions:
                if op.name in ['measure', 'reset']:
                    raise SimulatorError(
                        "In circuit {}: statevector simulator does not support "
                        "measure or reset.".format(experiment.header.name))
