import typescript from "@rollup/plugin-typescript";

export default {
  input: "src/index.ts",
  output: {
    file: "btoddb_ha_music.js",
    format: "iife",
    sourcemap: true,
  },
  plugins: [typescript()],
};
