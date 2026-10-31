import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export interface ArchitectureViolation {
  filePath: string;
  line: number;
  rawLine: string;
  importTarget: string;
  rule: string;
}

const IMPORT_PATTERN = /(?:from\s+|import\s*\(?\s*|require\s*\(\s*)["']([^"']+)["']/;

const FORBIDDEN_CORE_PACKAGES = [
  '@opencred/github-app',
  '@opencred/cli',
  '@opencred/simulation',
  'probot',
  '@octokit',
  'commander',
  'express',
  'fastify',
];

function isForbiddenCorePackage(specifier: string): boolean {
  return FORBIDDEN_CORE_PACKAGES.some((pkg) => {
    return specifier === pkg || specifier.startsWith(`${pkg}/`);
  });
}

function findSourceFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) {
    return [];
  }

  const results: string[] = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name === '.git') {
      continue;
    }

    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...findSourceFiles(fullPath));
    } else if (/\.(ts|tsx|js|mjs|cjs)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      results.push(fullPath);
    }
  }

  return results;
}

export function checkFile(
  filePath: string,
  packageType: 'core' | 'cli',
  rootDir: string,
): ArchitectureViolation[] {
  const violations: ArchitectureViolation[] = [];
  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split('\n');

  const coreDir = path.resolve(rootDir, 'packages/core');
  const githubAppDir = path.resolve(rootDir, 'packages/github-app');
  const cliDir = path.resolve(rootDir, 'packages/cli');
  const simulationDir = path.resolve(rootDir, 'packages/simulation');

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i] ?? '';
    const trimmed = rawLine.trim();

    // Skip single-line comments and comment block continuations
    if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) {
      continue;
    }

    const match = rawLine.match(IMPORT_PATTERN);
    if (!match) {
      continue;
    }

    const importTarget = match[1] ?? '';
    const lineNum = i + 1;

    if (packageType === 'core') {
      // Rule 1: Core cannot import forbidden packages/external interface packages
      if (isForbiddenCorePackage(importTarget)) {
        violations.push({
          filePath,
          line: lineNum,
          rawLine,
          importTarget,
          rule: 'Core must have no dependency on GitHub, Probot, CLI, simulation, or interface packages.',
        });
        continue;
      }

      // Rule 2: Core cannot import relatively from github-app, cli, or simulation
      if (importTarget.startsWith('.')) {
        const resolvedPath = path.resolve(path.dirname(filePath), importTarget);
        const isInGithubApp =
          resolvedPath === githubAppDir || resolvedPath.startsWith(`${githubAppDir}${path.sep}`);
        const isInCli = resolvedPath === cliDir || resolvedPath.startsWith(`${cliDir}${path.sep}`);
        const isInSimulation =
          resolvedPath === simulationDir || resolvedPath.startsWith(`${simulationDir}${path.sep}`);
        const isOutsideCore =
          !resolvedPath.startsWith(`${coreDir}${path.sep}`) && resolvedPath !== coreDir;

        if (isInGithubApp || isInCli || isInSimulation || isOutsideCore) {
          violations.push({
            filePath,
            line: lineNum,
            rawLine,
            importTarget,
            rule: 'Core cannot import relatively from packages outside packages/core.',
          });
        }
      }
    } else if (packageType === 'cli') {
      // Rule 3: CLI cannot import from github-app
      if (
        importTarget === '@opencred/github-app' ||
        importTarget.startsWith('@opencred/github-app/')
      ) {
        violations.push({
          filePath,
          line: lineNum,
          rawLine,
          importTarget,
          rule: 'CLI cannot depend on or import from github-app.',
        });
        continue;
      }

      if (importTarget.startsWith('.')) {
        const resolvedPath = path.resolve(path.dirname(filePath), importTarget);
        if (
          resolvedPath === githubAppDir ||
          resolvedPath.startsWith(`${githubAppDir}${path.sep}`)
        ) {
          violations.push({
            filePath,
            line: lineNum,
            rawLine,
            importTarget,
            rule: 'CLI cannot relatively import from github-app.',
          });
        }
      }
    }
  }

  return violations;
}

export function checkArchitecture(rootDir: string): ArchitectureViolation[] {
  const violations: ArchitectureViolation[] = [];

  const coreFiles = findSourceFiles(path.join(rootDir, 'packages/core'));
  for (const file of coreFiles) {
    violations.push(...checkFile(file, 'core', rootDir));
  }

  const cliFiles = findSourceFiles(path.join(rootDir, 'packages/cli'));
  for (const file of cliFiles) {
    violations.push(...checkFile(file, 'cli', rootDir));
  }

  return violations;
}

export function runCli(rootDir: string = process.cwd()): void {
  const violations = checkArchitecture(rootDir);

  if (violations.length > 0) {
    console.error('❌ Architecture boundary violations found:');
    for (const v of violations) {
      const relPath = path.relative(rootDir, v.filePath);
      console.error(`\nFile: ${relPath}:${v.line}`);
      console.error(`Rule: ${v.rule}`);
      console.error(`Import Target: ${v.importTarget}`);
      console.error(`Offending line:\n  ${v.rawLine.trim()}`);
    }
    process.exit(1);
  }

  console.log('✓ Architecture check passed: no boundary violations detected.');
}

const currentFilePath = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(currentFilePath)) {
  runCli();
}
