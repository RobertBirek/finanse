# Contextual Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat navigation with a responsive icon rail and URL-driven contextual sidebar without changing routes, authentication, topbar, page content, or the dark visual system.

**Architecture:** A single navigation module will own the seven context definitions, menu entries, existing inline SVG icon components, path matching, and active-item predicate. `IconRail` and `ContextualSidebar` will consume that module, while `Layout` only composes responsive navigation and retains the current overlay, header, outlet, user state, and logout behavior. Context resolution will inspect configured path prefixes and select the longest matching prefix, so nested routes remain in their parent context without duplicated component state.

**Tech Stack:** React 18, TypeScript, React Router v6, Tailwind CSS, Vitest, Testing Library.

---

## File Structure

- Create: `frontend/src/components/navigation.tsx` - typed context/menu configuration, existing inline SVG icons, URL context resolver, and active-item predicate.
- Create: `frontend/src/components/navigation.test.ts` - unit coverage for longest-prefix context selection and contextual-menu active states.
- Create: `frontend/src/components/IconRail.tsx` - icon-only desktop context selector with accessible native tooltips.
- Create: `frontend/src/components/ContextualSidebar.tsx` - selected context header, enabled `NavLink` menu, disabled forthcoming rows, and reusable user panel.
- Modify: `frontend/src/components/Layout.tsx` - replaces the flat sidebar with the two navigation components and uses the same sidebar composition on mobile.
- Modify: `docs/CHANGELOG.md` - records the added navigation architecture and verification result.
- Modify: `docs/TASKS.md` - records completion of the contextual-sidebar work.
- Modify: `docs/JOURNAL.md` - records the session scope, routing decision, and verification.

### Task 1: Specify and Test URL-Driven Navigation

**Files:**
- Create: `frontend/src/components/navigation.test.ts`
- Create: `frontend/src/components/navigation.tsx`

- [ ] **Step 1: Write the failing route and active-state tests**

```tsx
import { describe, expect, it } from "vitest";
import {
  getContextForPathname,
  isMenuItemActive,
  navigationContexts,
} from "./navigation";

describe("getContextForPathname", () => {
  it("uses the context with the longest matching route prefix", () => {
    expect(getContextForPathname("/projects/project-42").id).toBe("organization");
    expect(getContextForPathname("/finances/cashflow").id).toBe("finance");
  });

  it("falls back to today for a pathname outside the configuration", () => {
    expect(getContextForPathname("/unknown").id).toBe("today");
  });
});

describe("isMenuItemActive", () => {
  const projects = navigationContexts.find(
    (context) => context.id === "organization",
  )!.items[0];

  it("marks nested routes active without matching a sibling prefix", () => {
    expect(isMenuItemActive(projects, "/projects/project-42")).toBe(true);
    expect(isMenuItemActive(projects, "/projects-archive")).toBe(false);
  });
});
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `npm run test -- src/components/navigation.test.ts`

Expected: FAIL because `./navigation` does not exist.

- [ ] **Step 3: Add the navigation contracts and pure URL helpers**

Create `frontend/src/components/navigation.tsx` with these exported types and helpers. Use `React.ComponentType<{ className?: string }>` for existing inline SVG components so no icon dependency is installed.

```tsx
export type NavigationMenuItem = {
  label: string;
  to?: string;
  soon?: boolean;
};

export type NavigationContext = {
  id:
    | "today"
    | "organization"
    | "finance"
    | "advisor"
    | "knowledge"
    | "automation"
    | "system";
  label: string;
  to?: string;
  icon: IconComponent;
  routePrefixes: string[];
  items: NavigationMenuItem[];
};

export const getContextForPathname = (pathname: string): NavigationContext => {
  const match = navigationContexts
    .flatMap((context) =>
      context.routePrefixes
        .filter((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
        .map((prefix) => ({ context, prefix })),
    )
    .sort((left, right) => right.prefix.length - left.prefix.length)[0];

  return match?.context ?? navigationContexts[0];
};

export const isMenuItemActive = (
  item: NavigationMenuItem,
  pathname: string,
): boolean =>
  Boolean(item.to) && (pathname === item.to || pathname.startsWith(`${item.to}/`));
```

Define this single configuration in declaration order: `today` (`/today`, `/inbox`, `/calendar`); `organization` (`/projects`); `finance` (`/finances`); `advisor` (`/advisor`); `knowledge` (`/documents`); disabled `automation` (no `to` or route prefix); and `system` (`/settings`). The first six enabled entries must retain the current routes and labels. Add `"Automatyzacje"` and `"Reguły"` as disabled automation menu items, and `"Budżet"` plus `"Cele finansowe"` as disabled finance menu items. Disabled entries use `soon: true` and have no `to`, so the configuration cannot create a route.

Move the existing `SunIcon`, `InboxIcon`, `FolderIcon`, `CalendarIcon`, `WalletIcon`, `SparklesIcon`, `DocumentIcon`, and `CogIcon` JSX exactly from `Layout.tsx` into this module. Reuse `CogIcon` for the disabled automation rail entry; no new SVG artwork is required.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run: `npm run test -- src/components/navigation.test.ts`

Expected: PASS with three tests.

- [ ] **Step 5: Commit the tested navigation contract**

```bash
git add frontend/src/components/navigation.tsx frontend/src/components/navigation.test.ts
git commit -m "feat: dodaj konfigurację nawigacji kontekstowej"
```

### Task 2: Build Icon Rail and Contextual Menu

**Files:**
- Create: `frontend/src/components/IconRail.tsx`
- Create: `frontend/src/components/ContextualSidebar.tsx`
- Modify: `frontend/src/components/navigation.tsx`

- [ ] **Step 1: Write failing component tests for enabled and forthcoming navigation**

Extend `frontend/src/components/navigation.test.ts` with the pure behavior needed by the components:

```tsx
it("keeps forthcoming entries out of the route surface", () => {
  const finance = navigationContexts.find((context) => context.id === "finance")!;
  const budget = finance.items.find((item) => item.label === "Budżet")!;
  const automation = navigationContexts.find(
    (context) => context.id === "automation",
  )!;

  expect(budget.to).toBeUndefined();
  expect(budget.soon).toBe(true);
  expect(automation.to).toBeUndefined();
});
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `npm run test -- src/components/navigation.test.ts`

Expected: FAIL until the forthcoming entries are represented in the configuration.

- [ ] **Step 3: Create `IconRail` from the shared configuration**

Implement `IconRail` as a `w-[52px] shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col` desktop component. It receives `activeContext`, renders every `navigationContexts` entry in source order, and uses the native `title={context.label}` attribute for a dependency-free tooltip. For an entry with `to`, render a `NavLink` with `aria-label`, an icon, and active `bg-gray-800 text-white`; otherwise render a disabled `<span aria-disabled="true" title={`${context.label} — Wkrótce`}>` with `cursor-not-allowed opacity-50`. The rail must not create local selection state.

```tsx
type IconRailProps = { activeContext: NavigationContext };

export function IconRail({ activeContext }: IconRailProps) {
  return (
    <aside className="w-[52px] shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
      <nav className="p-2 space-y-2" aria-label="Obszary aplikacji">
        {navigationContexts.map((context) => {
          const content = <context.icon className="w-5 h-5" />;
          return context.to ? (
            <NavLink key={context.id} to={context.to} title={context.label} aria-label={context.label}>
              {content}
            </NavLink>
          ) : (
            <span key={context.id} title={`${context.label} — Wkrótce`} aria-disabled="true">
              {content}
            </span>
          );
        })}
      </nav>
    </aside>
  );
}
```

Apply the highlighted class from `activeContext.id`, rather than relying on `NavLink` exact matching, so an existing nested route such as `/projects/:id` keeps its area highlighted.

- [ ] **Step 4: Create `ContextualSidebar` with the current UserPanel behavior**

Implement `ContextualSidebar` with `context`, `user`, `onLogout`, and optional `onNavigate` props. It is `w-56 bg-gray-900 border-r border-gray-800 flex flex-col h-full`: a fixed Advisor header, the selected context label below it, a scrollable menu, and the existing avatar/name/email/logout panel at the bottom. Enabled items use `NavLink`, call `onNavigate`, and keep the existing `sidebar-link` styles; disabled items are noninteractive rows ending in `Wkrótce`, with `aria-disabled="true"`, muted colors, and no route. Call `onLogout` from the existing logout button.

```tsx
{context.items.map((item) =>
  item.to ? (
    <NavLink key={item.label} to={item.to} className="sidebar-link" onClick={onNavigate}>
      {item.label}
    </NavLink>
  ) : (
    <div key={item.label} className="sidebar-link cursor-not-allowed opacity-50" aria-disabled="true">
      <span>{item.label}</span>
      <span className="ml-auto text-xs">Wkrótce</span>
    </div>
  ),
)}
```

- [ ] **Step 5: Run the focused test to verify GREEN**

Run: `npm run test -- src/components/navigation.test.ts`

Expected: PASS with the route, active-state, and forthcoming-entry tests.

- [ ] **Step 6: Commit the reusable sidebar components**

```bash
git add frontend/src/components/IconRail.tsx frontend/src/components/ContextualSidebar.tsx frontend/src/components/navigation.tsx frontend/src/components/navigation.test.ts
git commit -m "feat: dodaj rail i menu kontekstowe"
```

### Task 3: Compose Responsive Navigation in Layout

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Test: `frontend/src/components/navigation.test.ts`

- [ ] **Step 1: Write a failing test for a nested existing path's context**

Add this assertion so the composition has a regression guard for the retained project-detail route:

```tsx
it("keeps a project detail in the organization context", () => {
  expect(getContextForPathname("/projects/1eaf6dce-ecda-4d42-89dd-1ca52d9e67d2").label).toBe(
    "Organizacja",
  );
});
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `npm run test -- src/components/navigation.test.ts`

Expected: FAIL until the organization prefix is included in the navigation configuration.

- [ ] **Step 3: Refactor only `Layout` to consume the components**

Remove `navItems` and all inline icon functions from `Layout.tsx`. Import `useLocation`, `IconRail`, `ContextualSidebar`, and `getContextForPathname`. Resolve `const activeContext = getContextForPathname(location.pathname)` on every render. Retain the current mobile overlay, `mobileOpen` state, topbar markup, `<Outlet />`, padding, auth-store lookup, and logout mutation.

Desktop structure:

```tsx
<div className="hidden lg:flex h-full">
  <IconRail activeContext={activeContext} />
  <ContextualSidebar
    context={activeContext}
    user={user}
    onLogout={() => logout.mutate()}
  />
</div>
```

Mobile structure: keep the fixed 240px (`w-60`) drawer and overlay behavior, but place only `ContextualSidebar` inside it. Pass `onNavigate={() => setMobileOpen(false)}` so the drawer closes after selecting an existing entry. Do not render `IconRail` in the narrow drawer, avoiding a two-column mobile navigation with reduced tap targets. The existing hamburger button continues to control this same drawer.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run: `npm run test -- src/components/navigation.test.ts`

Expected: PASS with all route-resolution tests.

- [ ] **Step 5: Run the frontend quality gate**

Run: `npm run test && npm run lint && npm run typecheck && npm run build`

Expected: all commands exit 0; Vite writes the production bundle to `frontend/dist`.

- [ ] **Step 6: Commit layout integration**

```bash
git add frontend/src/components/Layout.tsx frontend/src/components/navigation.test.ts
git commit -m "refactor: użyj sidebaru kontekstowego w layout"
```

### Task 4: Record the Completed Slice

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`

- [ ] **Step 1: Add verified session records**

Add an `Unreleased` changelog entry describing the data-driven `IconRail + ContextualSidebar`, longest-prefix URL resolution, disabled `Wkrótce` items, and the exact frontend quality-gate results. Add a completed sidebar task to `TASKS.md`. Add a new top journal session with scope, files/components, the URL-as-source-of-truth decision, and any verification limitation only if one occurs.

- [ ] **Step 2: Verify the final diff and documentation**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; status shows only the sidebar implementation, its tests, approved spec/plan, and session documentation.

- [ ] **Step 3: Commit the documented vertical slice**

```bash
git add docs/CHANGELOG.md docs/TASKS.md docs/JOURNAL.md docs/superpowers/specs/2026-08-14-contextual-sidebar-design.md docs/superpowers/plans/2026-08-14-contextual-sidebar.md
git commit -m "docs: opisz sidebar kontekstowy"
```

## Plan Self-Review

- Spec coverage: Tasks 1-3 cover one data-driven config, both components, existing SVG reuse, URL longest-prefix selection, active state, tooltips, disabled future entries, UserPanel, responsive use of the same context data, and the unchanged `/finances` route. Task 3 explicitly limits the refactor to `Layout` and preserves auth, topbar, content, routes, and colors.
- Placeholder scan: no `TBD`, `TODO`, deferred implementation, or undefined helper is present.
- Type consistency: `NavigationContext`, `NavigationMenuItem`, `getContextForPathname`, and `isMenuItemActive` are defined in Task 1 and used consistently in later tasks.
