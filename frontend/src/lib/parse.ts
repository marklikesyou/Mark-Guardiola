import Papa from "papaparse";

export const MAX_IMPORT_BYTES = 2 * 1024 * 1024;
export const IMPORT_SIZE_ERROR = "Il limite è 2 MiB. Carica un file più piccolo o riduci l’elenco.";

export interface ParsedRow {
  name: string;

  roles: string[];
  team: string | null;

  price: string | null;
  line: number;
  issue: string | null;
}

export interface ParseResult {
  rows: ParsedRow[];
  issues: ParsedRow[];
  error: string | null;
}

const CLASSIC_LETTERS: Record<string, string> = {
  p: "GK",
  d: "DEF",
  c: "MID",
  a: "FWD",
};

const CANONICAL_ROLES = new Set(["GK", "DEF", "MID", "FWD"]);

const MANTRA_ROLES = new Set([
  "Por",
  "Dd",
  "Ds",
  "Dc",
  "B",
  "E",
  "M",
  "C",
  "W",
  "T",
  "A",
  "Pc",
]);

const WORD_ROLES: Record<string, string> = {
  portiere: "GK",
  difensore: "DEF",
  centrocampista: "MID",
  attaccante: "FWD",
  gk: "GK",
  def: "DEF",
  mid: "MID",
  fwd: "FWD",
};

export type ParseMode = "classic" | "mantra";






export function normalizeRoleToken(
  token: string,
  mode: ParseMode = "classic",
): string | null {
  const trimmed = token.trim();
  if (trimmed === "") return null;
  const lower = trimmed.toLowerCase();

  if (mode === "mantra") {
    for (const role of MANTRA_ROLES) {
      if (role.toLowerCase() === lower) return role;
    }
    if (lower === "portiere" || lower === "gk" || lower === "p") return "Por";
    return null;
  }

  if (Object.hasOwn(WORD_ROLES, lower)) return WORD_ROLES[lower] ?? null;
  if (trimmed.length === 1 && Object.hasOwn(CLASSIC_LETTERS, lower)) {
    return CLASSIC_LETTERS[lower] ?? null;
  }
  if (CANONICAL_ROLES.has(trimmed.toUpperCase())) return trimmed.toUpperCase();
  return null;
}

function splitRoleField(field: string): string[] {
  return field
    .split(/[;/|]/)
    .map((token) => token.trim())
    .filter(Boolean);
}

function detectSeparator(line: string): RegExp {
  if (line.includes("\t")) return /\t/;
  if (line.includes(";")) return /;/;
  return /,/;
}

const HEADER_WORDS = new Set([
  "nome",
  "giocatore",
  "calciatore",
  "name",
  "ruolo",
  "r",
  "role",
  "squadra",
  "team",
  "club",
  "prezzo",
  "costo",
  "crediti",
  "price",
  "quotazione",
  "fvm",
]);

function looksLikeHeader(fields: string[]): boolean {
  if (fields.length < 2) return false;
  const known = fields.filter((field) =>
    HEADER_WORDS.has(field.trim().toLowerCase()),
  );
  return known.length >= 2;
}

function parsePrice(field: string): { price: string | null; issue: string | null } {
  const cleaned = field.trim().replace(/\s/g, "").replace(",", ".");
  if (cleaned === "") return { price: null, issue: null };
  if (!/^\d+(\.\d+)?$/.test(cleaned)) {
    return { price: null, issue: "prezzo non numerico, ignorato" };
  }
  return { price: cleaned, issue: null };
}





export function parseRosterText(
  text: string,
  mode: ParseMode = "classic",
  maxEntries = 1000,
): ParseResult {
  const fail = (error: string): ParseResult => ({ rows: [], issues: [], error });
  if (text.length > MAX_IMPORT_BYTES || new TextEncoder().encode(text).byteLength > MAX_IMPORT_BYTES) {
    return fail(IMPORT_SIZE_ERROR);
  }
  const rows: ParsedRow[] = [];
  const source = text.replace(/^\uFEFF/, "");
  let records: string[][];
  if (source.includes('"')) {

    const csv = Papa.parse<string[]>(source, {
      delimitersToGuess: ["\t", ";", ","],
      dynamicTyping: false,
      skipEmptyLines: "greedy",
      preview: maxEntries + 2,
    });
    if (csv.errors.some((error) => error.code !== "UndetectableDelimiter")) {
      return fail("CSV non valido: controlla virgolette e separatori prima di continuare.");
    }
    records = csv.data;
  } else {

    const lines = source.split(/\r\n|\n|\r/).filter((line) => line.trim() !== "");
    if (lines.length > maxEntries + 1) return fail(`Troppi elementi: il limite è ${maxEntries} righe, inclusi i ruoli aggiuntivi.`);
    records = lines.map((line) => line.split(detectSeparator(line)));
  }

  let inputError: string | null = null;
  records.forEach((record, index) => {
    const fields = record.map((field) => field.trim());
    if (index === 0 && looksLikeHeader(fields)) return;
    if (fields.length > 4) {
      inputError = `Riga ${index + 1}: sono ammessi Nome, Ruolo, Squadra e Prezzo. Racchiudi tra virgolette i campi che contengono separatori.`;
      return;
    }

    const name = fields[0] ?? "";
    if (name === "" && fields.every((field) => field === "")) return;
    if (name.length === 0 || name.length > 200 || (fields[2]?.length ?? 0) > 160) {
      inputError = `Riga ${index + 1}: inserisci un nome (massimo 200 caratteri) e una squadra di massimo 160 caratteri.`;
      return;
    }

    const issues: string[] = [];
    let roles: string[] = [];
    if (fields.length > 1 && (fields[1] ?? "").trim() !== "") {
      const tokens = splitRoleField(fields[1] ?? "");
      const normalized = tokens
        .map((token) => normalizeRoleToken(token, mode))
        .filter((role): role is string => role !== null);
      if (normalized.length < tokens.length) {
        issues.push(`ruolo "${fields[1]}" non riconosciuto, ignorato`);
      }
      roles = [...new Set(normalized)];
    }

    const team =
      fields.length > 2 && (fields[2] ?? "").trim() !== ""
        ? (fields[2] ?? null)
        : null;

    let price: string | null = null;
    if (fields.length > 3) {
      const parsed = parsePrice(fields[3] ?? "");
      price = parsed.price;
      if (parsed.issue) issues.push(parsed.issue);
    }

    rows.push({
      name,
      roles,
      team,
      price,
      line: index + 1,
      issue: issues.length > 0 ? issues.join(". ") : null,
    });
  });

  if (inputError) return fail(inputError);
  if (rows.reduce((count, row) => count + Math.max(1, row.roles.length), 0) > maxEntries) {
    return fail(`Troppi elementi: il limite è ${maxEntries} righe, inclusi i ruoli aggiuntivi.`);
  }
  return { rows, issues: rows.filter((row) => row.issue !== null), error: null };
}


export function toImportPlayers(
  rows: ParsedRow[],
): Array<{
  name: string;
  role?: string;
  team?: string;
  purchase_price?: string;
}> {
  return rows.map((row) => ({
    name: row.name,
    ...(row.roles[0] ? { role: row.roles[0] } : {}),
    ...(row.team ? { team: row.team } : {}),
    ...(row.price !== null ? { purchase_price: row.price } : {}),
  }));
}
