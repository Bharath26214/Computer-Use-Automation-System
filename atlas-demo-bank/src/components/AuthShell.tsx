import type { ReactNode } from 'react'

type AuthShellProps = {
  title: string
  children: ReactNode
}

export function AuthShell({ title, children }: AuthShellProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-atlas-sand px-4 py-10">
      <section className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs uppercase tracking-[0.22em] text-atlas-teal">Atlas Bank</p>
        <h1 className="mt-2 text-2xl font-semibold text-atlas-navy">{title}</h1>
        {children}
      </section>
    </div>
  )
}
