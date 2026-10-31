import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { checkArchitecture } from '../scripts/check-architecture.js';

describe('Architecture Boundary Checker', () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'arch-test-'));
    fs.mkdirSync(path.join(tempDir, 'packages/core/src'), { recursive: true });
    fs.mkdirSync(path.join(tempDir, 'packages/cli/src'), { recursive: true });
    fs.mkdirSync(path.join(tempDir, 'packages/github-app/src'), { recursive: true });
    fs.mkdirSync(path.join(tempDir, 'packages/simulation/src'), { recursive: true });
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it('passes when no architectural boundary rules are violated', () => {
    // Valid core internal import
    fs.writeFileSync(
      path.join(tempDir, 'packages/core/src/util.ts'),
      'export const util = () => "ok";\n',
    );
    fs.writeFileSync(
      path.join(tempDir, 'packages/core/src/index.ts'),
      'import { util } from "./util.js";\nexport const core = util();\n',
    );

    // Valid CLI importing core
    fs.writeFileSync(
      path.join(tempDir, 'packages/cli/src/index.ts'),
      'import { core } from "@opencred/core";\nconsole.log(core);\n',
    );

    const violations = checkArchitecture(tempDir);
    expect(violations).toHaveLength(0);
  });

  it('fails when packages/core imports forbidden external interface packages', () => {
    fs.writeFileSync(
      path.join(tempDir, 'packages/core/src/probot-bad.ts'),
      'import { Probot } from "probot";\n',
    );
    fs.writeFileSync(
      path.join(tempDir, 'packages/core/src/octokit-bad.ts'),
      'import { Octokit } from "@octokit/rest";\n',
    );
    fs.writeFileSync(
      path.join(tempDir, 'packages/core/src/commander-bad.ts'),
      'import { Command } from "commander";\n',
    );

    const violations = checkArchitecture(tempDir);
    expect(violations).toHaveLength(3);

    const targets = violations.map((v) => v.importTarget);
    expect(targets).toContain('probot');
    expect(targets).toContain('@octokit/rest');
    expect(targets).toContain('commander');
  });

  it('fails when packages/core imports from github-app, cli, or simulation', () => {
    fs.writeFileSync(
      path.join(tempDir, 'packages/core/src/index.ts'),
      `import { app } from "@opencred/github-app";
import { cli } from "@opencred/cli";
import { sim } from "@opencred/simulation";
`,
    );

    const violations = checkArchitecture(tempDir);
    expect(violations).toHaveLength(3);
    const targets = violations.map((v) => v.importTarget);
    expect(targets).toContain('@opencred/github-app');
    expect(targets).toContain('@opencred/cli');
    expect(targets).toContain('@opencred/simulation');
  });

  it('fails when packages/core uses relative imports targeting external packages', () => {
    fs.writeFileSync(
      path.join(tempDir, 'packages/core/src/bad-rel.ts'),
      'import { app } from "../../github-app/src/index.js";\n',
    );

    const violations = checkArchitecture(tempDir);
    expect(violations).toHaveLength(1);
    expect(violations[0]?.importTarget).toBe('../../github-app/src/index.js');
  });

  it('fails when packages/cli imports from packages/github-app', () => {
    fs.writeFileSync(
      path.join(tempDir, 'packages/cli/src/bad-pkg.ts'),
      'import { app } from "@opencred/github-app";\n',
    );
    fs.writeFileSync(
      path.join(tempDir, 'packages/cli/src/bad-rel.ts'),
      'import { app } from "../../github-app/src/index.js";\n',
    );

    const violations = checkArchitecture(tempDir);
    expect(violations).toHaveLength(2);
    expect(violations.every((v) => v.filePath.includes('cli'))).toBe(true);
  });

  it('ignores commented-out imports', () => {
    fs.writeFileSync(
      path.join(tempDir, 'packages/core/src/index.ts'),
      `// import { Probot } from "probot";
/* import { Octokit } from "@octokit/rest"; */
* import { Command } from "commander";
`,
    );

    const violations = checkArchitecture(tempDir);
    expect(violations).toHaveLength(0);
  });
});
