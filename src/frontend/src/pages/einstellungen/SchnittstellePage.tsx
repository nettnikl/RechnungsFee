import { useQuery } from '@tanstack/react-query'
import { getSchnittstelle } from '../../api/client'
import { useMxAuto } from '../../hooks/useAnsicht'

export function SchnittstellePage() {
  const mxAuto = useMxAuto()
  const { data, isLoading, error } = useQuery({
    queryKey: ['schnittstelle'],
    queryFn: getSchnittstelle,
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
        <section className="space-y-2">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            {data.aktiv ? 'MCP ist an.' : 'MCP ist aus.'}
          </p>
          {data.token && (
            <p className="text-sm font-mono text-slate-800 dark:text-slate-100 break-all">{data.token}</p>
          )}
        </section>
      )}
    </div>
  )
}
