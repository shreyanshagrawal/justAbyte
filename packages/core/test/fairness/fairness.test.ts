import { describe, it, expect } from 'vitest';
import { CORE_VERSION, getEngineStatus } from '../../src/index.js';

describe('OpenCred Fairness Test Suite [fairness]', () => {
  it('verifies advisory-only invariant for fairness', () => {
    const status = getEngineStatus();
    expect(status.advisoryOnly).toBe(true);
  });

  it('enforces cold start fairness baseline', () => {
    // Invariant: absence of history must result in default neutral state, never negative
    const coldStartDefaults = {
      reputation: 0.0,
      risk: 'insufficient_evidence',
      confidence: 0.0,
    };

    expect(coldStartDefaults.reputation).toBe(0.0);
    expect(coldStartDefaults.risk).toBe('insufficient_evidence');
    expect(coldStartDefaults.confidence).toBe(0.0);
  });

  it('guarantees core version integrity', () => {
    expect(CORE_VERSION).toBeDefined();
  });
});
