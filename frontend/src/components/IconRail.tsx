import { NavLink } from "react-router-dom";
import { navigationContexts, type NavigationContext } from "./navigation";

type IconRailProps = {
  activeContext: NavigationContext;
};

export function IconRail({ activeContext }: IconRailProps) {
  return (
    <aside className="w-[52px] shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
      <nav className="p-2 space-y-2" aria-label="Obszary aplikacji">
        {navigationContexts.map((context) => {
          const className = `flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
            context.id === activeContext.id
              ? "bg-gray-800 text-white"
              : "text-gray-400 hover:bg-gray-800 hover:text-gray-100"
          }`;

          return context.to ? (
            <NavLink
              key={context.id}
              to={context.to}
              title={context.label}
              aria-label={context.label}
              className={className}
            >
              <context.icon className="w-5 h-5" />
            </NavLink>
          ) : (
            <span
              key={context.id}
              title={`${context.label} - Wkrótce`}
              aria-label={`${context.label} - Wkrótce`}
              aria-disabled="true"
              className={`${className} cursor-not-allowed opacity-50`}
            >
              <context.icon className="w-5 h-5" />
            </span>
          );
        })}
      </nav>
    </aside>
  );
}
