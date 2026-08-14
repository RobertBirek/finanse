# Dwupoziomowy sidebar — specyfikacja

## Cel
Zastąpić płaski sidebar układem `IconRail + ContextualSidebar`, gdzie URL wybiera kontekst, a menu pokazuje wyłącznie elementy aktywnego obszaru.

## Architektura
- `IconRail` ma szerokość około 52px, pokazuje wyłącznie ikony i tooltipy.
- `ContextualSidebar` ma około 224px, zawiera stały header, przewijane menu oraz obecny UserPanel.
- Jedna data-driven konfiguracja definiuje obszary, ich domyślne trasy i elementy menu.
- Aktywny kontekst wynika z najdłuższego pasującego prefiksu URL, nie z local state.

## Trasy
Istniejące `/finances` pozostaje bez zmian. Przyszłe strony finansowe używają `/finances/*`; nie tworzymy pustych route’ów dla niedostępnych modułów.

## Konteksty
`today`, `organization`, `finance`, `advisor`, `knowledge`, `automation`, `system` z mapowaniem zgodnym z zaakceptowanym planem użytkownika. Niedostępne pozycje są oznaczone „Wkrótce”, bez linku.

## Granice
Nie zmieniać auth, topbara, zawartości stron, logiki biznesowej, istniejących route’ów ani globalnej palety. Wykorzystać React Router `NavLink`, Tailwind i istniejące SVG; nie instalować biblioteki ikon.

## Weryfikacja
Testy mapowania route→context i active state, frontend lint, TypeScript, Vitest oraz production build.
