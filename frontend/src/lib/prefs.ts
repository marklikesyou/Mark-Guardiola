const LEAGUE_KEY = "markguardiola.selectedLeagueId";
const IDENTITY_KEY = "markguardiola.localIdentity";

export const DEFAULT_IDENTITY = "local-owner";

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    return;
  }
}

export function getLocalIdentity(): string {
  return safeGet(IDENTITY_KEY) ?? DEFAULT_IDENTITY;
}

export function getSelectedLeagueId(): string | null {
  return safeGet(LEAGUE_KEY);
}

export function setSelectedLeagueId(id: string | null): void {
  safeSet(LEAGUE_KEY, id);
}
