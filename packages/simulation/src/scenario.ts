export interface ScenarioContributor {
  id: string;
  role: 'newcomer' | 'legitimate' | 'malicious_target' | 'ai_assisted' | 'sybil';
  prCount: number;
  closedPrCount: number;
  aiUsage: boolean;
  directVouches: { fromRepo: string; weight: number }[];
  denouncements: { fromRepo: string; weight: number }[];
}

export interface SimulationScenario {
  seed: number;
  contributors: ScenarioContributor[];
  trustedRepos: string[];
  maliciousRingRepos: string[];
}

/**
 * Deterministic pseudo-random number generator for reproducible scenarios
 */
function createPrng(seed: number): () => number {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

export function generateScenario(seed = 42): SimulationScenario {
  const prng = createPrng(seed);

  const trustedRepos = ['repo-primary', 'repo-core', 'repo-verified'];
  const maliciousRingRepos = ['colluding-ring-a', 'colluding-ring-b', 'colluding-ring-c'];

  // 1. Newcomers: Cold-start contributors with zero historical vouches/denouncements
  const newcomers: ScenarioContributor[] = [
    {
      id: 'newcomer-alice',
      role: 'newcomer',
      prCount: 1 + Math.floor(prng() * 3),
      closedPrCount: 1, // closed PR must not penalize newcomer
      aiUsage: false,
      directVouches: [],
      denouncements: [],
    },
    {
      id: 'newcomer-bob',
      role: 'newcomer',
      prCount: 1,
      closedPrCount: 0,
      aiUsage: false,
      directVouches: [],
      denouncements: [],
    },
  ];

  // 2. Legitimate Contributors: Established contributors with trusted vouches
  const legitimateContributors: ScenarioContributor[] = [
    {
      id: 'veteran-carol',
      role: 'legitimate',
      prCount: 25,
      closedPrCount: 2,
      aiUsage: false,
      directVouches: [
        { fromRepo: 'repo-primary', weight: 0.8 },
        { fromRepo: 'repo-core', weight: 0.75 },
      ],
      denouncements: [],
    },
  ];

  // 3. Malicious Target: Legitimate contributor attacked by an adversarial denouncement ring
  const maliciousTarget: ScenarioContributor = {
    id: 'legitimate-target-david',
    role: 'malicious_target',
    prCount: 18,
    closedPrCount: 1,
    aiUsage: false,
    directVouches: [
      { fromRepo: 'repo-primary', weight: 0.85 },
      { fromRepo: 'repo-verified', weight: 0.7 },
    ],
    // Coordinated attack from the colluding ring:
    denouncements: [
      { fromRepo: 'colluding-ring-a', weight: 1.0 },
      { fromRepo: 'colluding-ring-b', weight: 1.0 },
      { fromRepo: 'colluding-ring-c', weight: 1.0 },
    ],
  };

  // 4. AI-assisted contributor: Legitimate contributions utilizing AI tools
  const aiContributor: ScenarioContributor = {
    id: 'ai-assisted-eva',
    role: 'ai_assisted',
    prCount: 12,
    closedPrCount: 1,
    aiUsage: true,
    directVouches: [{ fromRepo: 'repo-core', weight: 0.65 }],
    denouncements: [],
  };

  return {
    seed,
    contributors: [...newcomers, ...legitimateContributors, maliciousTarget, aiContributor],
    trustedRepos,
    maliciousRingRepos,
  };
}
