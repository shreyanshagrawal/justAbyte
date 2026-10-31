import { describe, it, expect } from 'vitest';
import { checkGate } from '../packages/simulation/src/gate.js';
import { GateThresholds, ContributorEvaluation } from '../packages/simulation/src/types.js';

describe('Simulation Gate Fairness Verifications', () => {
  const defaultThresholds: GateThresholds = {
    scenario: { seed: 42 },
    newcomer: {
      minReputation: 0.0,
      maxRisk: 0.0,
      allowedRiskState: 'insufficient_evidence',
    },
    suppression: {
      legitimateContributorFloor: 0.4,
      maxAllowedSuppressionDrop: 0.15,
    },
    aiContributions: {
      minReputation: 0.0,
      maxRiskPenalty: 0.0,
    },
  };

  it('passes when all fairness metrics satisfy the configured thresholds', () => {
    const evaluations: ContributorEvaluation[] = [
      {
        id: 'newcomer-1',
        role: 'newcomer',
        reputation: 0.0,
        risk: 'insufficient_evidence',
        confidence: 0.0,
      },
      {
        id: 'legitimate-1',
        role: 'legitimate',
        reputation: 0.8,
        risk: 0.0,
        confidence: 0.8,
      },
      {
        id: 'target-1',
        role: 'malicious_target',
        reputation: 0.75,
        risk: 0.0,
        confidence: 0.9,
        baselineReputation: 0.8,
        suppressionDrop: 0.05,
      },
      {
        id: 'ai-1',
        role: 'ai_assisted',
        reputation: 0.5,
        risk: 0.0,
        confidence: 0.5,
      },
    ];

    const result = checkGate(evaluations, defaultThresholds);
    expect(result.passed).toBe(true);
    expect(result.violations).toHaveLength(0);
  });

  it('FAILS when a newcomer receives a negative reputation', () => {
    const evaluations: ContributorEvaluation[] = [
      {
        id: 'penalized-newcomer',
        role: 'newcomer',
        reputation: -0.2, // Negative reputation violation
        risk: 'insufficient_evidence',
        confidence: 0.1,
      },
    ];

    const result = checkGate(evaluations, defaultThresholds);
    expect(result.passed).toBe(false);
    expect(result.violations.some((v) => v.includes('negative reputation'))).toBe(true);
  });

  it('FAILS when a newcomer receives elevated risk', () => {
    const evaluations: ContributorEvaluation[] = [
      {
        id: 'flagged-newcomer',
        role: 'newcomer',
        reputation: 0.0,
        risk: 0.6, // Elevated risk violation
        confidence: 0.1,
      },
    ];

    const result = checkGate(evaluations, defaultThresholds);
    expect(result.passed).toBe(false);
    expect(result.violations.some((v) => v.includes('elevated risk'))).toBe(true);
  });

  it('FAILS when a malicious denouncement ring suppresses a contributor below the floor', () => {
    const evaluations: ContributorEvaluation[] = [
      {
        id: 'suppressed-contributor',
        role: 'malicious_target',
        reputation: 0.25, // Below floor 0.4
        risk: 0.0,
        confidence: 0.8,
        baselineReputation: 0.85,
        suppressionDrop: 0.6,
      },
    ];

    const result = checkGate(evaluations, defaultThresholds);
    expect(result.passed).toBe(false);
    expect(result.violations.some((v) => v.includes('suppressed below floor'))).toBe(true);
  });

  it('FAILS when suppression drop exceeds maximum allowed limit', () => {
    const evaluations: ContributorEvaluation[] = [
      {
        id: 'excessive-drop-contributor',
        role: 'malicious_target',
        reputation: 0.5,
        risk: 0.0,
        confidence: 0.8,
        baselineReputation: 0.8,
        suppressionDrop: 0.3, // Exceeds maxAllowedSuppressionDrop of 0.15
      },
    ];

    const result = checkGate(evaluations, defaultThresholds);
    expect(result.passed).toBe(false);
    expect(result.violations.some((v) => v.includes('excessive suppression drop'))).toBe(true);
  });
});
