export type Theme = "light" | "dark";

export function readTheme(value: string | null): Theme {
  return value === "dark" ? "dark" : "light";
}

export function readThemePreference(): Theme {
  try {
    return readTheme(window.localStorage.getItem("advisor-theme"));
  } catch {
    return "light";
  }
}

export function writeThemePreference(theme: Theme): void {
  try {
    window.localStorage.setItem("advisor-theme", theme);
  } catch {
    /* A denied optional preference must not prevent application use. */
  }
}
