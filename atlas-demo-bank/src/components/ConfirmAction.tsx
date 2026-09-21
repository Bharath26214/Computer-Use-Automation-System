type ConfirmActionProps = {
  title: string
  body: string
  confirmTestId: string
  cancelTestId?: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmAction({
  title,
  body,
  confirmTestId,
  cancelTestId = 'confirm-cancel',
  confirmLabel = 'Yes, Confirm',
  cancelLabel = 'No',
  onConfirm,
  onCancel,
}: ConfirmActionProps) {
  return (
    <section
      data-testid="confirm-action"
      className="mb-6 max-w-xl rounded-xl border border-amber-200 bg-amber-50 p-6 shadow-sm"
    >
      <h2 className="text-xl font-semibold text-atlas-navy">{title}</h2>
      <p className="mt-3 text-sm text-slate-700">{body}</p>
      <div className="mt-6 flex gap-3">
        <button
          type="button"
          data-testid={cancelTestId}
          onClick={onCancel}
          className="flex-1 rounded-md border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-atlas-navy hover:bg-slate-50"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          data-testid={confirmTestId}
          onClick={onConfirm}
          className="flex-1 rounded-md bg-atlas-teal px-4 py-3 text-sm font-semibold text-white hover:bg-[#1a5f67]"
        >
          {confirmLabel}
        </button>
      </div>
    </section>
  )
}
