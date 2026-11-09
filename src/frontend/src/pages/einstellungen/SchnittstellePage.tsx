import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getSchnittstelle,
  invoke,
  isTauri,
  schnittstelleAktivieren,
  schnittstelleDeaktivieren,
  schnittstelleTokenRotieren,
} from '../../api/client'
import { useMxAuto } from '../../hooks/useAnsicht'

const labelCls = 'block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1'
const inputCls = 'w-full min-w-0 border border-slate-300 dark:border-slate-600 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-slate-700 dark:text-slate-100'
const abschnittCls = 'text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide'

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0 disabled:opacity-50 ${checked ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'}`}
    >
      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-4' : 'translate-x-0.5'}`} />
    </button>
  )
}

async function mcpAdresse(): Promise<string> {
  if (isTauri() && !import.meta.env.DEV) {
    const port = await invoke<number>('get_backend_port')
    return `http://127.0.0.1:${port}/mcp/`
  }
  return 'http://127.0.0.1:8002/mcp/'
}

export function SchnittstellePage() {
  const mxAuto = useMxAuto()
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['schnittstelle'],
    queryFn: getSchnittstelle,
  })
  const { data: adresse } = useQuery({
    queryKey: ['schnittstelle-adresse'],
    queryFn: mcpAdresse,
    enabled: Boolean(data?.aktiv),
  })
  const [hinweis, setHinweis] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)

  function merken(naechster: { aktiv: boolean }) {
    queryClient.setQueryData(['schnittstelle'], naechster)
    setFehler(null)
  }

  const schalter = useMutation({
    mutationFn: (an: boolean) => (an ? schnittstelleAktivieren() : schnittstelleDeaktivieren()),
    onSuccess: merken,
    onError: (err: Error) => setFehler(err.message),
  })
  const rotieren = useMutation({
    mutationFn: schnittstelleTokenRotieren,
    onSuccess: (status) => {
      merken(status)
      setHinweis('Token erneuert. Bestehende Verbindungen brauchen den neuen Wert.')
    },
    onError: (err: Error) => setFehler(err.message),
  })

  async function kopieren(text: string, meldung: string) {
    await navigator.clipboard.writeText(text)
    setHinweis(meldung)
  }

  const snippet = data?.token && adresse
    ? JSON.stringify({
        mcpServers: {
          rechnungsfee: {
            url: adresse,
            headers: { Authorization: `Bearer ${data.token}` },
          },
        },
      }, null, 2)
    : ''

  return (
    <div className={`p-6 max-w-2xl ${mxAuto} space-y-8`}>
      <div>
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-1">MCP</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Ein Client auf diesem Rechner kann Rechnungen und Stammdaten lesen, solange MCP an ist.
        </p>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Wird geladen…</p>}
      {error && <p className="text-sm text-red-600">{(error as Error).message}</p>}

      {data && (
        <div className="flex items-center justify-between border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3">
          <div>
            <p className="text-sm font-medium text-slate-800 dark:text-slate-100">MCP aktivieren</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Schaltet die MCP-Endpunkte ein.</p>
          </div>
          <Toggle
            checked={data.aktiv}
            disabled={schalter.isPending}
            onChange={(an) => {
              setHinweis(null)
              schalter.mutate(an)
            }}
          />
        </div>
      )}

      {data?.aktiv && data.token && (
        <section className="space-y-3">
          <h2 className={abschnittCls}>Token</h2>
          <div className="border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-4">
            <div>
              <label htmlFor="api-token" className={labelCls}>Token</label>
              <div className="flex gap-2">
                <input id="api-token" readOnly value={data.token} className={inputCls} />
                <button
                  type="button"
                  title="Kopieren"
                  aria-label="Token kopieren"
                  onClick={() => kopieren(data.token!, 'Token kopiert.')}
                  className="shrink-0 inline-flex items-center justify-center rounded-lg border border-slate-300 dark:border-slate-600 w-9 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  <span className="material-symbols-outlined leading-none" style={{ fontSize: '1.1rem' }}>content_copy</span>
                </button>
                <button
                  type="button"
                  title="Token erneuern"
                  aria-label="Token erneuern"
                  disabled={rotieren.isPending}
                  onClick={() => {
                    if (!window.confirm('Der bisherige Token funktioniert danach nicht mehr. Trotzdem erneuern?')) return
                    setHinweis(null)
                    rotieren.mutate()
                  }}
                  className="shrink-0 inline-flex items-center justify-center rounded-lg border border-slate-300 dark:border-slate-600 w-9 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  <span className="material-symbols-outlined leading-none" style={{ fontSize: '1.1rem' }}>autorenew</span>
                </button>
              </div>
            </div>

            {adresse && (
              <div>
                <p className={labelCls}>MCP-Adresse</p>
                <p className="text-sm font-mono text-slate-800 dark:text-slate-100 break-all">{adresse}</p>
              </div>
            )}

            {snippet && (
              <div className="relative">
                <pre className="rounded-lg bg-slate-900 text-slate-100 text-xs p-3 pr-12 overflow-x-auto">{snippet}</pre>
                <button
                  type="button"
                  title="Konfiguration kopieren"
                  aria-label="Konfiguration kopieren"
                  onClick={() => kopieren(snippet, 'Konfiguration kopiert.')}
                  className="absolute top-2 right-2 inline-flex items-center justify-center rounded-md w-7 h-7 text-slate-300 hover:bg-slate-800"
                >
                  <span className="material-symbols-outlined leading-none" style={{ fontSize: '1.1rem' }}>content_copy</span>
                </button>
              </div>
            )}

            {hinweis && <p className="text-sm text-emerald-700 dark:text-emerald-400">{hinweis}</p>}
            {fehler && <p className="text-sm text-red-600">{fehler}</p>}
          </div>
        </section>
      )}

      {data && !data.aktiv && fehler && <p className="text-sm text-red-600">{fehler}</p>}

      {data && (
        <section className="space-y-3">
          <h2 className={abschnittCls}>Werkzeuge</h2>
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900 text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
                  <th className="text-left px-4 py-2.5 font-medium">Name</th>
                </tr>
              </thead>
              <tbody>
                {data.werkzeuge.map((name, i) => (
                  <tr
                    key={name}
                    className={`border-b border-slate-100 dark:border-slate-700 last:border-0 ${i % 2 === 0 ? '' : 'bg-slate-50/50 dark:bg-slate-900/30'}`}
                  >
                    <td className="px-4 py-2 font-mono text-slate-800 dark:text-slate-100">{name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
