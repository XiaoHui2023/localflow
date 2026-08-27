import { defineConfig } from "vite";
import legacy from "@vitejs/plugin-legacy";
import react from "@vitejs/plugin-react";

function monacoLegacyRegExpIndices() {
  const target = "/monaco-editor/esm/vs/editor/common/services/findSectionHeaders.js";
  return {
    name: "localflow-monaco-legacy-regexp-indices",
    enforce: "pre",
    transform(code, id) {
      if (!id.replaceAll("\\", "/").includes(target)) return null;
      const replacements = [
        ["new RegExp('\\\\bMARK:\\\\s*(.*)$', 'd')", "new RegExp('\\\\bMARK:\\\\s*(.*)$')"],
        ["const column = match.indices[1][0] + 1;", "const column = match.index + match[0].length - match[1].length + 1;"],
        ["const endColumn = match.indices[1][1] + 1;", "const endColumn = column + match[1].length;"],
      ];
      let next = code;
      for (const [source, replacement] of replacements) {
        if (!next.includes(source)) throw new Error(`Monaco compatibility source changed: ${source}`);
        next = next.replace(source, () => replacement);
      }
      return { code: next, map: null };
    },
  };
}

export default defineConfig({
  plugins: [
    monacoLegacyRegExpIndices(),
    react(),
    legacy({
      targets: ["Chrome >= 79", "Firefox >= 78"],
      renderModernChunks: false,
    }),
  ],
  base: "./",
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
});
