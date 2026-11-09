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
        <section className="space-y-4">
          <button
            type="button"
            role="switch"
            aria-checked={data.aktiv}
            disabled={schalter.isPending}
            onClick={() => {
              setHinweis(null)
              schalter.mutate(!data.aktiv)
            }}
            className="flex items-center justify-between w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 text-left"
          >
            <span className="text-sm font-medium text-slate-800 dark:text-slate-100">MCP</span>
            <span className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${data.aktiv ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}`}>
              <span className={`inline-block h-5 w-5 mt-0.5 rounded-full bg-white transition-transform ${data.aktiv ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </span>
          </button>

          {data.aktiv && data.token && (
            <div className="space-y-2">
              <label htmlFor="api-token" className="text-sm font-medium text-slate-700 dark:text-slate-300">Token</label>
              <div className="flex gap-2">
                <input
                  id="api-token"
                  readOnly
                  value={data.token}
                  className="flex-1 min-w-0 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-900 px-3 py-2 text-sm font-mono text-slate-800 dark:text-slate-100"
                />
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
          )}

          {data.aktiv && adresse && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">MCP-Adresse</p>
              <p className="text-sm font-mono text-slate-600 dark:text-slate-300 break-all">{adresse}</p>
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
            </div>
          )}

          {hinweis && <p className="text-sm text-emerald-700 dark:text-emerald-400">{hinweis}</p>}
          {fehler && <p className="text-sm text-red-600">{fehler}</p>}
        </section>
      )}
    </div>
  )
}
