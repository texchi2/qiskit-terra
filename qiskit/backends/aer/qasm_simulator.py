# -*- coding: utf-8 -*-

# Copyright 2017, IBM.
#
# This source code is licensed under the Apache License, Version 2.0 found in
# the LICENSE.txt file in the root directory of this source tree.

"""
Interface to C++ quantum circuit simulator with realistic noise.
"""


import uuid
import json
import logging
import os
import subprocess
from subprocess import PIPE
import platform

from math import log2
import numpy as np
from qiskit._util import local_hardware_info
from qiskit.backends.models import BackendConfiguration
from qiskit.backends import BaseBackend
from qiskit.backends.aer.aerjob import AerJob
from qiskit.result import Result

logger = logging.getLogger(__name__)

EXTENSION = '.exe' if platform.system() == 'Windows' else ''

# Add path to compiled qasm simulator
DEFAULT_SIMULATOR_PATHS = [
    # This is the path where Makefile creates the simulator by default
    os.path.abspath(os.path.join(os.path.dirname(__file__),
                                 '../../../out/src/qasm-simulator-cpp/qasm_simulator_cpp'
                                 + EXTENSION)),
    # This is the path where PIP installs the simulator
    os.path.abspath(os.path.join(os.path.dirname(__file__),
                                 'qasm_simulator_cpp' + EXTENSION)),
]


class QasmSimulator(BaseBackend):
    """C++ quantum circuit simulator with realistic noise"""

    DEFAULT_CONFIGURATION = {
        'backend_name': 'qasm_simulator',
        'backend_version': '1.0.0',
        'n_qubits': int(log2(local_hardware_info()['memory'] * (1024**3)/16)),
        'url': 'https://github.com/Qiskit/qiskit-terra/src/qasm-simulator-cpp',
        'simulator': True,
        'local': True,
        'conditional': True,
        'open_pulse': False,
        'memory': True,
        'max_shots': 65536,
        'description': 'A C++ realistic noise simulator for qasm experiments',
        'basis_gates': ['u0', 'u1', 'u2', 'u3', 'cx', 'cz', 'id', 'x', 'y', 'z',
                        'h', 's', 'sdg', 't', 'tdg', 'rzz', 'snapshot', 'wait',
                        'noise', 'save', 'load'],
        'gates': [{'name': 'TODO', 'parameters': [], 'qasm_def': 'TODO'}]
    }

    def __init__(self, configuration=None, provider=None):
        super().__init__(configuration=(configuration or
                                        BackendConfiguration.from_dict(self.DEFAULT_CONFIGURATION)),
                         provider=provider)

        # Try to use the default executable if not specified.
        if 'exe' in self._configuration:
            paths = [self._configuration.exe]
        else:
            paths = DEFAULT_SIMULATOR_PATHS

        # Ensure that the executable is available.
        try:
            self._configuration.exe = next(
                path for path in paths if (os.path.exists(path) and
                                           os.path.getsize(path) > 100))
        except StopIteration:
            raise FileNotFoundError('Simulator executable not found (using %s)' %
                                    getattr(self._configuration, 'exe', 'default locations'))

    def run(self, qobj):
        """Run a qobj on the backend."""
        job_id = str(uuid.uuid4())
        aer_job = AerJob(self, job_id, self._run_job, qobj)
        aer_job.submit()
        return aer_job

    def _run_job(self, job_id, qobj):
        """Run a Qobj on the backend."""
        self._validate(qobj)
        qobj_dict = qobj.as_dict()
        result = run(qobj_dict, self._configuration.exe)
        result['job_id'] = job_id
        return Result.from_dict(result)

    def _validate(self, qobj):
        for experiment in qobj.experiments:
            if 'measure' not in [op.name for
                                 op in experiment.instructions]:
                logger.warning("no measurements in circuit '%s', "
                               "classical register will remain all zeros.",
                               experiment.header.name)


class CliffordSimulator(BaseBackend):
    """"C++ Clifford circuit simulator with realistic noise."""

    DEFAULT_CONFIGURATION = {
        'backend_name': 'clifford_simulator',
        'backend_version': '1.0.0',
        'n_qubits': int(log2(local_hardware_info()['memory'] * (1024**3)/16)),
        'url': 'https://github.com/Qiskit/qiskit-terra/src/qasm-simulator-cpp',
        'simulator': True,
        'local': True,
        'conditional': True,
        'open_pulse': False,
        'memory': False,
        'max_shots': 65536,
        'description': 'A C++ Clifford simulator with approximate noise',
        'basis_gates': ['cx', 'id', 'x', 'y', 'z', 'h', 's', 'sdg', 'snapshot',
                        'wait', 'noise', 'save', 'load'],
        'gates': [{'name': 'TODO', 'parameters': [], 'qasm_def': 'TODO'}]
    }

    def __init__(self, configuration=None, provider=None):
        super().__init__(configuration=(configuration or
                                        BackendConfiguration.from_dict(self.DEFAULT_CONFIGURATION)),
                         provider=provider)

        # Try to use the default executable if not specified.
        if 'exe' in self._configuration:
            paths = [self._configuration.exe]
        else:
            paths = DEFAULT_SIMULATOR_PATHS

        # Ensure that the executable is available.
        try:
            self._configuration.exe = next(
                path for path in paths if (os.path.exists(path) and
                                           os.path.getsize(path) > 100))
        except StopIteration:
            raise FileNotFoundError('Simulator executable not found (using %s)' %
                                    getattr(self._configuration, 'exe', 'default locations'))

    def run(self, qobj):
        """Run a Qobj on the backend.

        Args:
            qobj (dict): job description

        Returns:
            AerJob: derived from BaseJob
        """
        job_id = str(uuid.uuid4())
        aer_job = AerJob(self, job_id, self._run_job, qobj)
        aer_job.submit()
        return aer_job

    def _run_job(self, job_id, qobj):
        qobj_dict = qobj.as_dict()
        self._validate()
        # set backend to Clifford simulator
        if 'config' in qobj_dict:
            qobj_dict['config']['simulator'] = 'clifford'
        else:
            qobj_dict['config'] = {'simulator': 'clifford'}
        result = run(qobj_dict, self._configuration.exe)
        result['job_id'] = job_id
        return Result.from_dict(result)

    def _validate(self):
        return


def run(qobj, executable):
    """
    Run simulation on C++ simulator inside a subprocess.

    Args:
        qobj (Qobj): qobj dictionary defining the simulation to run
        executable (string): filename (with path) of the simulator executable
    Returns:
        dict: A dict of simulation results
    """

    # Open subprocess and execute external command
    try:
        with subprocess.Popen([executable, '-'],
                              stdin=PIPE, stdout=PIPE, stderr=PIPE) as proc:
            cin = json.dumps(qobj).encode()
            cout, cerr = proc.communicate(cin)
        if cerr:
            logger.error('ERROR: Simulator encountered a runtime error: %s',
                         cerr.decode())
        sim_output = json.loads(cout.decode())
        return sim_output

    except FileNotFoundError:
        msg = "ERROR: Simulator exe not found at: %s" % executable
        logger.error(msg)
        return {"status": msg, "success": False}


def cx_error_matrix(cal_error, zz_error):
    """
    Return the coherent error matrix for CR error model of a CNOT gate.

    Args:
        cal_error (double): calibration error of rotation
        zz_error (double): ZZ interaction term error

    Returns:
        numpy.ndarray: A coherent error matrix U_error for the CNOT gate.

    Details:

    The ideal cross-resonsance (CR) gate corresponds to a 2-qubit rotation
        U_CR_ideal = exp(-1j * (pi/2) * XZ/2)

    where qubit-0 is the control, and qubit-1 is the target. This can be
    converted to a CNOT gate by single-qubit rotations::

        U_CX = U_L * U_CR_ideal * U_R

    The noisy rotation is implemented as
        U_CR_noise = exp(-1j * (pi/2 + cal_error) * (XZ + zz_error ZZ)/2)

    The retured error matrix is given by
        U_error = U_L * U_CR_noise * U_R * U_CX^dagger
    """
    # pylint: disable=invalid-name
    if cal_error == 0 and zz_error == 0:
        return np.eye(4)

    cx_ideal = np.array([[1, 0, 0, 0],
                         [0, 0, 0, 1],
                         [0, 0, 1, 0],
                         [0, 1, 0, 0]])
    b = np.sqrt(1.0 + zz_error * zz_error)
    a = b * (np.pi / 2.0 + cal_error) / 2.0
    sp = (1.0 + 1j * zz_error) * np.sin(a) / b
    sm = (1.0 - 1j * zz_error) * np.sin(a) / b
    c = np.cos(a)
    cx_noise = np.array([[c + sm, 0, -1j * (c - sm), 0],
                         [0, 1j * (c - sm), 0, c + sm],
                         [-1j * (c - sp), 0, c + sp, 0],
                         [0, c + sp, 0, 1j * (c - sp)]]) / np.sqrt(2)
    return cx_noise.dot(cx_ideal.conj().T)


def x90_error_matrix(cal_error, detuning_error):
    """
    Return the coherent error matrix for a X90 rotation gate.

    Args:
        cal_error (double): calibration error of rotation
        detuning_error (double): detuning amount for rotation axis error

    Returns:
        numpy.ndarray: A coherent error matrix U_error for the X90 gate.

    Details:

    The ideal X90 rotation is a pi/2 rotation about the X-axis:
        U_X90_ideal = exp(-1j (pi/2) X/2)

    The noisy rotation is implemented as
        U_X90_noise = exp(-1j (pi/2 + cal_error) (cos(d) X + sin(d) Y)/2)

    where d is the detuning_error.

    The retured error matrix is given by
        U_error = U_X90_noise * U_X90_ideal^dagger
    """
    # pylint: disable=invalid-name
    if cal_error == 0 and detuning_error == 0:
        return np.eye(2)
    else:
        x90_ideal = np.array([[1., -1.j], [-1.j, 1]]) / np.sqrt(2)
        c = np.cos(0.5 * cal_error)
        s = np.sin(0.5 * cal_error)
        gamma = np.exp(-1j * detuning_error)
        x90_noise = np.array([[c - s, -1j * (c + s) * gamma],
                              [-1j * (c + s) * np.conj(gamma), c - s]]) / np.sqrt(2)
    return x90_noise.dot(x90_ideal.conj().T)


def _generate_coherent_error_matrix(config):
    """
    Generate U_error matrix for CX and X90 gates.

    Args:
        config (dict): the config of a qobj circuit

    This parses the config for the following noise parameter keys and returns a
    coherent error matrix for simulation coherent noise::

        * 'CX' gate: 'calibration_error', 'zz_error'
        * 'X90' gate: 'calibration_error', 'detuning_error'
    """
    # pylint: disable=invalid-name
    if 'noise_params' in config:
        # Check for CR coherent error parameters
        if 'CX' in config['noise_params']:
            noise_cx = config['noise_params']['CX']
            cal_error = noise_cx.pop('calibration_error', 0)
            zz_error = noise_cx.pop('zz_error', 0)
            # Add to current coherent error matrix
            if not cal_error == 0 or not zz_error == 0:
                u_error = noise_cx.get('U_error', np.eye(4))
                u_error = u_error.dot(cx_error_matrix(cal_error, zz_error))
                config['noise_params']['CX']['U_error'] = u_error
        # Check for X90 coherent error parameters
        if 'X90' in config['noise_params']:
            noise_x90 = config['noise_params']['X90']
            cal_error = noise_x90.pop('calibration_error', 0)
            detuning_error = noise_x90.pop('detuning_error', 0)
            # Add to current coherent error matrix
            if not cal_error == 0 or not detuning_error == 0:
                u_error = noise_x90.get('U_error', np.eye(2))
                u_error = u_error.dot(x90_error_matrix(cal_error,
                                                       detuning_error))
                config['noise_params']['X90']['U_error'] = u_error
