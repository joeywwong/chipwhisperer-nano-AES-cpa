"""Fresh Nano acquisitions using existing firmware. Never builds or flashes."""
import argparse
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import secrets
import sys
import uuid

import numpy as np
from Crypto.Cipher import AES
from aeslab import write_json, digest


def checked_capture(cw, scope, target, key, plaintext, samples):
    trace = cw.capture_trace(scope, target, bytearray(plaintext), bytearray(key), always_send_key=True)
    if trace is None or trace.textout is None:
        raise TimeoutError('Missing trace or ciphertext')
    w = np.asarray(trace.wave, dtype=float)
    if w.shape != (samples,) or not np.isfinite(w).all():
        raise ValueError('Invalid waveform length or nonfinite samples')
    expected = AES.new(key, AES.MODE_ECB).encrypt(plaintext)
    if bytes(trace.textout) != expected:
        raise ValueError('Ciphertext mismatch: abort, do not select only successful encryptions')
    if bytes(trace.textin) != plaintext:
        raise ValueError('Plaintext mismatch')
    return w, expected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--trials', type=int, default=5)
    p.add_argument('--traces', type=int, default=100)
    p.add_argument('--samples', type=int, default=5000)
    p.add_argument('--retries', type=int, default=2)
    p.add_argument('--firmware-file', type=Path, help='Candidate file only; does not attest installed image')
    args = p.parse_args()
    if args.trials < 1 or args.traces < 2 or not 2 <= args.samples <= 50000 or args.retries < 0:
        p.error('Invalid counts')
    args.out.mkdir(parents=True, exist_ok=False)
    import chipwhisperer as cw
    if 'always_send_key' not in inspect.signature(cw.capture_trace).parameters:
        raise RuntimeError('Installed capture API lacks explicit key reload')
    session = str(uuid.uuid4())
    settings = {'status': 'MEASURED', 'session_id': session, 'python': sys.version.split()[0],
                'chipwhisperer': cw.__version__, 'numpy': np.__version__, 'protocol': 'SimpleSerial 1.1',
                'target': 'Nano integrated STM32F030; owner laboratory target',
                'firmware_installed_hash': 'UNKNOWN: no readback or flashing performed',
                'candidate_firmware_sha256': digest(args.firmware_file) if args.firmware_file else None,
                'requested_trials': args.trials, 'requested_traces': args.traces, 'samples': args.samples,
                'independence': 'fresh OS-random key/plaintexts and reopened scope per trial; one visit, no power cycle',
                'key_reload': 'set_key(always_send=True) and capture_trace(always_send_key=True) every encryption',
                'reset_validation': 'No reset requested; each returned ciphertext independently checked'}
    write_json(args.out/'protocol.json', settings)
    failures = 0
    for trial in range(args.trials):
        scope = target = None
        waves, pts, cts, errors = [], [], [], []
        key = secrets.token_bytes(16)
        meta = {**settings, 'trial_id': str(uuid.uuid4()), 'trial': trial,
                'started_utc': datetime.now(timezone.utc).isoformat()}
        try:
            scope = cw.scope()
            if type(scope).__name__ != 'CWNano':
                raise RuntimeError('Expected CWNano; refusing another device')
            scope.default_setup()
            scope.adc.samples = args.samples
            target = cw.target(scope, cw.targets.SimpleSerial)
            meta['scope_settings'] = str(scope)
            meta['adc_clock_hz'] = scope.adc.clk_freq
            # Known-answer health check, not included in statistical dataset.
            katkey = bytes(range(16)); katpt = bytes.fromhex('00112233445566778899aabbccddeeff')
            target.set_key(bytearray(katkey), always_send=True)
            checked_capture(cw, scope, target, katkey, katpt, args.samples)
            target.set_key(bytearray(key), always_send=True)
            for i in range(args.traces):
                pt = secrets.token_bytes(16)
                for retry in range(args.retries+1):
                    try:
                        w, ct = checked_capture(cw, scope, target, key, pt, args.samples)
                        break
                    except TimeoutError as e:
                        errors.append({'trace': i, 'retry': retry, 'error': str(e)})
                        if retry == args.retries:
                            raise
                        target.flush()
                waves.append(w); pts.append(np.frombuffer(pt, dtype=np.uint8)); cts.append(np.frombuffer(ct, dtype=np.uint8))
            meta['outcome'] = 'COMPLETE'
        except Exception as e:
            failures += 1
            meta['outcome'] = 'FAILED'
            errors.append({'error': type(e).__name__ + ': ' + str(e)})
        finally:
            for device in (target, scope):
                if device is not None:
                    try: device.dis()
                    except Exception as e: errors.append({'disconnect_error': str(e)})
        meta.update(completed_traces=len(waves), errors=errors, finished_utc=datetime.now(timezone.utc).isoformat())
        stem = f'trial-{trial:02d}'
        if waves:
            name = stem + ('.npz' if meta['outcome']=='COMPLETE' else '-partial.npz')
            with (args.out/name).open('xb') as f:
                np.savez_compressed(f, waves=np.stack(waves), plaintexts=np.stack(pts), ciphertexts=np.stack(cts),
                                    key=np.frombuffer(key, dtype=np.uint8), metadata=json.dumps(meta))
            meta['dataset'] = name; meta['sha256'] = digest(args.out/name)
        write_json(args.out/(stem+'.json'), meta)
        print(f"trial {trial+1}/{args.trials}: {meta['outcome']}, {len(waves)} traces", flush=True)
        if meta['outcome'] != 'COMPLETE':
            print(json.dumps(errors), flush=True)
            # A failed health check must not repeatedly drive an unknown target.
            break
    write_json(args.out/'completion.json', {'requested_trials': args.trials, 'attempted_trials': trial+1,
               'failed_trials': failures, 'unattempted_trials': args.trials-trial-1})
    if failures: raise SystemExit(1)


if __name__ == '__main__':
    main()
