import MonacoEditor, {
  DiffEditor as MonacoDiffEditor,
  loader,
} from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import "monaco-editor/esm/vs/basic-languages/ini/ini.contribution";
import "monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution";
import JsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
import "monaco-editor/esm/vs/language/json/monaco.contribution";

self.MonacoEnvironment = {
  getWorker(_workerId, label) {
    return label === "json" ? new JsonWorker() : new EditorWorker();
  },
};
monaco.editor.defineTheme("localflow-dark", {
  base: "vs-dark",
  inherit: true,
  rules: [{ token: "comment", foreground: "86A77B" }],
  colors: {},
});
loader.config({ monaco });

export { MonacoDiffEditor, MonacoEditor };
