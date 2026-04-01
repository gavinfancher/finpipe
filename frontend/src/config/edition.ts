export type Edition = "oss" | "managed";

export const EDITION: Edition = (import.meta.env.VITE_EDITION ?? "oss") as Edition;
export const isManaged = EDITION === "managed";
