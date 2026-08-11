import { useAuthStore } from "../stores/authStore";

export function Settings() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-white mb-6">Ustawienia</h1>

      <div className="space-y-6">
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Profil</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Imię
              </label>
              <input
                value={user?.display_name || ""}
                readOnly
                className="input opacity-60"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Email
              </label>
              <input
                value={user?.email || ""}
                readOnly
                className="input opacity-60"
              />
            </div>
          </div>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">
            Preferencje
          </h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-200">Język</p>
                <p className="text-xs text-gray-500">Język interfejsu</p>
              </div>
              <select className="input w-40">
                <option value="pl">Polski</option>
                <option value="en">English</option>
              </select>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-200">Waluta domyślna</p>
                <p className="text-xs text-gray-500">
                  Waluta dla nowych kont i transakcji
                </p>
              </div>
              <select className="input w-40">
                <option value="PLN">PLN</option>
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
              </select>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-200">Poziom autonomii AI</p>
                <p className="text-xs text-gray-500">
                  Jak samodzielny ma być Doradca
                </p>
              </div>
              <select className="input w-40" defaultValue="1">
                <option value="0">0 — Obserwacja</option>
                <option value="1">1 — Sugestie</option>
                <option value="2">2 — Zatwierdzenie</option>
                <option value="3">3 — Ograniczona</option>
              </select>
            </div>
          </div>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">
            O aplikacji
          </h2>
          <div className="text-sm text-gray-400 space-y-1">
            <p>Personal Advisor v0.2.0</p>
            <p>Osobisty system operacyjny do zarządzania czasem i pieniędzmi</p>
          </div>
        </div>
      </div>
    </div>
  );
}
