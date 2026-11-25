import { useAuthStore } from "../stores/authStore";
import { PageHeader } from "../components/PageHeader";

export function Settings() {
  const user = useAuthStore((s) => s.user);
  return (
    <div className="page-workspace">
      <PageHeader title="Ustawienia" />
      <div className="workspace-panels">
        <section className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Profil</h2>
          <dl className="space-y-4 text-sm">
            <div>
              <dt className="text-gray-400">Imię</dt>
              <dd className="mt-1 break-words">{user?.display_name || "—"}</dd>
            </div>
            <div>
              <dt className="text-gray-400">E-mail</dt>
              <dd className="mt-1 break-all">{user?.email || "—"}</dd>
            </div>
          </dl>
        </section>
        <section className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Preferencje</h2>
          <dl className="space-y-4 text-sm">
            <div>
              <dt className="text-gray-400">Język interfejsu</dt>
              <dd className="mt-1">Polski</dd>
            </div>
            <div>
              <dt className="text-gray-400">Waluta bazowa raportów</dt>
              <dd className="mt-1">
                PLN — walutę konta wybierasz przy jego tworzeniu.
              </dd>
            </div>
          </dl>
          <p className="mt-4 text-sm text-gray-400">
            Zmiana języka i zapisywanie indywidualnych preferencji nie są
            jeszcze dostępne.
          </p>
        </section>
        <section className="card">
          <h2 className="text-lg font-semibold text-white mb-3">
            Działania Doradcy
          </h2>
          <p className="text-sm text-gray-300">
            Dostępny zakres działań i wymagane potwierdzenia są określane przez
            serwer dla poszczególnych narzędzi.
          </p>
          <p className="mt-3 text-sm text-gray-400">
            Zmiana poziomu autonomii nie jest dostępna w tym widoku. Ten ekran
            nie zmienia uprawnień ani zasad zatwierdzania.
          </p>
        </section>
        <section className="card">
          <h2 className="text-lg font-semibold text-white mb-4">O aplikacji</h2>
          <p className="text-sm text-gray-400">
            Personal Advisor — zarządzanie czasem, pieniędzmi i projektami.
          </p>
        </section>
      </div>
    </div>
  );
}
