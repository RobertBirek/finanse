import type { ReactNode } from "react";

type PageHeaderProps = {
  title: ReactNode;
  description?: ReactNode;
  context?: ReactNode;
  actions?: ReactNode;
};

export function PageHeader({
  title,
  description,
  context,
  actions,
}: PageHeaderProps) {
  return (
    <header className="page-heading">
      <div className="page-heading-copy">
        {context && <div className="page-heading-context">{context}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-heading-actions">{actions}</div>}
    </header>
  );
}
