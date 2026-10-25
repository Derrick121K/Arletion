import { spawnSync } from "node:child_process";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const buildId = new Date().toISOString().replaceAll(/[^0-9TZ]/g, "-") + `-${process.pid}`;
const buildDir = process.env.ARLETION_BUILD_DIR || `.next-arletion-build-${buildId}`;
const tsconfigPath = `.arletion-tsconfig-${process.pid}.json`;
const tsconfig = JSON.parse(await readFile(resolve(root, "tsconfig.json"), "utf8"));
tsconfig.include = tsconfig.include.filter((item) => !item.startsWith(".next-arletion-build-"));
await writeFile(resolve(root, tsconfigPath), JSON.stringify(tsconfig, null, 2));
const nextCli = resolve(root, "node_modules/next/dist/bin/next");
const build = spawnSync(process.execPath, [nextCli, "build", "--webpack"], {
  cwd: root,
  env: { ...process.env, ARLETION_BUILD_DIR: buildDir, ARLETION_TSCONFIG_PATH: tsconfigPath },
  stdio: "inherit",
  shell: false,
});
await rm(resolve(root, tsconfigPath), { force: true });
if (build.error) throw build.error;
if (build.status !== 0) process.exit(build.status ?? 1);

const output = resolve(root, buildDir);
const standalone = resolve(output, "standalone");
await mkdir(resolve(standalone, "public"), { recursive: true });
await cp(resolve(root, "public"), resolve(standalone, "public"), { recursive: true, force: true });
await mkdir(resolve(standalone, buildDir, "static"), { recursive: true });
await cp(resolve(output, "static"), resolve(standalone, buildDir, "static"), { recursive: true, force: true });
await writeFile(resolve(root, ".arletion-latest-build.json"), JSON.stringify({ buildDir }, null, 2));
console.log(`Standalone build ready at ${standalone}`);
