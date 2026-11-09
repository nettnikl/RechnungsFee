import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getSchnittstelle, schnittstelleAktivieren, schnittstelleDeaktivieren } from '../../api/client'
import { useMxAuto } from '../../hooks/useAnsicht'

export function SchnittstellePage() {
  const mxAuto = useMxAuto()
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['schnittstelle'],
    queryFn: getSchnittstelle,
  })
  const [fehler, setFehler] = useState<string | null>(null)

  const schalter = useMutation({
    mutationFn: (an: boolean) => (an ? schnittstelleAktivieren() : schnittstelleDeaktivieren()),
    onSuccess: (status) => {
      queryClient.setQueryData(['schnittstelle'], status)
      setFehler(null)
    },
    onError: (err: Error) => setFehler(err.message),
  })

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
            onClick={() => schalter.mutate(!data.aktiv)}
            className="flex items-center justify-between w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 text-left"
          >
            <span className="text-sm font-medium text-slate-800 dark:text-slate-100">MCP</span>
            <span className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${data.aktiv ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}`}>
              <span className={`inline-block h-5 w-5 mt-0.5 rounded-full bg-white transition-transform ${data.aktiv ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </span>
          </button>

          {data.token && (
            <p className="text-sm font-mono text-slate-800 dark:text-slate-100 break-all">{data.token}</p>
          )}
          {fehler && <p className="text-sm text-red-600">{fehler}</p>}
        </section>
      )}
    </div>
  )
}
