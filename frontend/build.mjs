import { build } from "esbuild";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));

await build({
  entryPoints: ["src/index.ts"],
  outfile: "../web/main.js",
  bundle: true,
  format: "esm",
  target: "es2020",
  minify: false,
  sourcemap: false,
  legalComments: "none",
  banner: { js: "// Comfy-DeepSeekAPI · ImageCompositorHelper v" + pkg.version + " (built from frontend/src, do not edit)" },
  external: ["../../scripts/app.js", "../../scripts/api.js"],
  logLevel: "info",
});
