import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export interface DiffResult {
  path: string;
  value1: unknown;
  value2: unknown;
  message: string;
}

export function findFirstDifference(
  obj1: unknown,
  obj2: unknown,
  currentPath = '',
): DiffResult | null {
  if (obj1 === obj2) {
    return null;
  }

  if (typeof obj1 !== typeof obj2) {
    return {
      path: currentPath || 'root',
      value1: obj1,
      value2: obj2,
      message: `Type mismatch: ${typeof obj1} !== ${typeof obj2}`,
    };
  }

  if (obj1 === null || obj2 === null || typeof obj1 !== 'object') {
    return {
      path: currentPath || 'root',
      value1: obj1,
      value2: obj2,
      message: `Value mismatch: ${JSON.stringify(obj1)} !== ${JSON.stringify(obj2)}`,
    };
  }

  if (Array.isArray(obj1) !== Array.isArray(obj2)) {
    return {
      path: currentPath || 'root',
      value1: obj1,
      value2: obj2,
      message: `Array mismatch: Array.isArray was ${Array.isArray(obj1)} vs ${Array.isArray(obj2)}`,
    };
  }

  if (Array.isArray(obj1) && Array.isArray(obj2)) {
    if (obj1.length !== obj2.length) {
      return {
        path: `${currentPath}.length`,
        value1: obj1.length,
        value2: obj2.length,
        message: `Array length mismatch: ${obj1.length} !== ${obj2.length}`,
      };
    }

    for (let i = 0; i < obj1.length; i++) {
      const diff = findFirstDifference(obj1[i], obj2[i], `${currentPath}[${i}]`);
      if (diff) return diff;
    }

    return null;
  }

  const record1 = obj1 as Record<string, unknown>;
  const record2 = obj2 as Record<string, unknown>;

  const keys1 = Object.keys(record1).sort();
  const keys2 = Object.keys(record2).sort();

  for (const k of keys1) {
    if (!(k in record2)) {
      return {
        path: currentPath ? `${currentPath}.${k}` : k,
        value1: record1[k],
        value2: undefined,
        message: `Missing key in Run 2: "${k}"`,
      };
    }
  }

  for (const k of keys2) {
    if (!(k in record1)) {
      return {
        path: currentPath ? `${currentPath}.${k}` : k,
        value1: undefined,
        value2: record2[k],
        message: `Extra key in Run 2: "${k}"`,
      };
    }
  }

  for (const k of keys1) {
    const nextPath = currentPath ? `${currentPath}.${k}` : k;
    const diff = findFirstDifference(record1[k], record2[k], nextPath);
    if (diff) return diff;
  }

  return null;
}

export function runSimulationAndGetOutput(rootDir: string): {
  rawBuffer: Buffer;
  parsedJson: unknown;
} {
  execSync('npm run simulation:gate', { cwd: rootDir, stdio: 'pipe' });

  const reportPath = path.resolve(rootDir, 'packages/simulation/output/simulation-report.json');
  if (!fs.existsSync(reportPath)) {
    throw new Error(`Expected simulation report at ${reportPath} does not exist`);
  }

  const rawBuffer = fs.readFileSync(reportPath);
  const parsedJson = JSON.parse(rawBuffer.toString('utf8'));
  return { rawBuffer, parsedJson };
}

export function checkDeterminism(rootDir = process.cwd()): {
  identical: boolean;
  diff: DiffResult | null;
} {
  // First simulation run
  const run1 = runSimulationAndGetOutput(rootDir);

  // Second simulation run with the same seed
  const run2 = runSimulationAndGetOutput(rootDir);

  // Byte-for-byte comparison of output files
  const byteEqual = run1.rawBuffer.equals(run2.rawBuffer);
  if (byteEqual) {
    return { identical: true, diff: null };
  }

  const diff = findFirstDifference(run1.parsedJson, run2.parsedJson);
  return { identical: false, diff };
}

export function runCli(): void {
  console.log('🔄 Checking simulation determinism across dual consecutive runs with seed 42...');
  const { identical, diff } = checkDeterminism();

  if (!identical) {
    console.error('\n❌ DETERMINISM CHECK FAILED: Simulation output differed byte for byte.');
    if (diff) {
      console.error(`First differing field:`);
      console.error(`  Field Path: ${diff.path}`);
      console.error(`  Run 1: ${JSON.stringify(diff.value1)}`);
      console.error(`  Run 2: ${JSON.stringify(diff.value2)}`);
      console.error(`  Details: ${diff.message}`);
    } else {
      console.error('  Raw byte mismatch occurred in formatted JSON output.');
    }
    process.exit(1);
  }

  console.log(
    '✅ DETERMINISM CHECK PASSED: Simulation outputs are byte-for-byte identical across runs.',
  );
}

const currentFilePath = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(currentFilePath)) {
  runCli();
}
