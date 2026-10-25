/** @type {import('next').NextConfig} */
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = dirname(fileURLToPath(import.meta.url));
const nextConfig = {
  output: "standalone",
  distDir: process.env.ARLETION_BUILD_DIR || ".next-arletion",
  outputFileTracingRoot: projectRoot,
  turbopack: { root: projectRoot },
  typescript: { tsconfigPath: process.env.ARLETION_TSCONFIG_PATH || "tsconfig.json" },
};
export default nextConfig;
