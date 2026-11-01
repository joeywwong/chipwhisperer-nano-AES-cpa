# ChipWhisperer-Nano AES CPA: Setup and Reproduction

This document describes the experimental setup and reproduction procedure for
[`aes128_cpa_nano.ipynb`](../aes128_cpa_nano.ipynb).

The experiment uses a **ChipWhisperer-Nano with its integrated STM32F030 target**,
not an external STM32 development board. It is a hands-on learning exercise
against an unprotected AES-128 reference implementation.

## Hardware and software

| Item | Configuration |
| --- | --- |
| Capture and target hardware | ChipWhisperer-Nano (CWNANO), integrated STM32F030 |
| Host OS | Windows 11 |
| Firmware build | Ubuntu via Windows Subsystem for Linux (WSL) |
| ARM toolchain | `arm-none-eabi-gcc` |
| Target firmware | NewAE `simpleserial-aes` with `TINYAES128C` |
| Firmware build options | `PLATFORM=CWNANO CRYPTO_TARGET=TINYAES128C SS_VER=SS_VER_1_1` |
| Capture configuration | `scope.default_setup()`, 5,000 samples per trace in the recorded run |
| Analyzer | ChipWhisperer `cwa.cpa()` with `cwa.leakage_models.sbox_output` |
| Recorded Python package versions | ChipWhisperer 6.0.0; NumPy 1.26.4 |

Refer to the notebook's first executed cell for the captured environment
information. Other exact environment versions have not all been independently
verified. The `requirements.txt` file lists intended dependencies but is not
a fully tested environment lockfile.

## 1. Prepare the environment

1. Install NewAE ChipWhisperer following the
   [official setup documentation](https://chipwhisperer.readthedocs.io/).
2. Ensure the ChipWhisperer Python/Jupyter environment can access the Nano
   over USB from Windows.
3. In Ubuntu/WSL, install a suitable ARM cross-compiler (`gcc-arm-none-eabi`)
   and `make`.
4. Keep the **ChipWhisperer source checkout** and **this repository** in
   separate directories. The ChipWhisperer source checkout must contain
   `firmware/mcu/simpleserial-aes/Makefile`.

If a normal Windows PowerShell session cannot find `jupyter`, launch Jupyter
using the Python environment included with or configured for ChipWhisperer.
The interpreter used by a working ChipWhisperer notebook can be identified with
`import sys; print(sys.executable)`.

## 2. Open the notebook from the project repository

Open Jupyter with the repository as its working directory, then select
[`aes128_cpa_nano.ipynb`](../aes128_cpa_nano.ipynb).

The notebook resolves two **different** locations:

- `REPO_ROOT`: the directory containing the notebook, `README.md`, and `docs/`.
- `CW_SOURCE`: the NewAE ChipWhisperer source directory containing firmware.

By default, `REPO_ROOT` is the kernel's current directory and `CW_SOURCE` is
`Path.home() / "ChipWhisperer" / "chipwhisperer"`. If necessary, configure
`AES_CPA_REPO_ROOT` and `CHIPWHISPERER_SOURCE` before launching the kernel.
The notebook checks both locations before beginning.

On Windows, the firmware build cell calls WSL's Ubuntu distribution. If the
distribution has a different name, set `CHIPWHISPERER_WSL_DISTRO`.

## 3. Execute the hardware experiment

With the Nano connected via USB, execute the notebook cells in sequence:

1. **Configuration:** validate directories and print the ChipWhisperer/NumPy
   versions without printing absolute filesystem paths.
2. **Firmware build:** compile the NewAE SimpleSerial AES-128 target for CWNANO.
3. **Target programming:** flash and verify the integrated STM32F030 target.
4. **Known-answer verification:** confirm AES-128 encryption with an all-zero
   key and plaintext.
5. **Zero-key capture and CPA:** capture 100 traces with random plaintexts,
   save the measured arrays, and recover the 16-byte all-zero key.
6. **Nonzero-key capture and CPA:** verify the FIPS 197 example vector, capture
   100 more traces, and recover the fixed test key
   `000102030405060708090a0b0c0d0e0f`.
7. **Trace-count analysis:** rerun CPA on successively longer prefixes of the
   *same* nonzero-key capture set.
8. **Disconnect:** release the scope and target connections.

The CPA leakage hypothesis for each plaintext byte \(p\) and candidate
key byte \(k\) is

\[
L(p,k)=\operatorname{HW}(\operatorname{SBOX}(p\oplus k)).
\]

The analyzer correlates the predicted first-round S-box output Hamming weight
with the measured power samples.

## 4. Recorded results

**2026-11-02 indexing erratum:** the historical notebook and four original PNGs
are preserved. In the installed ChipWhisperer 6.0.0 progressive analyzer,
`trace_range=[0,n]` includes index `n`: the table below labels requests that used
11, 21, 31, 41, 51, 61, and 81 traces where available. At `[0,100]`, the analyzer
retains the result for the available 100 traces before an out-of-range read.
Use `[0,n-1]` for exactly `n` traces. Fresh exact-prefix analysis reports
1/11/15/16/16/16/16/16 correct bytes at 10/20/30/40/50/60/80/100 traces.
Thus 40 exact traces do recover this archived key, now independently verified;
the old graph alone did not establish that count. See the
[audit and cross-check](notes/01_existing_aes_cpa.md).

The committed notebook contains the following successful outputs:

- AES known-answer tests passed.
- Both datasets have 100 power traces, with 5,000 recorded samples per trace.
- Zero test key: **16/16 bytes recovered** using 100 traces.
- Nonzero test key (`000102030405060708090a0b0c0d0e0f`):
  **16/16 bytes recovered** using 100 traces.

The nonzero-key trace-prefix analysis in the committed notebook reported:

| Traces used | Correctly recovered bytes (out of 16) |
| ---: | ---: |
| 10 | 2 |
| 20 | 11 |
| 30 | 15 |
| 40 | 16 |
| 50 | 16 |
| 60 | 16 |
| 80 | 16 |
| 100 | 16 |

This is **one measured capture set**. The historical label 40 corresponds to
41 traces; see the exact-prefix correction above. It is not a guaranteed minimum or a
statistical success rate. Small-prefix analysis emitted a numerical
`RuntimeWarning` about an invalid division; the notebook records it.

## 5. Published artifacts

The repository contains two measured `.npz` archives:

- [`data/aes_100_traces.npz`](../data/aes_100_traces.npz)
- [`data/aes_100_traces_nonzero_key.npz`](../data/aes_100_traces_nonzero_key.npz)

Each archive is written by the notebook with the fields:

| Field | Expected shape | Meaning |
| --- | --- | --- |
| `waves` | `(100, 5000)` | Acquired power waveforms |
| `plaintexts` | `(100, 16)` | AES plaintext bytes |
| `ciphertexts` | `(100, 16)` | Captured AES ciphertext bytes |
| `key` | `(16,)` | Fixed laboratory test key |

The following figures are generated under `results/`:

- [`verified_aes_trace.png`](../results/verified_aes_trace.png)
- [`power_traces.png`](../results/power_traces.png)
- [`trace_variability.png`](../results/trace_variability.png)
- [`key_recovery_vs_traces.png`](../results/key_recovery_vs_traces.png)

The ChipWhisperer `.cwp` project files generated during execution are
local working files and are excluded by `.gitignore`; the `.npz` archives
are the portable published datasets.

## 6. Scope and limitations

- The target is an intentionally unprotected educational AES implementation.
- The exercise uses two known fixed test keys rather than independently
  randomized keys across many sessions.
- The trace-prefix curve reuses the same captured dataset; it is **not**
  a measured attack success probability.
- Hardware-specific results can change across captures due to noise,
  selected random plaintexts, alignment, and environmental conditions.
- The code and firmware depend on the NewAE ChipWhisperer ecosystem.
  No novel cryptanalytic attack is claimed.
- On another machine, validate the installed software versions and run the
  complete notebook rather than assuming identical measurements.

## References

- [NewAE ChipWhisperer source](https://github.com/newaetech/chipwhisperer)
- [ChipWhisperer documentation](https://chipwhisperer.readthedocs.io/)
- [NIST FIPS 197 — Advanced Encryption Standard](https://csrc.nist.gov/pubs/fips/197/final)
