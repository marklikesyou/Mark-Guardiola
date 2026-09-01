import fs from "node:fs";

const path = process.argv[2];
if (path === undefined) throw new Error();
const source = fs.readFileSync(path, "utf8");
const cleaned = source
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n")
  .map((line) => line.trimEnd())
  .join("\n")
  .replace(/^\n+/, "");
fs.writeFileSync(path, cleaned);
