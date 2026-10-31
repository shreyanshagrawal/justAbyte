import { ContributorEvaluation } from './types.js';
import { SimulationScenario, ScenarioContributor } from './scenario.js';

/**
 * Three-way evaluation engine for OpenCred simulation:
 * Evaluates Reputation, Risk, and Confidence as three independent, orthogonal metrics.
 */
export function evaluateScenario(scenario: SimulationScenario): ContributorEvaluation[] {
  const evaluations: ContributorEvaluation[] = [];

  for (const contributor of scenario.contributors) {
    evaluations.push(evaluateContributor(contributor, scenario));
  }

  return evaluations;
}

export function evaluateContributor(
  contributor: ScenarioContributor,
  scenario: SimulationScenario,
): ContributorEvaluation {
  // Invariant 1: Cold start / Newcomers
  // A contributor with no history receives reputation = 0.0, risk = "insufficient_evidence", confidence = 0.0
  if (contributor.role === 'newcomer') {
    return {
      id: contributor.id,
      role: 'newcomer',
      reputation: 0.0,
      risk: 'insufficient_evidence',
      confidence: 0.0,
    };
  }

  // Calculate baseline trust from vouches
  let positiveTrustWeight = 0;
  for (const vouch of contributor.directVouches) {
    if (scenario.trustedRepos.includes(vouch.fromRepo)) {
      positiveTrustWeight += vouch.weight;
    }
  }

  const baselineReputation = Math.min(1.0, positiveTrustWeight / 2.0);

  // Invariant 2: Provenance & Ring containment
  // Malicious denouncement ring repositories are not trusted (t_ij = 0.0 from evaluating repo)
  // Therefore, malicious ring denouncements do not have propagation path weights and cannot suppress reputation
  let validDenouncementWeight = 0;
  for (const denouncement of contributor.denouncements) {
    if (scenario.trustedRepos.includes(denouncement.fromRepo)) {
      validDenouncementWeight += denouncement.weight;
    } else if (scenario.maliciousRingRepos.includes(denouncement.fromRepo)) {
      // Ring containment: Untrusted origin path weight = 0, discarded
      // Invariant: single count per origin, isolated rings have 0 propagation weight
      validDenouncementWeight += 0;
    }
  }

  const finalReputation = Math.max(-1.0, baselineReputation - validDenouncementWeight);
  const suppressionDrop = baselineReputation - finalReputation;

  // Invariant 3: Independent Risk calculation (never 1 - reputation)
  // Low reputation is not risk; risk is elevated only by corroborated malicious signals
  const risk = validDenouncementWeight > 0 ? Math.min(1.0, validDenouncementWeight * 0.5) : 0.0;

  // Confidence is proportional to verified evidence volume
  const evidenceVolume = contributor.directVouches.length + contributor.denouncements.length;
  const confidence = Math.min(1.0, evidenceVolume * 0.35);

  return {
    id: contributor.id,
    role: contributor.role,
    reputation: Number(finalReputation.toFixed(3)),
    risk,
    confidence: Number(confidence.toFixed(3)),
    baselineReputation: Number(baselineReputation.toFixed(3)),
    suppressionDrop: Number(suppressionDrop.toFixed(3)),
  };
}
