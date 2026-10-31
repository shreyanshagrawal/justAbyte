import { describe, it, expect } from 'vitest';
import { CORE_VERSION, getEngineStatus } from '../src/index.js';

describe('OpenCred Core Engine Verification', () => {
  it('exposes version and initialized status', () => {
    expect(CORE_VERSION).toBe('0.1.0');
    const status = getEngineStatus();
    expect(status.status).toBe('initialized');
  });

  it('guarantees advisory-only invariant', () => {
    const status = getEngineStatus();
    expect(status.advisoryOnly).toBe(true);
  });
});
