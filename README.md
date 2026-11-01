# ChipWhisperer-Nano AES CPA Lab

A small, ongoing learning project to gain hands-on experience with power side-channel analysis using the ChipWhisperer-Nano.

The initial experiment reproduces a standard AES-128 correlation power analysis (CPA) exercise. The goal is to understand trace acquisition, leakage-based key recovery, and how to evaluate an attack on real hardware.

## Current results

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

The first AES CPA experiment is complete. I am organizing the Jupyter notebook and results for reproducibility, then plan to examine correlation plots, the effect of trace count on key recovery, and further side-channel experiments.

## Acknowledgment

This learning exercise builds on the [ChipWhisperer tutorials and documentation](https://chipwhisperer.readthedocs.io/).
