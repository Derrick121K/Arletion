import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const { buildDir } = JSON.parse(await readFile(resolve(root, ".arletion-latest-build.json"), "utf8"));
const server = resolve(root, buildDir, "standalone/server.js");
const child = spawn(process.execPath, [server], { cwd: resolve(server, ".."), env: process.env, stdio: "inherit" });
child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
