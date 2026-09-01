const CLASSIC_LETTER: Record<string, string> = {
  GK: "P",
  DEF: "D",
  MID: "C",
  FWD: "A",
};

const CLASSIC_NAME: Record<string, string> = {
  GK: "Portiere",
  DEF: "Difensore",
  MID: "Centrocampista",
  FWD: "Attaccante",
};

const CLASSIC_GROUP: Record<string, string> = {
  GK: "Portieri",
  DEF: "Difensori",
  MID: "Centrocampisti",
  FWD: "Attaccanti",
};


export function roleLetter(role: string): string {
  return CLASSIC_LETTER[role] ?? role;
}

export function roleName(role: string): string {
  return CLASSIC_NAME[role] ?? role;
}

export function roleGroupName(role: string): string {
  return CLASSIC_GROUP[role] ?? role;
}


export const CLASSIC_ROLE_ORDER = ["GK", "DEF", "MID", "FWD"] as const;

const MANTRA_GROUP: Record<string, "GK" | "DEF" | "MID" | "FWD"> = {
  Por: "GK",
  Dd: "DEF",
  Dc: "DEF",
  Ds: "DEF",
  B: "DEF",
  E: "MID",
  M: "MID",
  C: "MID",
  W: "FWD",
  T: "FWD",
  A: "FWD",
  Pc: "FWD",
};

const POSITION_WORDS: Record<string, string> = {
  gk: "Portiere",
  goalkeeper: "Portiere",
  def: "Difensore",
  defender: "Difensore",
  "centre back": "Difensore centrale",
  "center back": "Difensore centrale",
  "full back": "Terzino",
  "wing back": "Esterno basso",
  mid: "Centrocampista",
  midfielder: "Centrocampista",
  "defensive midfielder": "Mediano",
  "attacking midfielder": "Trequartista",
  fwd: "Attaccante",
  forward: "Attaccante",
  striker: "Punta",
  substitute: "Riserva",
};


export function positionLabel(position: string | null): string | null {
  if (position === null || position.trim() === "") return null;
  const normalized = position.toLowerCase().replace(/-/g, " ").trim();
  return POSITION_WORDS[normalized] ?? position;
}


export function classicGroupOf(roles: readonly string[]): string {
  for (const candidate of CLASSIC_ROLE_ORDER) {
    if (roles.includes(candidate)) return candidate;
  }
  return "other";
}

const POSITION_GROUPS: Record<string, "GK" | "DEF" | "MID" | "FWD"> = {
  gk: "GK",
  goalkeeper: "GK",
  portiere: "GK",
  def: "DEF",
  defender: "DEF",
  "centre back": "DEF",
  "center back": "DEF",
  "full back": "DEF",
  "wing back": "DEF",
  mid: "MID",
  midfielder: "MID",
  "defensive midfielder": "MID",
  "attacking midfielder": "MID",
  fwd: "FWD",
  forward: "FWD",
  striker: "FWD",
};


export function positionGroup(
  position: string | null,
): "GK" | "DEF" | "MID" | "FWD" | null {
  if (position === null) return null;
  const normalized = position.toLowerCase().replace(/-/g, " ").trim();
  return POSITION_GROUPS[normalized] ?? null;
}


export function pitchGroupOf(
  roles: readonly string[],
  primaryPosition: string | null,
): "GK" | "DEF" | "MID" | "FWD" | "other" {
  for (const candidate of CLASSIC_ROLE_ORDER) {
    if (roles.includes(candidate)) return candidate;
  }
  for (const role of roles) {
    const group = MANTRA_GROUP[role];
    if (group) return group;
  }
  return positionGroup(primaryPosition) ?? "other";
}
