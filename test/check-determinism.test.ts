import { describe, it, expect } from 'vitest';
import { findFirstDifference, checkDeterminism } from '../scripts/check-determinism.js';

describe('Determinism Check & Differing Field Detection', () => {
  it('returns null when objects are identical', () => {
    const objA = {
      seed: 42,
      contributors: [{ id: 'alice', reputation: 0.5 }],
      summary: { allPassed: true },
    };
    const objB = {
      seed: 42,
      contributors: [{ id: 'alice', reputation: 0.5 }],
      summary: { allPassed: true },
    };

    expect(findFirstDifference(objA, objB)).toBeNull();
  });

  it('detects and reports first differing field in nested object properties', () => {
    const run1 = {
      seed: 42,
      contributors: [{ id: 'alice', reputation: 0.5 }],
    };
    const run2 = {
      seed: 42,
      contributors: [{ id: 'alice', reputation: 0.55 }], // Differing value
    };

    const diff = findFirstDifference(run1, run2);
    expect(diff).not.toBeNull();
    expect(diff?.path).toBe('contributors[0].reputation');
    expect(diff?.value1).toBe(0.5);
    expect(diff?.value2).toBe(0.55);
  });

  it('detects leaked timestamp fields', () => {
    const run1 = {
      seed: 42,
      timestamp: '2026-11-01T01:00:00.000Z',
    };
    const run2 = {
      seed: 42,
      timestamp: '2026-11-01T01:00:00.500Z',
    };

    const diff = findFirstDifference(run1, run2);
    expect(diff).not.toBeNull();
    expect(diff?.path).toBe('timestamp');
  });

  it('detects array length differences', () => {
    const run1 = { items: [1, 2, 3] };
    const run2 = { items: [1, 2] };

    const diff = findFirstDifference(run1, run2);
    expect(diff).not.toBeNull();
    expect(diff?.path).toBe('items.length');
  });

  it('detects missing or unexpected keys', () => {
    const run1 = { seed: 42, extra: true };
    const run2 = { seed: 42 };

    const diff = findFirstDifference(run1, run2);
    expect(diff).not.toBeNull();
    expect(diff?.path).toBe('extra');
  });

  it('verifies that two consecutive simulation runs are byte-for-byte identical', () => {
    const result = checkDeterminism();
    expect(result.identical).toBe(true);
    expect(result.diff).toBeNull();
  });
});
