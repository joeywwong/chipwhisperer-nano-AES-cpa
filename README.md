# ChipWhisperer-Nano AES CPA Lab

A small, ongoing learning project to gain hands-on experience with power side-channel analysis using the ChipWhisperer-Nano.

The initial experiment reproduces a standard AES-128 correlation power analysis (CPA) exercise. The goal is to understand trace acquisition, leakage-based key recovery, and how to evaluate an attack on real hardware.

## Preserved initial results

- Hardware: ChipWhisperer-Nano with its onboard target
- Experiment: AES-128 encryption and power-trace capture
- Captured traces: 100
- AES ciphertext verification: passed
- CPA result: 16/16 key bytes recovered correctly

```text
Expected key:  000102030405060708090a0b0c0d0e0f
Recovered key: 000102030405060708090a0b0c0d0e0f
```

This is a controlled educational experiment using a fixed test key, not a new attack technique or a claim about the security of a production device.

## Status and next steps

On 2026-11-02, five new random-key acquisitions each recorded 100 physical traces
using the Nano's existing firmware. All 500 ciphertexts passed independent AES
checks, and all five keys were fully recovered at the exact 40-trace and
100-trace prefixes. Five successes give a Wilson 95% interval of approximately
56.6%–100%, conditional on independent trials; this is one device and one visit,
not a universal minimum or a cross-session reliability study.

Offline leakage-model and timing-shift comparisons are also available. Injected
shifts are **simulated transformations of measured traces**, not a deployed
countermeasure; an expanded alignment search restored all five keys. No new
firmware was flashed. The installed firmware's exact image hash remains unknown.

Start with the [experiment roadmap](docs/notes/experiment_roadmap.md),
[three-pass notes](docs/notes/01_existing_aes_cpa.md), and
[professor discussion guide](docs/notes/explain_to_professor.md).
Machine-readable outcomes are in
[results/random-key-20261102](results/random-key-20261102).

An [indexing erratum](docs/experiment_setup.md#4-recorded-results) explains the
historical notebook's inclusive `trace_range` endpoint. The notebook, original
datasets, and four original PNGs are unchanged. New analysis uses exact counts.

## Acknowledgment

This learning exercise builds on the [ChipWhisperer tutorials and documentation](https://chipwhisperer.readthedocs.io/).
