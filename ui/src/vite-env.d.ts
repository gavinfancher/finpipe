/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_EDITION?: "oss" | "managed";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
